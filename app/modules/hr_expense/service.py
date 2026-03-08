"""
app/modules/hr_expense/service.py

All field names verified against schema.prisma (model HrExpense):
  date, details, accountFrom, accountTo, debit, credit, remainingBalance, createdAt
"""
from fastapi import HTTPException
from prisma import Prisma

from .schema import HrExpenseCreate, HrExpenseUpdate


async def list_expenses(db: Prisma, date_filter: dict):
    where: dict = {}
    if date_filter:
        where["date"] = date_filter
    return await db.hrexpense.find_many(where=where, order={"date": "desc"})


async def create_expense(db: Prisma, data: HrExpenseCreate):
    return await db.hrexpense.create(
        data={
            "date":             data.date,
            "details":          data.details,
            "accountFrom":      data.accountFrom,   
            "accountTo":        data.accountTo,     
            "debit":            data.debit,
            "credit":           data.credit,
            "remainingBalance": data.remaining_balance,
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