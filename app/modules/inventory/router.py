"""app/modules/inventory/router.py"""
from fastapi import APIRouter, Depends
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import ALL_ROLES, CEO_DIRECTOR
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
    _=Depends(CEO_DIRECTOR),
):
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
    _=Depends(CEO_DIRECTOR),
):
    return await update_item(db, item_id, body)


@router.delete("/{item_id}", status_code=204)
async def remove_item(
    item_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_item(db, item_id)