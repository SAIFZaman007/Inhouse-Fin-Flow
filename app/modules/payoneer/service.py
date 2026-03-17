"""
app/modules/payoneer/service.py
════════════════════════════════════════════════════════════════════════════════
v4 — Enterprise Edition

Changes vs v3
─────────────
update_account      EXTENDED — PATCH /accounts/{id}
                      Now handles ``description``, ``initial_balance``, and
                      ``opening_note`` from PayoneerAccountUpdate.
                      When ``initial_balance`` is supplied the service appends a
                      credit transaction immediately — no separate POST
                      /transactions call required.
                      ``description`` is stored in the new transaction's
                      ``details`` field (if ``initial_balance`` is also given)
                      or acknowledged in the response even without a transaction.

update_transaction  FIXED — ``date`` is now Optional in the schema (v4).
                      The guard `if data.date is not None` was already present
                      in v3 so no logic change is needed here; the fix is purely
                      in the schema layer.

Everything else is unchanged from v3.
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
    PayoneerAccountUpdate,
    PayoneerTransactionCreate,
    PayoneerTransactionUpdate,
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


async def _get_account_or_404(db: Prisma, account_id: str):
    account = await db.payoneeraccount.find_unique(where={"id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Payoneer account not found.")
    return account


async def _get_transaction_or_404(db: Prisma, transaction_id: str):
    tx = await db.payoneertransaction.find_unique(where={"id": transaction_id})
    if not tx:
        raise HTTPException(status_code=404, detail="Payoneer transaction not found.")
    return tx


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


async def update_account(
    db: Prisma,
    account_id: str,
    data: PayoneerAccountUpdate,
) -> dict:
    """
    PATCH /accounts/{id} — partial account update (v4).

    Handles two independent concerns in one call:

    1. Account metadata  — rename (with uniqueness check) and/or isActive toggle.
    2. Balance adjustment — if ``initial_balance`` is supplied, a new credit
       transaction is appended to the ledger with the supplied (or default)
       ``opening_note`` as its details text.

    ``description`` is stored in the adjustment transaction's ``details`` field
    when ``initial_balance`` is also provided; otherwise it is returned in the
    response as an acknowledged note (the schema has no dedicated DB column for
    account-level description — the transaction ledger is the source of truth).

    Returns the updated account dict plus the adjustment transaction (if any).
    """
    account = await _get_account_or_404(db, account_id)

    # ── 1. Account metadata patch ─────────────────────────────────────────────
    account_patch: dict = {}

    if data.accountName is not None and data.accountName != account.accountName:
        conflict = await db.payoneeraccount.find_first(
            where={
                "accountName": {"equals": data.accountName, "mode": "insensitive"},
                "id":          {"not": account_id},
            }
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Account name '{data.accountName}' is already taken.",
            )
        account_patch["accountName"] = data.accountName

    if data.isActive is not None:
        account_patch["isActive"] = data.isActive

    if account_patch:
        account = await db.payoneeraccount.update(
            where={"id": account_id},
            data=account_patch,
        )

    # ── 2. Balance-adjustment transaction (v4) ────────────────────────────────
    adjustment_tx: Optional[dict] = None

    if data.initial_balance is not None and data.initial_balance > 0:
        # Determine the running balance to use as the new remainingBalance.
        # We take the latest transaction's remainingBalance and add the credit.
        latest_tx = await db.payoneertransaction.find_first(
            where={"accountId": account_id},
            order={"date": "desc"},
        )
        current_balance = _d(latest_tx.remainingBalance) if latest_tx else _ZERO
        new_balance     = current_balance + data.initial_balance

        # Build the details string — prefer explicit description over opening_note
        details_text = (
            data.description
            or data.opening_note
            or "Balance adjustment"
        )

        tx = await db.payoneertransaction.create(
            data={
                "accountId":        account_id,
                "date":             datetime.combine(date.today(), time.min),
                "details":          details_text,
                "accountFrom":      None,
                "accountTo":        account.accountName,
                "debit":            _ZERO,
                "credit":           data.initial_balance,
                "remainingBalance": new_balance,
            }
        )
        adjustment_tx = _tx_to_dict(tx, account.accountName)

    return {
        "id":                   account.id,
        "accountName":          account.accountName,
        "isActive":             account.isActive,
        # Echo back description so the caller can confirm it was received,
        # even when no transaction was created.
        "description":          data.description,
        "adjustmentTransaction": adjustment_tx,
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
    )
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    accounts = await db.payoneeraccount.find_many(**find_kw)

    t_balance = t_credit = t_debit = _ZERO
    t_txcount  = 0
    summaries  = []

    for acc in accounts:
        # Latest balance across ALL time (not filtered)
        latest_tx = await db.payoneertransaction.find_first(
            where={"accountId": acc.id}, order={"date": "desc"}
        )
        current_balance = _d(latest_tx.remainingBalance) if latest_tx else _ZERO
        t_balance      += current_balance

        period_credit = sum((_d(t.credit) for t in acc.transactions), _ZERO)
        period_debit  = sum((_d(t.debit)  for t in acc.transactions), _ZERO)
        t_credit      += period_credit
        t_debit       += period_debit
        t_txcount     += len(acc.transactions)

        summaries.append({
            "id":                acc.id,
            "accountName":       acc.accountName,
            "isActive":          acc.isActive,
            "currentBalance":    float(current_balance),
            "periodCredit":      float(period_credit),
            "periodDebit":       float(period_debit),
            "transactionCount":  len(acc.transactions),
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


async def update_transaction(
    db: Prisma,
    transaction_id: str,
    data: PayoneerTransactionUpdate,
) -> dict:
    """
    PATCH /transactions/{id} — partial transaction update.

    • All fields are optional; only supplied ones are written.
    • remainingBalance is updated only when explicitly provided — the system
      does NOT auto-recompute it (ledger integrity is the caller's responsibility,
      mirroring the POST contract).
    • Returns the updated full transaction dict (with accountName).
    """
    tx      = await _get_transaction_or_404(db, transaction_id)
    account = await _get_account_or_404(db, tx.accountId)

    patch: dict = {}

    if data.date is not None:
        patch["date"] = datetime.combine(data.date, time.min)

    if data.details is not None:
        patch["details"] = data.details

    # accountFrom / accountTo: distinguish "not supplied" from "explicitly cleared"
    # Pydantic v2 passes None for both cases with Optional fields, so we rely on
    # model_fields_set to detect which keys the caller actually sent.
    sent = data.model_fields_set

    if "accountFrom" in sent:
        patch["accountFrom"] = data.accountFrom   # may be None → explicit clear

    if "accountTo" in sent:
        patch["accountTo"] = data.accountTo        # may be None → explicit clear

    if data.debit is not None:
        patch["debit"] = data.debit

    if data.credit is not None:
        patch["credit"] = data.credit

    if data.remaining_balance is not None:
        patch["remainingBalance"] = data.remaining_balance

    if not patch:
        return _tx_to_dict(tx, account.accountName)

    updated = await db.payoneertransaction.update(
        where={"id": transaction_id},
        data=patch,
    )
    return _tx_to_dict(updated, account.accountName)


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

    detail   = await get_account_transactions(db, account_id, filters.to_prisma_filter())
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