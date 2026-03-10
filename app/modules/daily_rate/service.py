from decimal import Decimal
from fastapi import HTTPException
from prisma import Prisma
from .schema import DailyRateCreate, DailyRateUpdate


async def get_current_rate(db: Prisma):
    """Return the most recent DailyRate record."""
    record = await db.dailyrate.find_first(order={"date": "desc"})
    if not record:
        raise HTTPException(status_code=404, detail="No daily rate has been set yet.")
    return record


async def get_rate_for_date(db: Prisma, for_date: str):
    """Return rate for a specific date, falling back to the nearest past rate."""
    from datetime import datetime, time
    d = datetime.strptime(for_date, "%Y-%m-%d").date()
    record = await db.dailyrate.find_first(
        where={"date": {"lte": datetime.combine(d, time.max)}},
        order={"date": "desc"},
    )
    if not record:
        raise HTTPException(status_code=404, detail=f"No rate found for {for_date} or earlier.")
    return record


async def list_rates(db: Prisma, limit: int = 30):
    return await db.dailyrate.find_many(order={"date": "desc"}, take=limit)


async def upsert_rate(db: Prisma, data: DailyRateCreate, set_by_email: str | None = None):
    """
    Create or update the rate for the given date.
    If a rate already exists for that date, update it (upsert by date).
    """
    from datetime import datetime, time
    dt = datetime.combine(data.date, time.min)

    existing = await db.dailyrate.find_first(
        where={"date": {"gte": datetime.combine(data.date, time.min),
                        "lte": datetime.combine(data.date, time.max)}}
    )
    payload = {
        "date":  dt,
        "rate":  data.rate,
        "setBy": data.setBy or set_by_email,
        "note":  data.note,
    }
    if existing:
        return await db.dailyrate.update(where={"id": existing.id}, data=payload)
    return await db.dailyrate.create(data=payload)


async def update_rate(db: Prisma, rate_id: str, data: DailyRateUpdate):
    record = await db.dailyrate.find_unique(where={"id": rate_id})
    if not record:
        raise HTTPException(status_code=404, detail="Rate record not found.")
    update_payload = {}
    if data.rate is not None:
        update_payload["rate"] = data.rate
    if data.note is not None:
        update_payload["note"] = data.note
    return await db.dailyrate.update(where={"id": rate_id}, data=update_payload)


async def delete_rate(db: Prisma, rate_id: str) -> None:
    record = await db.dailyrate.find_unique(where={"id": rate_id})
    if not record:
        raise HTTPException(status_code=404, detail="Rate record not found.")
    await db.dailyrate.delete(where={"id": rate_id})


async def convert_usd_to_bdt(db: Prisma, usd_amount: float) -> dict:
    """Utility: convert a USD amount using the latest rate."""
    record = await get_current_rate(db)
    rate   = float(record.rate)
    return {
        "usdAmount":  usd_amount,
        "rate":       rate,
        "bdtAmount":  round(usd_amount * rate, 2),
        "rateDate":   record.date.isoformat(),
    }