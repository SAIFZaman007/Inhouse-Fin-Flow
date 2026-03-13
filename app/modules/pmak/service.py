"""
app/modules/pmak/service.py
════════════════════════════════════════════════════════════════════════════════
v4 — Enterprise Edition

Changes vs v3
─────────────
_resolve_account_by_name  NEW — case-insensitive account lookup by name.
_tx_to_dict               NEW — serialises a transaction row + accountName.
_inhouse_to_dict          NEW — serialises an inhouse row + accountName.
_inhouse_status_summary   NEW — builds the {PENDING, IN_PROGRESS, COMPLETED,
                                 CANCELLED} breakdown dict.
add_transaction           Resolves account via ``data.account_name`` (not id).
create_inhouse_deal       Resolves account via ``data.account_name`` (not id).
list_accounts             Combined totals including inhouse breakdown; period +
                          name filter + pagination.
get_account_transactions  Paginated, includes accountName per row.
get_account_inhouse_deals Paginated, includes accountName per row + status summary.

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

from app.shared.constants import InhouseOrderStatus
from app.shared.filters import DateRangeFilter, to_dt_start, to_dt_end
from app.shared.pagination import PageParams
from .schema import (
    PmakAccountCreate,
    PmakInhouseCreate, PmakInhouseStatusUpdate,
    PmakTransactionCreate, PmakTransactionStatusUpdate,
)

logger = logging.getLogger(__name__)
_ZERO = Decimal("0")

# All InhouseOrderStatus values, in display order
_INHOUSE_STATUSES = [
    InhouseOrderStatus.PENDING,
    InhouseOrderStatus.IN_PROGRESS,
    InhouseOrderStatus.COMPLETED,
    InhouseOrderStatus.CANCELLED,
]


# ── Private helpers ───────────────────────────────────────────────────────────

def _d(v: Any) -> Decimal:
    return _ZERO if v is None else Decimal(str(v))


def _tx_to_dict(tx: Any, account_name: str) -> dict:
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
        "status":           tx.status,
        "createdAt":        tx.createdAt,
    }


def _inhouse_to_dict(deal: Any, account_name: str) -> dict:
    return {
        "id":          deal.id,
        "accountId":   deal.accountId,
        "accountName": account_name,
        "date":        deal.date.date() if isinstance(deal.date, datetime) else deal.date,
        "details":     deal.details,
        "buyerName":   deal.buyerName,
        "sellerName":  deal.sellerName,
        "orderAmount": _d(deal.orderAmount),
        "orderStatus": deal.orderStatus,
        "createdAt":   deal.createdAt,
        "updatedAt":   deal.updatedAt,
    }


def _inhouse_status_summary(deals: list) -> dict:
    """Build {PENDING: {count, totalAmount}, IN_PROGRESS: ..., ...} dict."""
    summary: dict = {
        s.value: {"count": 0, "totalAmount": float(_ZERO)}
        for s in _INHOUSE_STATUSES
    }
    for deal in deals:
        key = deal.orderStatus if isinstance(deal.orderStatus, str) else deal.orderStatus.value
        if key in summary:
            summary[key]["count"]       += 1
            summary[key]["totalAmount"] += float(_d(deal.orderAmount))
    return summary


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
    Return the active PmakAccount whose name matches ``account_name``
    (case-insensitive).  Raises HTTP 404 if not found.
    """
    account = await db.pmakaccount.find_first(
        where={
            "accountName": {"equals": account_name, "mode": "insensitive"},
            "isActive":    True,
        }
    )
    if not account:
        raise HTTPException(
            status_code=404,
            detail=f"PMAK account '{account_name}' not found.",
        )
    return account


# ── Account CRUD ──────────────────────────────────────────────────────────────

async def create_account(db: Prisma, data: PmakAccountCreate) -> dict:
    existing = await db.pmakaccount.find_unique(where={"accountName": data.accountName})
    if existing:
        raise HTTPException(status_code=409, detail="Account name already exists.")
    account = await db.pmakaccount.create(data={"accountName": data.accountName})
    return {
        "id":                account.id,
        "accountName":       account.accountName,
        "isActive":          account.isActive,
        "currentBalance":    0.0,
        "totalTransactions": 0,
        "totalInhouse":      0,
        "inhouseByStatus":   _inhouse_status_summary([]),
    }


async def list_accounts(
    db: Prisma,
    filters: DateRangeFilter,
    name: Optional[str] = None,
    pagination: Optional[PageParams] = None,
) -> dict:
    """
    Combined totals (ledger + inhouse) + paginated per-account breakdown.
    ``name`` performs case-insensitive partial search on accountName.
    """
    date_f = filters.to_prisma_filter()

    where: dict = {"isActive": True}
    if name:
        where["accountName"] = {"contains": name, "mode": "insensitive"}

    total_accounts = await db.pmakaccount.count(where=where)

    find_kw: dict = dict(
        where=where,
        include={
            "transactions": {
                "where":    {"date": date_f} if date_f else {},
                "order_by": {"date": "desc"},
            },
            "inhouse": {
                "where":    {"date": date_f} if date_f else {},
                "order_by": {"date": "desc"},
            },
        },
        order={"accountName": "asc"},
    )
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    accounts = await db.pmakaccount.find_many(**find_kw)

    # ── Cross-account accumulators ────────────────────────────────────────────
    t_balance    = _ZERO
    t_credit     = _ZERO
    t_debit      = _ZERO
    t_tx_count   = 0
    t_inhouse    = 0
    t_inh_amount = _ZERO
    t_inh_status: dict = {s.value: {"count": 0, "totalAmount": 0.0} for s in _INHOUSE_STATUSES}

    summaries = []
    for acc in accounts:
        latest_tx = await db.pmaktransaction.find_first(
            where={"accountId": acc.id}, order={"date": "desc"}
        )
        current_balance = _d(latest_tx.remainingBalance) if latest_tx else _ZERO

        period_credit = sum((_d(t.credit) for t in acc.transactions), _ZERO)
        period_debit  = sum((_d(t.debit)  for t in acc.transactions), _ZERO)
        inh_summary   = _inhouse_status_summary(acc.inhouse)
        inh_amount    = sum((_d(d.orderAmount) for d in acc.inhouse), _ZERO)

        t_balance    += current_balance
        t_credit     += period_credit
        t_debit      += period_debit
        t_tx_count   += len(acc.transactions)
        t_inhouse    += len(acc.inhouse)
        t_inh_amount += inh_amount
        for s_key, val in inh_summary.items():
            t_inh_status[s_key]["count"]       += val["count"]
            t_inh_status[s_key]["totalAmount"] += val["totalAmount"]

        summaries.append({
            "id":                acc.id,
            "accountName":       acc.accountName,
            "isActive":          acc.isActive,
            "currentBalance":    float(current_balance),
            "periodCredit":      float(period_credit),
            "periodDebit":       float(period_debit),
            "transactionCount":  len(acc.transactions),
            "inhouseCount":      len(acc.inhouse),
            "inhouseByStatus":   inh_summary,
            "recentTransactions": [_tx_to_dict(t, acc.accountName) for t in acc.transactions[:5]],
            "recentInhouse":      [_inhouse_to_dict(d, acc.accountName) for d in acc.inhouse[:5]],
        })

    return {
        "filter": filters.meta(),
        "totals": {
            "totalBalance":       float(t_balance),
            "totalCredit":        float(t_credit),
            "totalDebit":         float(t_debit),
            "totalTransactions":  t_tx_count,
            "totalInhouse":       t_inhouse,
            "totalInhouseAmount": float(t_inh_amount),
            "inhouseByStatus":    t_inh_status,
            "activeAccountCount": total_accounts,
        },
        "pagination": _pagination_meta(pagination, total_accounts),
        "accounts":   summaries,
    }


async def deactivate_account(db: Prisma, account_id: str) -> None:
    acc = await db.pmakaccount.find_unique(where={"id": account_id})
    if not acc:
        raise HTTPException(status_code=404, detail="PMAK account not found.")
    await db.pmakaccount.update(where={"id": account_id}, data={"isActive": False})


# ── Ledger Transaction CRUD ───────────────────────────────────────────────────

async def add_transaction(db: Prisma, data: PmakTransactionCreate) -> dict:
    """
    Add a ledger transaction.
    Resolves account by ``data.account_name`` — staff never handle UUIDs.
    """
    account = await _resolve_account_by_name(db, data.account_name)

    tx = await db.pmaktransaction.create(
        data={
            "accountId":        account.id,
            "date":             datetime.combine(data.date, time.min),
            "details":          data.details,
            "accountFrom":      data.accountFrom,
            "accountTo":        data.accountTo,
            "debit":            data.debit,
            "credit":           data.credit,
            "remainingBalance": data.remaining_balance,
            "status":           data.status,
        }
    )
    return _tx_to_dict(tx, account.accountName)


async def update_transaction_status(
    db: Prisma,
    transaction_id: str,
    data: PmakTransactionStatusUpdate,
) -> dict:
    """Restricted PATCH — only ``status`` is touched. Safe for BDev role."""
    tx = await db.pmaktransaction.find_unique(where={"id": transaction_id})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    if data.status is None:
        raise HTTPException(status_code=400, detail="No fields to update.")

    updated = await db.pmaktransaction.update(
        where={"id": transaction_id},
        data={"status": data.status},
    )
    # Fetch account name for the response
    account = await db.pmakaccount.find_unique(where={"id": updated.accountId})
    acc_name = account.accountName if account else ""
    return _tx_to_dict(updated, acc_name)


async def get_account_transactions(
    db: Prisma,
    account_id: str,
    date_filter: dict,
    pagination: Optional[PageParams] = None,
) -> dict:
    """Paginated ledger transactions — every row includes ``accountName``."""
    account = await db.pmakaccount.find_unique(where={"id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="PMAK account not found.")

    where: dict = {"accountId": account_id}
    if date_filter:
        where["date"] = date_filter

    total   = await db.pmaktransaction.count(where=where)
    find_kw = dict(where=where, order={"date": "desc"})
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    transactions = await db.pmaktransaction.find_many(**find_kw)

    latest = await db.pmaktransaction.find_first(
        where={"accountId": account_id}, order={"date": "desc"}
    )
    current_balance = _d(latest.remainingBalance) if latest else _ZERO
    period_credit   = sum((_d(t.credit) for t in transactions), _ZERO)
    period_debit    = sum((_d(t.debit)  for t in transactions), _ZERO)

    return {
        "account":      {"id": account.id, "accountName": account.accountName, "isActive": account.isActive},
        "currentBalance": float(current_balance),
        "periodCredit":   float(period_credit),
        "periodDebit":    float(period_debit),
        "pagination":     _pagination_meta(pagination, total),
        "transactions":   [_tx_to_dict(t, account.accountName) for t in transactions],
    }


async def delete_transaction(db: Prisma, transaction_id: str) -> None:
    tx = await db.pmaktransaction.find_unique(where={"id": transaction_id})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    await db.pmaktransaction.delete(where={"id": transaction_id})


# ── Inhouse Deal CRUD ─────────────────────────────────────────────────────────

async def create_inhouse_deal(db: Prisma, data: PmakInhouseCreate) -> dict:
    """
    Create an inhouse deal.
    Resolves account by ``data.account_name`` — staff never handle UUIDs.
    """
    account = await _resolve_account_by_name(db, data.account_name)

    deal = await db.pmakinhouse.create(
        data={
            "accountId":   account.id,
            "date":        datetime.combine(data.date, time.min),
            "details":     data.details,
            "buyerName":   data.buyer_name,
            "sellerName":  data.seller_name,
            "orderAmount": data.order_amount,
            "orderStatus": data.order_status,
        }
    )
    return _inhouse_to_dict(deal, account.accountName)


async def update_inhouse_deal(
    db: Prisma,
    deal_id: str,
    data: PmakInhouseStatusUpdate,
) -> dict:
    deal = await db.pmakinhouse.find_unique(where={"id": deal_id})
    if not deal:
        raise HTTPException(status_code=404, detail="Inhouse deal not found.")

    update_data: dict = {}
    if data.order_status is not None:
        update_data["orderStatus"] = data.order_status
    if data.details is not None:
        update_data["details"] = data.details
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    updated = await db.pmakinhouse.update(where={"id": deal_id}, data=update_data)
    account = await db.pmakaccount.find_unique(where={"id": updated.accountId})
    acc_name = account.accountName if account else ""
    return _inhouse_to_dict(updated, acc_name)


async def get_account_inhouse_deals(
    db: Prisma,
    account_id: str,
    date_filter: dict,
    pagination: Optional[PageParams] = None,
) -> dict:
    """Paginated inhouse deals — every row includes ``accountName`` + status summary."""
    account = await db.pmakaccount.find_unique(where={"id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="PMAK account not found.")

    where: dict = {"accountId": account_id}
    if date_filter:
        where["date"] = date_filter

    total   = await db.pmakinhouse.count(where=where)
    find_kw = dict(where=where, order={"date": "desc"})
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    deals        = await db.pmakinhouse.find_many(**find_kw)
    all_deals    = await db.pmakinhouse.find_many(where=where)   # for status summary (all pages)
    inh_summary  = _inhouse_status_summary(all_deals)
    total_amount = sum((_d(d.orderAmount) for d in all_deals), _ZERO)

    return {
        "account":       {"id": account.id, "accountName": account.accountName, "isActive": account.isActive},
        "inhouseByStatus": inh_summary,
        "totalAmount":   float(total_amount),
        "pagination":    _pagination_meta(pagination, total),
        "deals":         [_inhouse_to_dict(d, account.accountName) for d in deals],
    }


async def delete_inhouse_deal(db: Prisma, deal_id: str) -> None:
    deal = await db.pmakinhouse.find_unique(where={"id": deal_id})
    if not deal:
        raise HTTPException(status_code=404, detail="Inhouse deal not found.")
    await db.pmakinhouse.delete(where={"id": deal_id})


# ── Profile-level Excel export ────────────────────────────────────────────────

async def export_account_excel(
    db: Prisma,
    account_id: str,
    filters: DateRangeFilter,
) -> tuple[bytes, str]:
    """Two-sheet Excel: Sheet 1 = Ledger Transactions, Sheet 2 = Inhouse Deals."""
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="openpyxl not installed — cannot generate Excel export.",
        )

    tx_data  = await get_account_transactions(db, account_id, filters.to_prisma_filter())
    inh_data = await get_account_inhouse_deals(db, account_id, filters.to_prisma_filter())
    acc_name = tx_data["account"]["accountName"]
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

    # Sheet 1 — Ledger
    ws1 = wb.active
    ws1.title = "Ledger"
    _header(ws1, ["Date", "Details", "Account From", "Account To",
                  "Debit ($)", "Credit ($)", "Balance ($)", "Status"])
    for ri, t in enumerate(tx_data["transactions"], 2):
        fill = ALT_FILL if ri % 2 == 0 else None
        for ci, v in enumerate([
            str(t["date"]), t["details"], t["accountFrom"] or "",
            t["accountTo"] or "", float(t["debit"]),
            float(t["credit"]), float(t["remainingBalance"]),
            t["status"],
        ], 1):
            cell = ws1.cell(row=ri, column=ci, value=v)
            if fill:
                cell.fill = fill
    _autofit(ws1)

    # Sheet 2 — Inhouse
    ws2 = wb.create_sheet("Inhouse")
    _header(ws2, ["Date", "Buyer", "Seller", "Amount ($)", "Status", "Details"])
    for ri, d in enumerate(inh_data["deals"], 2):
        fill = ALT_FILL if ri % 2 == 0 else None
        for ci, v in enumerate([
            str(d["date"]), d["buyerName"], d["sellerName"],
            float(d["orderAmount"]), d["orderStatus"], d["details"] or "",
        ], 1):
            cell = ws2.cell(row=ri, column=ci, value=v)
            if fill:
                cell.fill = fill
    _autofit(ws2)

    buf      = io.BytesIO()
    wb.save(buf)
    tag      = f"{start}_{end}" if start else "all"
    filename = f"pmak_{acc_name.replace(' ', '_')}_{tag}.xlsx"
    return buf.getvalue(), filename