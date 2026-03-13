"""
app/modules/payoneer/service.py
════════════════════════════════════════════════════════════════════════════════
v2 — Enterprise Edition

Changes vs v1
─────────────
_resolve_account_by_name  NEW — case-insensitive account lookup by name.
_tx_to_dict               NEW — serialises a transaction row + accountName.
create_account            Returns enriched dict; optionally seeds opening tx.
add_transaction           Resolves account via ``data.account_name`` (not id).
list_accounts             Combined totals + per-account breakdown; period +
                          name filter + pagination aware.
get_account_transactions  Returns paginated dict with accountName on each row.

Datetime bug fix
────────────────
All date writes use ``datetime.combine(d, time.min)`` — bare datetime.date
values are rejected by prisma-client-py's JSON serialiser.
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import io
import logging
import math
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException
from prisma import Prisma

from app.shared.filters import DateRangeFilter, to_dt_start, to_dt_end
from app.shared.pagination import PageParams
from .schema import (
    PayoneerAccountCreate,
    PayoneerTransactionCreate,
)

logger = logging.getLogger(__name__)
_ZERO = Decimal("0")


# ── Private helpers ───────────────────────────────────────────────────────────

def _d(v: Any) -> Decimal:
    return _ZERO if v is None else Decimal(str(v))


def _tx_to_dict(tx: Any, account_name: str) -> dict:
    """ORM transaction → serialisable dict with accountName injected."""
    return {
        "id":               tx.id,
        "accountId":        tx.accountId,
        "accountName":      account_name,
        "date":             tx.date.date() if isinstance(tx.date, datetime) else tx.date,
        "details":          tx.details,
        "accountFrom":      tx.accountFrom,
        "accountTo":        tx.accountTo,
        "debit":            _d(tx.debit),
        "credit":           _d(tx.credit),
        "remainingBalance": _d(tx.remainingBalance),
    }


def _pagination_meta(pagination: Optional[PageParams], total: int) -> dict:
    if pagination is None:
        return {"page": 1, "pageSize": total, "total": total, "totalPages": 1}
    return {
        "page":       pagination.page,
        "pageSize":   pagination.page_size,
        "total":      total,
        "totalPages": math.ceil(total / pagination.page_size) if total > 0 else 1,
    }


async def _resolve_account_by_name(db: Prisma, account_name: str):
    """
    Return the active PayoneerAccount whose name matches ``account_name``
    (case-insensitive).  Raises HTTP 404 if not found.
    """
    account = await db.payoneeraccount.find_first(
        where={
            "accountName": {"equals": account_name, "mode": "insensitive"},
            "isActive":    True,
        }
    )
    if not account:
        raise HTTPException(
            status_code=404,
            detail=f"Payoneer account '{account_name}' not found.",
        )
    return account


# ── Account CRUD ──────────────────────────────────────────────────────────────

async def create_account(db: Prisma, data: PayoneerAccountCreate) -> dict:
    """
    Create a Payoneer account.  If ``initial_balance`` is provided, an
    opening credit transaction is inserted immediately.
    """
    existing = await db.payoneeraccount.find_unique(
        where={"accountName": data.accountName}
    )
    if existing:
        raise HTTPException(status_code=409, detail="Account name already exists.")

    account = await db.payoneeraccount.create(
        data={"accountName": data.accountName}
    )

    opening_tx: Optional[dict] = None
    if data.initial_balance is not None and data.initial_balance > 0:
        today = date.today()
        tx = await db.payoneertransaction.create(
            data={
                "accountId":        account.id,
                "date":             datetime.combine(today, time.min),
                "details":          data.opening_note,
                "accountFrom":      None,
                "accountTo":        data.accountName,
                "debit":            Decimal("0"),
                "credit":           data.initial_balance,
                "remainingBalance": data.initial_balance,
            }
        )
        opening_tx = _tx_to_dict(tx, account.accountName)

    return {
        "id":                account.id,
        "accountName":       account.accountName,
        "isActive":          account.isActive,
        "currentBalance":    float(data.initial_balance or _ZERO),
        "openingTransaction": opening_tx,
    }


async def list_accounts(
    db: Prisma,
    filters: DateRangeFilter,
    name: Optional[str] = None,
    pagination: Optional[PageParams] = None,
) -> dict:
    """
    Combined totals + paginated per-account breakdown.
    ``name`` performs case-insensitive partial search on accountName.
    """
    date_f = filters.to_prisma_filter()

    where: dict = {"isActive": True}
    if name:
        where["accountName"] = {"contains": name, "mode": "insensitive"}

    total_accounts = await db.payoneeraccount.count(where=where)

    find_kw: dict = dict(
        where=where,
        include={
            "transactions": {
                "where":    {"date": date_f} if date_f else {},
                "order_by": {"date": "desc"},
            },
        },
        order={"accountName": "asc"},
    )
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    accounts = await db.payoneeraccount.find_many(**find_kw)

    t_balance = _ZERO
    t_credit  = _ZERO
    t_debit   = _ZERO
    t_txcount = 0

    summaries = []
    for acc in accounts:
        # Current balance = latest transaction's remainingBalance (across ALL time)
        latest_tx = await db.payoneertransaction.find_first(
            where={"accountId": acc.id},
            order={"date": "desc"},
        )
        current_balance = _d(latest_tx.remainingBalance) if latest_tx else _ZERO

        # Period totals from the filtered transactions
        period_credit = sum((_d(t.credit) for t in acc.transactions), _ZERO)
        period_debit  = sum((_d(t.debit)  for t in acc.transactions), _ZERO)

        t_balance += current_balance
        t_credit  += period_credit
        t_debit   += period_debit
        t_txcount += len(acc.transactions)

        summaries.append({
            "id":               acc.id,
            "accountName":      acc.accountName,
            "isActive":         acc.isActive,
            "currentBalance":   float(current_balance),
            "periodCredit":     float(period_credit),
            "periodDebit":      float(period_debit),
            "transactionCount": len(acc.transactions),
            "recentTransactions": [
                _tx_to_dict(t, acc.accountName) for t in acc.transactions[:5]
            ],
        })

    return {
        "filter": filters.meta(),
        "totals": {
            "totalBalance":       float(t_balance),
            "totalCredit":        float(t_credit),
            "totalDebit":         float(t_debit),
            "totalTransactions":  t_txcount,
            "activeAccountCount": total_accounts,
        },
        "pagination": _pagination_meta(pagination, total_accounts),
        "accounts":   summaries,
    }


async def deactivate_account(db: Prisma, account_id: str) -> None:
    acc = await db.payoneeraccount.find_unique(where={"id": account_id})
    if not acc:
        raise HTTPException(status_code=404, detail="Payoneer account not found.")
    await db.payoneeraccount.update(
        where={"id": account_id}, data={"isActive": False}
    )


# ── Transaction CRUD ──────────────────────────────────────────────────────────

async def add_transaction(db: Prisma, data: PayoneerTransactionCreate) -> dict:
    """
    Add a ledger transaction.
    Resolves account by ``data.account_name`` — staff never handle UUIDs.
    """
    account = await _resolve_account_by_name(db, data.account_name)

    tx = await db.payoneertransaction.create(
        data={
            "accountId":        account.id,
            "date":             datetime.combine(data.date, time.min),
            "details":          data.details,
            "accountFrom":      data.accountFrom,
            "accountTo":        data.accountTo,
            "debit":            data.debit,
            "credit":           data.credit,
            "remainingBalance": data.remaining_balance,
        }
    )
    return _tx_to_dict(tx, account.accountName)


async def get_account_transactions(
    db: Prisma,
    account_id: str,
    date_filter: dict,
    pagination: Optional[PageParams] = None,
) -> dict:
    """Paginated transaction list for one account — every row includes accountName."""
    account = await db.payoneeraccount.find_unique(where={"id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Payoneer account not found.")

    where: dict = {"accountId": account_id}
    if date_filter:
        where["date"] = date_filter

    total   = await db.payoneertransaction.count(where=where)
    find_kw = dict(where=where, order={"date": "desc"})
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    transactions = await db.payoneertransaction.find_many(**find_kw)

    # Current balance from latest tx across all time
    latest = await db.payoneertransaction.find_first(
        where={"accountId": account_id}, order={"date": "desc"}
    )
    current_balance = _d(latest.remainingBalance) if latest else _ZERO

    period_credit = sum((_d(t.credit) for t in transactions), _ZERO)
    period_debit  = sum((_d(t.debit)  for t in transactions), _ZERO)

    return {
        "account": {
            "id":          account.id,
            "accountName": account.accountName,
            "isActive":    account.isActive,
        },
        "currentBalance": float(current_balance),
        "periodCredit":   float(period_credit),
        "periodDebit":    float(period_debit),
        "pagination":     _pagination_meta(pagination, total),
        "transactions":   [_tx_to_dict(t, account.accountName) for t in transactions],
    }


async def delete_transaction(db: Prisma, transaction_id: str) -> None:
    tx = await db.payoneertransaction.find_unique(where={"id": transaction_id})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    await db.payoneertransaction.delete(where={"id": transaction_id})


# ── Profile-level Excel export ────────────────────────────────────────────────

async def export_account_excel(
    db: Prisma,
    account_id: str,
    filters: DateRangeFilter,
) -> tuple[bytes, str]:
    """Single-account Excel export — all transactions for the period."""
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="openpyxl not installed — cannot generate Excel export.",
        )

    detail  = await get_account_transactions(db, account_id, filters.to_prisma_filter())
    acc_name = detail["account"]["accountName"]
    start, end = filters.window()

    wb          = openpyxl.Workbook()
    HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
    HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
    ALT_FILL    = PatternFill("solid", fgColor="EBF3FB")

    def _header(ws, cols):
        for c, h in enumerate(cols, 1):
            cell = ws.cell(row=1, column=c, value=h)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 20

    def _autofit(ws):
        for col in ws.columns:
            w = max((len(str(cell.value or "")) for cell in col), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(w + 4, 40)

    ws = wb.active
    ws.title = "Transactions"
    _header(ws, [
        "Date", "Details", "Account From", "Account To",
        "Debit ($)", "Credit ($)", "Balance ($)",
    ])
    for ri, t in enumerate(detail["transactions"], 2):
        fill = ALT_FILL if ri % 2 == 0 else None
        for ci, v in enumerate([
            str(t["date"]), t["details"], t["accountFrom"] or "",
            t["accountTo"] or "", float(t["debit"]),
            float(t["credit"]), float(t["remainingBalance"]),
        ], 1):
            cell = ws.cell(row=ri, column=ci, value=v)
            if fill:
                cell.fill = fill
    _autofit(ws)

    buf      = io.BytesIO()
    wb.save(buf)
    tag      = f"{start}_{end}" if start else "all"
    filename = f"payoneer_{acc_name.replace(' ', '_')}_{tag}.xlsx"
    return buf.getvalue(), filename