"""
app/modules/dollar_exchange/service.py
CRUD operations for DollarExchange records.
"""
from fastapi import HTTPException
from prisma import Prisma

from .schema import DollarExchangeCreate, DollarExchangeUpdate


async def create_exchange(db: Prisma, data: DollarExchangeCreate):
    return await db.dollarexchange.create(
        data={
            "date":          data.date,
            "details":       data.details,
            "accountFrom":   data.accountFrom,     
            "accountTo":     data.accountTo,       
            "debit":         data.debit,
            "credit":        data.credit,
            "rate":          data.rate,
            "totalBdt":      data.total_bdt,
            "paymentStatus": data.payment_status,
        }
    )


async def list_exchanges(db: Prisma, date_filter: dict, payment_status: str | None = None):
    where: dict = {}
    if date_filter:
        where["date"] = date_filter
    if payment_status:
        where["paymentStatus"] = payment_status
    return await db.dollarexchange.find_many(where=where, order={"date": "desc"})


async def get_exchange(db: Prisma, exchange_id: str):
    record = await db.dollarexchange.find_unique(where={"id": exchange_id})
    if not record:
        raise HTTPException(status_code=404, detail="Exchange record not found")
    return record


async def update_exchange(db: Prisma, exchange_id: str, data: DollarExchangeUpdate):
    await get_exchange(db, exchange_id)
    update_data = data.model_dump(exclude_none=True)
    field_map = {"payment_status": "paymentStatus"}
    mapped = {field_map.get(k, k): v for k, v in update_data.items()}
    return await db.dollarexchange.update(where={"id": exchange_id}, data=mapped)


async def delete_exchange(db: Prisma, exchange_id: str):
    await get_exchange(db, exchange_id)
    await db.dollarexchange.delete(where={"id": exchange_id})


async def get_total_bdt(db: Prisma) -> float:
    result = await db.dollarexchange.aggregate(_sum={"totalBdt": True})
    return float(result.sum.totalBdt or 0)