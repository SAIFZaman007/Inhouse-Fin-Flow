"""
app/modules/inventory/router.py
════════════════════════════════════════════════════════════════════════════════
v3 — search/filter on GET + dual-mode POST (single item & bulk Excel import)

  • GET    /inventory              → ALL_ROLES
      Optional `search` keyword — OR-matched across itemName, category,
      condition, assignedTo, notes (case-insensitive, partial match).
      Combinable with all DateRangeFilter params.

  • GET    /inventory/{item_id}    → ALL_ROLES (unchanged)

  • POST   /inventory              → HR_AND_ABOVE
      Dual-mode endpoint (multipart/form-data):

      ┌─────────────────────────────────────────────────────────────────┐
      │  MODE A — Single item (no file attached)                        │
      │  Send all InventoryCreate fields as form fields.                │
      │  Returns: InventoryResponse (HTTP 201)                          │
      ├─────────────────────────────────────────────────────────────────┤
      │  MODE B — Bulk Excel import (file attached)                     │
      │  Attach an .xlsx file in the `file` field.                      │
      │  Row 1 = headers; row 2+ = data. Per-row error isolation.       │
      │  Returns: InventoryBulkImportResponse (HTTP 201)                │
      └─────────────────────────────────────────────────────────────────┘

  • PATCH  /inventory/{item_id}    → HR_AND_ABOVE (unchanged)
  • DELETE /inventory/{item_id}    → HR_AND_ABOVE + structured response body (unchanged)
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date
from decimal import Decimal
from typing import Optional, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import ALL_ROLES, HR_AND_ABOVE
from app.shared.filters import DateRangeFilter

from .schema import (
    InventoryBulkImportResponse,
    InventoryCreate,
    InventoryResponse,
    InventoryUpdate,
)
from .service import (
    bulk_import_items,
    create_item,
    delete_item,
    get_item,
    list_inventory,
    update_item,
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[InventoryResponse])
async def get_inventory(
    search:  Optional[str] = Query(
        default=None,
        description=(
            "Partial / case-insensitive keyword search. "
            "Matched against itemName, category, condition, assignedTo, and notes "
            "via a single OR condition — any field containing the keyword is returned."
        ),
    ),
    filters: DateRangeFilter = Depends(),
    db:      Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    """
    List all inventory items.

    Filters (all combinable):
    - `search`     — single keyword matched across itemName, category, condition,
                     assignedTo, and notes (case-insensitive, partial match)
    - Date filters — period (daily/weekly/monthly/yearly) or explicit from/to
    """
    return await list_inventory(db, filters.to_prisma_filter(), search=search)


# ── Create / Bulk Import ──────────────────────────────────────────────────────

@router.post("", status_code=201)
async def add_item(
    # ── Optional Excel file — triggers bulk-import mode when present ───────────
    file: Optional[UploadFile] = File(
        default=None,
        description=(
            "Excel workbook (.xlsx) for bulk import. "
            "Row 1 must contain column headers; row 2+ are data rows. "
            "When this field is provided all form fields below are ignored."
        ),
    ),
    # ── Single-item form fields (used only when no file is attached) ───────────
    date:        Optional[date]    = Form(None,  description="Item date (YYYY-MM-DD). Required for single-item mode."),
    itemName:    Optional[str]     = Form(None,  description="Item name. Required for single-item mode."),
    category:    Optional[str]     = Form(None,  description="Item category."),
    quantity:    int               = Form(1,     description="Quantity (default 1)."),
    unitPrice:   float             = Form(0.0,   description="Unit price (default 0). totalPrice is auto-computed."),
    condition:   Optional[str]     = Form(None,  description="Item condition (e.g. New, Used, Damaged)."),
    assignedTo:  Optional[str]     = Form(None,  description="Person or team the item is assigned to."),
    notes:       Optional[str]     = Form(None,  description="Free-text notes."),
    db:          Prisma            = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
) -> Union[InventoryResponse, InventoryBulkImportResponse]:
    """
    Create one inventory item **or** bulk-import many from an Excel file.

    ---

    ### Mode A — Single item (no file attached)
    Submit all fields as `multipart/form-data`.

    | Field       | Required | Default | Notes                              |
    |-------------|----------|---------|------------------------------------|
    | date        | ✅ Yes   | —       | ISO-8601: YYYY-MM-DD               |
    | itemName    | ✅ Yes   | —       | —                                  |
    | category    | No       | null    | —                                  |
    | quantity    | No       | 1       | —                                  |
    | unitPrice   | No       | 0.00    | totalPrice auto-computed           |
    | condition   | No       | null    | e.g. New / Used / Damaged          |
    | assignedTo  | No       | null    | —                                  |
    | notes       | No       | null    | —                                  |

    **Returns:** `InventoryResponse`

    ---

    ### Mode B — Bulk Excel import (file attached)
    Attach an `.xlsx` file in the `file` field.

    **Excel format:**
    - **Row 1:** Column headers (case-insensitive; aliases accepted — see below)
    - **Row 2+:** Data rows (fully empty rows are skipped automatically)

    **Accepted header aliases:**

    | Column     | Accepted header names                          |
    |------------|------------------------------------------------|
    | date       | date                                           |
    | itemName   | itemname, item_name, item name, item           |
    | category   | category, cat                                  |
    | quantity   | quantity, qty                                  |
    | unitPrice  | unitprice, unit_price, unit price, price       |
    | condition  | condition                                      |
    | assignedTo | assignedto, assigned_to, assigned to, assignee |
    | notes      | notes, note, remarks                           |

    **Row isolation:** a malformed row never blocks the rest — it is collected
    into the `errors` list while valid rows are imported normally.

    **Returns:** `InventoryBulkImportResponse`
    ```json
    {
      "importedCount": 42,
      "skippedCount":  2,
      "records": [ ...InventoryResponse objects... ],
      "errors":  [ { "row": 5, "error": "Cannot parse date: '31-13-2024'" }, ... ]
    }
    ```

    Accessible by: CEO, DIRECTOR, HR (BDEV excluded).
    """
    # ── Mode B: bulk Excel import ──────────────────────────────────────────────
    if file and file.filename:
        return await bulk_import_items(db, file)

    # ── Mode A: single item creation ───────────────────────────────────────────
    if not date:
        raise HTTPException(
            status_code=422,
            detail="'date' is required when creating a single inventory item.",
        )
    if not itemName or not itemName.strip():
        raise HTTPException(
            status_code=422,
            detail="'itemName' is required when creating a single inventory item.",
        )

    body = InventoryCreate(
        date=date,
        itemName=itemName.strip(),
        category=category,
        quantity=quantity,
        unitPrice=Decimal(str(unitPrice)),
        condition=condition,
        assignedTo=assignedTo,
        notes=notes,
    )
    return await create_item(db, body)


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{item_id}", response_model=InventoryResponse)
async def get_inventory_item(
    item_id: str,
    db:      Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await get_item(db, item_id)


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{item_id}", response_model=InventoryResponse)
async def edit_item(
    item_id: str,
    body:    InventoryUpdate,
    db:      Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    """
    Partially update an inventory item.

    Accessible by: CEO, DIRECTOR, HR (BDEV excluded).
    """
    return await update_item(db, item_id, body)


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{item_id}", status_code=200)
async def remove_item(
    item_id: str,
    db:      Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    """
    Delete an inventory item.

    Accessible by: CEO, DIRECTOR, HR (BDEV excluded).
    Returns a structured success message.
    """
    await delete_item(db, item_id)
    return {
        "success": True,
        "message": "Inventory item deleted successfully.",
        "id": item_id,
    }