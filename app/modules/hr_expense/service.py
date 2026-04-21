"""
app/modules/hr_expense/service.py
════════════════════════════════════════════════════════════════════════════════
v6 — search/filter keyword on list_expenses (Three-Layer Defence intact)
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date as dt_date, datetime, time
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from prisma import Prisma

from .schema import HrExpenseCreate, HrExpenseListResponse, HrExpenseTotals, HrExpenseUpdate

_ZERO = Decimal("0")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dt(d: dt_date) -> datetime:
    """
    Convert datetime.date → datetime.datetime at midnight.

    prisma-py v0.14.0 requires a full datetime object for every
    DateTime @db.Date field — the same pattern used across all modules:
    datetime.combine(d, time.min).
    """
    if isinstance(d, datetime):
        return d
    return datetime.combine(d, time.min)


def _d(v) -> Decimal:
    """Safely coerce a Prisma Decimal / None → Python Decimal."""
    if v is None:
        return _ZERO
    return Decimal(str(v))


# ── Field map: snake_case (schema) → camelCase (Prisma model) ─────────────────
_FIELD_MAP: dict[str, str] = {
    "remaining_balance": "remainingBalance",
}


# ── Serialiser — mirrors PMAK's _serialize_txn() ─────────────────────────────

def _serialize_expense(row) -> dict:
    """
    Serialise a HrExpense ORM row into a plain dict.
    Using a dict (not the ORM object) lets us inject the authoritative
    computed_balance in Layer 3 without fighting Pydantic / ORM coercions.
    """
    return {
        "id":               row.id,
        "date":             row.date.date() if hasattr(row.date, "date") else row.date,
        "details":          row.details,
        "accountFrom":      row.accountFrom,
        "accountTo":        row.accountTo,
        "debit":            _d(row.debit),
        "credit":           _d(row.credit),
        "remainingBalance": _d(row.remainingBalance),
        "remarks":          row.remarks,
        "createdAt":        row.createdAt,
        "updatedAt":        row.updatedAt,
    }


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def list_expenses(
    db:          Prisma,
    date_filter: dict,
    search:      str | None = None,
) -> HrExpenseListResponse:
    """
    Fetch all HR expense records matching the date filter and/or keyword search,
    then compute aggregate totals in a single pass.

    search — single case-insensitive keyword matched against details,
             accountFrom, accountTo, and remarks via a single OR clause.
             Combinable freely with date_filter (AND between the two conditions).

    totalRemainingBalance = sum(remainingBalance) + totalCredits − totalDebits
    This reflects the net effective balance after all movements in the window.
    """
    where: dict = {}

    if date_filter:
        where["date"] = date_filter

    if search:
        where["OR"] = [
            {"details":     {"contains": search, "mode": "insensitive"}},
            {"accountFrom": {"contains": search, "mode": "insensitive"}},
            {"accountTo":   {"contains": search, "mode": "insensitive"}},
            {"remarks":     {"contains": search, "mode": "insensitive"}},
        ]

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

    remainingBalance is auto-computed as:
        prev_record.remainingBalance − debit + credit

    where prev_record is the most-recent expense entry (ordered by createdAt desc).
    If no prior records exist, the opening balance is treated as 0.

    Caller may still override by explicitly supplying a non-zero remaining_balance
    in the request body — the system will use that value as-is.

    Three-layer defence (mirrors PMAK add_transaction):
      Layer 1 — computed_balance written into .create()
      Layer 2 — .find_unique() re-fetch immediately after write
      Layer 3 — computed_balance injected into the response dict

    Other optional fields:
      • date    → today  (if omitted)
      • details → ""     (if omitted)
      • debit / credit → 0 (if omitted)
    """
    entry_date = data.date or dt_date.today()
    debit_val  = _d(data.debit  or _ZERO)
    credit_val = _d(data.credit or _ZERO)

    # ── Fetch previous record to continue the running balance ──────────────────
    # Order by createdAt DESC — same-day entries are indistinguishable by date alone.
    latest = await db.hrexpense.find_first(order={"createdAt": "desc"})
    latest_balance = float(latest.remainingBalance) if latest else 0.0

    # ── caller_override guard (mirrors PMAK add_transaction [FIX-C]) ──────────
    # Only a non-None AND non-zero value is treated as a deliberate override.
    # Decimal("0") == "not provided" — prevents Swagger UI echoing the numeric
    # default from short-circuiting the auto-compute path.
    caller_override = (
        data.remaining_balance is not None
        and data.remaining_balance != Decimal("0")
    )

    if caller_override:
        # [Priority 1] Manual balance correction supplied by the caller.
        computed_balance = Decimal(str(data.remaining_balance))
    else:
        # [Priority 2] Auto-compute: previous balance − debit + credit
        computed_balance = Decimal(str(round(
            latest_balance - float(debit_val) + float(credit_val), 2
        )))

    # ── Layer 1: persist with the correct computed_balance ────────────────────
    created = await db.hrexpense.create(
        data={
            "date":             _dt(entry_date),
            "details":          data.details or "",
            "accountFrom":      data.accountFrom,
            "accountTo":        data.accountTo,
            "debit":            float(debit_val),
            "credit":           float(credit_val),
            "remainingBalance": float(computed_balance),
            "remarks":          data.remarks,
        }
    )

    # ── Layer 2: re-fetch the exact DB-committed row ───────────────────────────
    persisted = await db.hrexpense.find_unique(where={"id": created.id})

    # ── Layer 3: serialise + inject authoritative balance ─────────────────────
    response = _serialize_expense(persisted)
    response["remainingBalance"] = computed_balance
    return response


async def update_expense(db: Prisma, expense_id: str, data: HrExpenseUpdate):
    """
    Partially update an HR expense record.

    Supports patching: date, details, accountFrom, accountTo,
    debit, credit, remaining_balance, remarks.
    Only fields explicitly supplied in the request body are written.

    remainingBalance resolution (three-way priority — mirrors PMAK update_transaction):
      Priority 1 — explicit non-zero caller override  → trust it as a correction
      Priority 2 — debit or credit changed            → auto-recompute from stored state
      Priority 3 — neither                            → leave remainingBalance unchanged

    Auto-recompute formula:
        balance_before = existing.remainingBalance + existing.debit − existing.credit
        new_remaining  = balance_before − new_debit + new_credit

    Three-layer defence (mirrors PMAK update_transaction):
      Layer 1 — computed_balance written into .update()
      Layer 2 — .find_unique() re-fetch immediately after write
      Layer 3 — computed_balance injected into the response dict
    """
    existing = await db.hrexpense.find_unique(where={"id": expense_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")

    patch: dict = {}

    # ── Build patch dict field-by-field (mirrors PMAK explicit field checks) ──
    if data.date is not None:
        patch["date"] = _dt(data.date)
    if data.details is not None:
        patch["details"] = data.details
    if data.accountFrom is not None:
        patch["accountFrom"] = data.accountFrom
    if data.accountTo is not None:
        patch["accountTo"] = data.accountTo
    if data.debit is not None:
        patch["debit"] = float(data.debit)
    if data.credit is not None:
        patch["credit"] = float(data.credit)

    # ── remainingBalance resolution (three-way priority) ─────────────────────
    computed_balance: Optional[Decimal] = None

    caller_override = (
        data.remaining_balance is not None
        and data.remaining_balance != Decimal("0")
    )

    if caller_override:
        # [Priority 1] Manual balance correction supplied by the caller.
        computed_balance          = Decimal(str(data.remaining_balance))
        patch["remainingBalance"] = float(computed_balance)

    elif "debit" in patch or "credit" in patch:
        # [Priority 2] Debit or credit changed — auto-derive the new balance.
        #
        # Reverse the stored formula to recover the balance BEFORE this entry:
        #   stored formula:  remainingBalance = balance_before − debit + credit
        #   reversed:        balance_before   = remainingBalance + debit − credit
        #
        # Then apply the updated values:
        #   new_remainingBalance = balance_before − new_debit + new_credit
        balance_before = (
            float(_d(existing.remainingBalance))
            + float(_d(existing.debit))
            - float(_d(existing.credit))
        )
        new_debit  = float(patch.get("debit",  float(_d(existing.debit))))
        new_credit = float(patch.get("credit", float(_d(existing.credit))))

        computed_balance          = Decimal(str(round(
            balance_before - new_debit + new_credit, 2
        )))
        patch["remainingBalance"] = float(computed_balance)

    if data.remarks is not None:
        patch["remarks"] = data.remarks

    # ── Idempotent: nothing changed ────────────────────────────────────────────
    if not patch:
        return _serialize_expense(existing)

    # ── Layer 1: persist the patch (with correct remainingBalance) ────────────
    await db.hrexpense.update(where={"id": expense_id}, data=patch)

    # ── Layer 2: re-fetch the exact DB-committed row ───────────────────────────
    persisted = await db.hrexpense.find_unique(where={"id": expense_id})

    # ── Layer 3: serialise + inject authoritative balance ─────────────────────
    response = _serialize_expense(persisted)
    if computed_balance is not None:
        response["remainingBalance"] = computed_balance
    return response


async def delete_expense(db: Prisma, expense_id: str) -> None:
    existing = await db.hrexpense.find_unique(where={"id": expense_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")
    await db.hrexpense.delete(where={"id": expense_id})