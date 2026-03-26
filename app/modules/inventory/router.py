"""
app/modules/inventory/router.py
========================================
v2 — Role & response-body changes:
  • GET    /inventory              → ALL_ROLES (unchanged)
  • GET    /inventory/{item_id}    → ALL_ROLES (unchanged)
  • POST   /inventory              → HR_AND_ABOVE (CEO, DIRECTOR, HR — excludes BDEV)
  • PATCH  /inventory/{item_id}    → HR_AND_ABOVE
  • DELETE /inventory/{item_id}    → HR_AND_ABOVE + structured response body
"""
from fastapi import APIRouter, Depends
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import ALL_ROLES, HR_AND_ABOVE
from app.shared.filters import DateRangeFilter

from .schema import InventoryCreate, InventoryResponse, InventoryUpdate
from .service import create_item, delete_item, get_item, list_inventory, update_item

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("", response_model=list[InventoryResponse])
async def get_inventory(
    filters: DateRangeFilter = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await list_inventory(db, filters.to_prisma_filter())


@router.post("", response_model=InventoryResponse, status_code=201)
async def add_item(
    body: InventoryCreate,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    """
    Create an inventory item.

    Accessible by: CEO, DIRECTOR, HR (BDEV excluded).
    """
    return await create_item(db, body)


@router.get("/{item_id}", response_model=InventoryResponse)
async def get_inventory_item(
    item_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await get_item(db, item_id)


@router.patch("/{item_id}", response_model=InventoryResponse)
async def edit_item(
    item_id: str,
    body: InventoryUpdate,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    """
    Partially update an inventory item.

    Accessible by: CEO, DIRECTOR, HR (BDEV excluded).
    """
    return await update_item(db, item_id, body)


@router.delete("/{item_id}", status_code=200)
async def remove_item(
    item_id: str,
    db: Prisma = Depends(get_db),
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