"""
app/modules/hr_expense/service.py
========================================
v2 — date serialization fix

All field names verified against schema.prisma (model HrExpense):
  date, details, accountFrom, accountTo, debit, credit, remainingBalance,
  remarks, createdAt, updatedAt
"""
from datetime import date as dt_date, datetime, time

from fastapi import HTTPException
from prisma import Prisma

from .schema import HrExpenseCreate, HrExpenseUpdate


# ── Date helper ───────────────────────────────────────────────────────────────

def _dt(d: dt_date) -> datetime:
    """
    Convert datetime.date → datetime.datetime at midnight.

    prisma-py v0.14.0 requires a full datetime object for every
    DateTime @db.Date field — the same pattern used across the Fiverr
    module: datetime.combine(d, time.min).
    """
    return datetime.combine(d, time.min)


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def list_expenses(db: Prisma, date_filter: dict):
    where: dict = {}
    if date_filter:
        where["date"] = date_filter
    return await db.hrexpense.find_many(where=where, order={"date": "desc"})


async def create_expense(db: Prisma, data: HrExpenseCreate):
    return await db.hrexpense.create(
        data={
            "date":             _dt(data.date),          
            "details":          data.details,
            "accountFrom":      data.accountFrom,
            "accountTo":        data.accountTo,
            "debit":            float(data.debit),        
            "credit":           float(data.credit),       
            "remainingBalance": float(data.remaining_balance), 
            "remarks":          data.remarks,
        }
    )


async def update_expense(db: Prisma, expense_id: str, data: HrExpenseUpdate):
    existing = await db.hrexpense.find_unique(where={"id": expense_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")

    update_data = data.model_dump(exclude_none=True)
    field_map = {"remaining_balance": "remainingBalance"}
    mapped = {field_map.get(k, k): v for k, v in update_data.items()}
    return await db.hrexpense.update(where={"id": expense_id}, data=mapped)


async def delete_expense(db: Prisma, expense_id: str):
    existing = await db.hrexpense.find_unique(where={"id": expense_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")
    await db.hrexpense.delete(where={"id": expense_id})