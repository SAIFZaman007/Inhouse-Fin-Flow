"""
app/modules/hr_expense/service.py
========================================
v3 — full PATCH support + GET totals
"""
from datetime import date as dt_date, datetime, time
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from prisma import Prisma

from .schema import HrExpenseCreate, HrExpenseListResponse, HrExpenseTotals, HrExpenseUpdate

_ZERO = Decimal("0")


# ── Date helper ───────────────────────────────────────────────────────────────

def _dt(d: dt_date) -> datetime:
    """
    Convert datetime.date → datetime.datetime at midnight.

    prisma-py v0.14.0 requires a full datetime object for every
    DateTime @db.Date field — the same pattern used across the Fiverr
    module: datetime.combine(d, time.min).
    """
    return datetime.combine(d, time.min)


def _d(v) -> Decimal:
    """Safely coerce a Prisma Decimal/None to Python Decimal."""
    if v is None:
        return _ZERO
    return Decimal(str(v))


# ── Field map: snake_case (schema) → camelCase (Prisma model) ─────────────────
_FIELD_MAP: dict[str, str] = {
    "remaining_balance": "remainingBalance",
}


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def list_expenses(db: Prisma, date_filter: dict) -> HrExpenseListResponse:
    """
    Fetch all HR expense records matching the date filter and compute
    aggregate totals in a single pass.

    totalRemainingBalance = sum(remainingBalance) + totalCredits - totalDebits
    This reflects the net effective balance after all movements in the window.
    """
    where: dict = {}
    if date_filter:
        where["date"] = date_filter

    rows = await db.hrexpense.find_many(where=where, order={"date": "desc"})

    total_debits    = _ZERO
    total_credits   = _ZERO
    total_remaining = _ZERO

    for r in rows:
        total_debits    += _d(r.debit)
        total_credits   += _d(r.credit)
        total_remaining += _d(r.remainingBalance)

    net_remaining_balance = total_remaining + total_credits - total_debits

    totals = HrExpenseTotals(
        totalRecords          = len(rows),
        totalDebits           = total_debits,
        totalCredits          = total_credits,
        totalRemainingBalance = net_remaining_balance,
    )

    return HrExpenseListResponse(totals=totals, records=rows)


async def create_expense(db: Prisma, data: HrExpenseCreate):
    """
    Create an HR expense record.
    All fields are optional — omitted fields fall back to safe defaults:
      • date              → today
      • details           → empty string
      • debit / credit    → 0
      • remaining_balance → 0
    """
    entry_date = data.date or dt_date.today()

    return await db.hrexpense.create(
        data={
            "date":             _dt(entry_date),
            "details":          data.details or "",
            "accountFrom":      data.accountFrom,
            "accountTo":        data.accountTo,
            "debit":            float(data.debit  or _ZERO),
            "credit":           float(data.credit or _ZERO),
            "remainingBalance": float(data.remaining_balance or _ZERO),
            "remarks":          data.remarks,
        }
    )


async def update_expense(db: Prisma, expense_id: str, data: HrExpenseUpdate):
    """
    Partially update an HR expense record.

    Supports patching: date, details, accountFrom, accountTo,
    debit, credit, remaining_balance, remarks.
    Only fields explicitly supplied in the request body are written.
    """
    existing = await db.hrexpense.find_unique(where={"id": expense_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")

    # Dump only the fields the caller actually provided
    update_data = data.model_dump(exclude_none=True)

    if not update_data:
        # Nothing to update — return the record as-is
        return existing

    # Remap snake_case keys → Prisma camelCase field names
    mapped: dict = {}
    for k, v in update_data.items():
        prisma_key = _FIELD_MAP.get(k, k)

        # date must be serialised to datetime for prisma-py
        if prisma_key == "date":
            mapped[prisma_key] = _dt(v)
        elif prisma_key in ("debit", "credit", "remainingBalance"):
            mapped[prisma_key] = float(v)
        else:
            mapped[prisma_key] = v

    return await db.hrexpense.update(where={"id": expense_id}, data=mapped)


async def delete_expense(db: Prisma, expense_id: str) -> None:
    existing = await db.hrexpense.find_unique(where={"id": expense_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")
    await db.hrexpense.delete(where={"id": expense_id})