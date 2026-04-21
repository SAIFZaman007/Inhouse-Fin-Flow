"""
app/modules/dollar_exchange/router.py
================================================================================
v4 — Access control tightened to CEO & DIRECTOR only:

  • GET    /dollar-exchange            → CEO_DIRECTOR
  • POST   /dollar-exchange            → CEO_DIRECTOR
  • PATCH  /dollar-exchange/{id}       → CEO_DIRECTOR
  • DELETE /dollar-exchange/{id}       → CEO_DIRECTOR  
  • GET    /dollar-exchange/export     → CEO_DIRECTOR
  • GET    /dollar-exchange/total-bdt  → CEO_DIRECTOR

  HR and BDEV roles have no access to any dollar exchange endpoint.
================================================================================
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR
from app.shared.filters import DateRangeFilter

from .schema import DollarExchangeCreate, DollarExchangeResponse, DollarExchangeUpdate
from .service import (
    create_exchange, delete_exchange, export_exchanges,
    get_exchange, get_total_bdt, list_exchanges, update_exchange,
)

router = APIRouter(prefix="/dollar-exchange", tags=["Dollar Exchange"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[DollarExchangeResponse])
async def get_exchanges(
    payment_status: Optional[str] = Query(
        default=None,
        description="Filter by payment status: RECEIVED | DUE",
    ),
    account_from: Optional[str] = Query(
        default=None,
        description="Partial / case-insensitive match on accountFrom (legacy — use account_name for OR search).",
    ),
    account_name: Annotated[
        Optional[str],
        Query(
            description=(
                "Case-insensitive partial search across BOTH accountFrom AND accountTo "
                "(OR logic — matches either side of the exchange)."
            )
        ),
    ] = None,
    search: Annotated[
        Optional[str],
        Query(
            description=(
                "Case-insensitive keyword search on the details field. "
                "e.g. ?search=Adobe returns all rows whose details mention 'Adobe'."
            )
        ),
    ] = None,
    filters: DateRangeFilter = Depends(),
    db:      Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    List dollar exchange records.

    Accessible by: CEO, DIRECTOR only.

    Filters (all combinable):
    - `payment_status` — RECEIVED | DUE
    - `account_from`   — legacy exact-side search on accountFrom
    - `account_name`   — OR search across both accountFrom and accountTo
    - `search`         — keyword search on the details field
    - Date filters     — period (daily/weekly/monthly/yearly) or explicit from/to

    Each row includes `createdAt` and `updatedAt`.
    """
    return await list_exchanges(
        db,
        date_filter=filters.to_prisma_filter(),
        payment_status=payment_status,
        account_from=account_from,
        account_name=account_name,
        search=search,
    )


# ── Export ────────────────────────────────────────────────────────────────────

@router.get(
    "/export",
    summary="Export dollar exchange records to Excel (.xlsx)",
    response_description="Excel workbook download",
)
async def export_exchanges_endpoint(
    payment_status: Optional[str] = Query(default=None, description="Filter: RECEIVED | DUE"),
    account_from:   Optional[str] = Query(default=None, description="Partial match on accountFrom"),
    account_name: Annotated[
        Optional[str],
        Query(description="OR search across accountFrom AND accountTo."),
    ] = None,
    search: Annotated[
        Optional[str],
        Query(description="Case-insensitive keyword search on the details field."),
    ] = None,
    filters:        DateRangeFilter = Depends(),
    db:             Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Export filtered dollar exchange records to Excel.

    Accessible by: CEO, DIRECTOR only.
    Supports the same filters as GET /dollar-exchange.
    DUE rows are highlighted in light red in the output workbook.
    """
    meta     = filters.meta()
    date_str = (meta["dateRange"]["from"] or "all").replace("-", "")
    label    = f"dollar_exchange_{date_str}"

    data, filename = await export_exchanges(
        db,
        date_filter=filters.to_prisma_filter(),
        payment_status=payment_status,
        account_from=account_from,
        account_name=account_name,
        search=search,
        label=label,
    )
    return Response(
        content=data,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Totals ────────────────────────────────────────────────────────────────────

@router.get("/total-bdt")
async def total_bdt(
    payment_status: Annotated[
        Optional[str],
        Query(description="Filter totals by status: RECEIVED | DUE"),
    ] = None,
    account_name: Annotated[
        Optional[str],
        Query(description="Case-insensitive partial search across accountFrom AND accountTo."),
    ] = None,
    search: Annotated[
        Optional[str],
        Query(description="Case-insensitive keyword search on the details field."),
    ] = None,
    filters: DateRangeFilter = Depends(),
    db:      Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Return aggregate BDT totals (total, received, due).

    Supports all the same filters as GET /dollar-exchange so the totals
    always reflect the currently active filter state.

    Accessible by: CEO, DIRECTOR only.
    """
    return await get_total_bdt(
        db,
        date_filter=filters.to_prisma_filter(),
        payment_status=payment_status,
        account_name=account_name,
        search=search,
    )


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("", response_model=DollarExchangeResponse, status_code=201)
async def add_exchange(
    body: DollarExchangeCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Create a dollar exchange record.

    Accessible by: CEO, DIRECTOR only.
    """
    return await create_exchange(db, body)


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{exchange_id}", response_model=DollarExchangeResponse)
async def get_exchange_detail(
    exchange_id: str,
    db:          Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Get a single dollar exchange record by ID.

    Accessible by: CEO, DIRECTOR only.
    """
    return await get_exchange(db, exchange_id)


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{exchange_id}", response_model=DollarExchangeResponse)
async def update_exchange_endpoint(
    exchange_id: str,
    body:        DollarExchangeUpdate,
    db:          Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Partially update a dollar exchange record.

    Accessible by: CEO, DIRECTOR only.
    """
    return await update_exchange(db, exchange_id, body)


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{exchange_id}", status_code=200)
async def delete_exchange_endpoint(
    exchange_id: str,
    db:          Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Delete a dollar exchange record.

    Accessible by: CEO, DIRECTOR only.
    Returns a structured success message.
    """
    await delete_exchange(db, exchange_id)
    return {
        "success": True,
        "message": "Dollar exchange record deleted successfully.",
        "id": exchange_id,
    }