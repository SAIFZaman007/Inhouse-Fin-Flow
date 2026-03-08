from typing import Optional
from fastapi import APIRouter, Depends, Query
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR
from app.shared.filters import DateRangeFilter

from .schema import DollarExchangeCreate, DollarExchangeResponse, DollarExchangeUpdate
from .service import (
    create_exchange, delete_exchange, get_exchange,
    get_total_bdt, list_exchanges, update_exchange,
)

router = APIRouter(prefix="/dollar-exchange", tags=["Dollar Exchange"])


@router.get("", response_model=list[DollarExchangeResponse])
async def get_exchanges(
    payment_status: Optional[str] = Query(default=None),
    filters: DateRangeFilter = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await list_exchanges(db, filters.to_prisma_filter(), payment_status)


@router.post("", response_model=DollarExchangeResponse, status_code=201)
async def add_exchange(body: DollarExchangeCreate, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)):
    return await create_exchange(db, body)


@router.get("/total-bdt")
async def total_bdt(db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)):
    return {"total_bdt": await get_total_bdt(db)}


@router.get("/{exchange_id}", response_model=DollarExchangeResponse)
async def get_exchange_detail(exchange_id: str, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)):
    return await get_exchange(db, exchange_id)


@router.patch("/{exchange_id}", response_model=DollarExchangeResponse)
async def update_exchange_endpoint(
    exchange_id: str, body: DollarExchangeUpdate, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)
):
    return await update_exchange(db, exchange_id, body)


@router.delete("/{exchange_id}", status_code=204)
async def delete_exchange_endpoint(
    exchange_id: str, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)
):
    await delete_exchange(db, exchange_id)