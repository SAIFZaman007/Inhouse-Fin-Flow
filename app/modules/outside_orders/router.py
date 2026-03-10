"""
app/modules/outside_orders/router.py

Role matrix:
  GET  (list / detail)  → HR_AND_ABOVE
  POST                  → HR_AND_ABOVE
  PATCH                 → HR_AND_ABOVE
  DELETE                → CEO_DIRECTOR
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR, HR_AND_ABOVE
from app.shared.filters import DateRangeFilter

from .schema import OutsideOrderCreate, OutsideOrderResponse, OutsideOrderUpdate
from .service import create_order, delete_order, get_order, list_orders, update_order

router = APIRouter(prefix="/outside-orders", tags=["Outside Orders"])


@router.get("", response_model=list[OutsideOrderResponse])
async def get_orders(
    status: Optional[str] = Query(default=None),
    filters: DateRangeFilter = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await list_orders(db, filters.to_prisma_filter(), status)


@router.post("", response_model=OutsideOrderResponse, status_code=201)
async def add_order(
    body: OutsideOrderCreate,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await create_order(db, body)


@router.get("/{order_id}", response_model=OutsideOrderResponse)
async def get_order_detail(
    order_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_order(db, order_id)


@router.patch("/{order_id}", response_model=OutsideOrderResponse)
async def update_order_endpoint(
    order_id: str,
    body: OutsideOrderUpdate,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await update_order(db, order_id, body)


@router.delete("/{order_id}", status_code=204)
async def delete_order_endpoint(
    order_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_order(db, order_id)