"""
app/modules/pmak/service.py
════════════════════════════════════════════════════════════════════════════════
v4.2 — Bug Fix

ROOT CAUSE FIX (this version):
  PrismaError: Could not find field at `findManyPmakAccount.transactions.order`

  prisma-client-py does NOT support `order` inside a nested `include` block.
  The `order` / `order_by` key is only valid at the TOP-LEVEL `find_many`.
  Nested includes return all matching rows — sorting must be done in Python
  after the data is returned.

  REMOVED from include blocks:
    "order": {"createdAt": "desc"}   ← invalid in nested include → PrismaError

  ADDED after fetch:
    txns.sort(key=lambda t: t.createdAt, reverse=True)
    deals.sort(key=lambda d: d.createdAt, reverse=True)

SECONDARY FIX:
  Eliminated N+1 query pattern in list_accounts.
  Previously: 1 find_many + 1 find_first PER ACCOUNT for the balance lookup.
  Now: all latest transactions fetched in a single query, keyed by accountId.
════════════════════════════════════════════════════════════════════════════════
"""
import io
from datetime import date as dt_date, datetime, time
from decimal import Decimal
from typing import Optional

import openpyxl
from fastapi import HTTPException
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from prisma import Prisma

from app.shared.filters import DateRangeFilter
from app.shared.pagination import PageParams

from .schema import (
    PmakAccountCreate,
    PmakInhouseCreate,
    PmakInhouseStatusUpdate,
    PmakTransactionCreate,
    PmakTransactionStatusUpdate,
)


# ── Date helper ───────────────────────────────────────────────────────────────

def _to_dt(d: dt_date) -> datetime:
    """date → datetime midnight.  Prisma-client-py rejects bare date objects."""
    if isinstance(d, datetime):
        return d
    return datetime.combine(d, time.min)


# ── Inhouse status summary helpers ────────────────────────────────────────────

def _empty_inhouse_by_status() -> dict:
    return {
        "PENDING":     {"count": 0, "totalAmount": 0.0},
        "IN_PROGRESS": {"count": 0, "totalAmount": 0.0},
        "COMPLETED":   {"count": 0, "totalAmount": 0.0},
        "CANCELLED":   {"count": 0, "totalAmount": 0.0},
    }


def _build_inhouse_by_status(deals: list) -> dict:
    result = _empty_inhouse_by_status()
    for d in deals:
        key = d.orderStatus if isinstance(d.orderStatus, str) else d.orderStatus.value
        if key in result:
            result[key]["count"] += 1
            result[key]["totalAmount"] += float(d.orderAmount)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Accounts
# ─────────────────────────────────────────────────────────────────────────────

async def create_account(db: Prisma, data: PmakAccountCreate):
    existing = await db.pmakaccount.find_first(
        where={"accountName": {"equals": data.accountName, "mode": "insensitive"}}
    )
    if existing:
        raise HTTPException(status_code=409, detail="Account name already exists")

    account = await db.pmakaccount.create(data={"accountName": data.accountName})
    return {
        "id":                account.id,
        "accountName":       account.accountName,
        "isActive":          account.isActive,
        "currentBalance":    0.0,
        "totalTransactions": 0,
        "totalInhouse":      0,
        "inhouseByStatus":   _empty_inhouse_by_status(),
    }


async def deactivate_account(db: Prisma, account_id: str):
    account = await db.pmakaccount.find_unique(where={"id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="PMAK account not found")
    await db.pmakaccount.update(
        where={"id": account_id},
        data={"isActive": False},
    )


async def list_accounts(
    db:         Prisma,
    filters:    DateRangeFilter,
    name:       Optional[str] = None,
    pagination: PageParams = None,
):
    """
    Combined totals + paginated per-account breakdown.

    v4.2 fixes:
    1. Removed `order` from nested `include` blocks — not supported by
       prisma-client-py. Sorting is now done in Python after the fetch.
    2. Eliminated N+1 query: balance lookup is now a single query for all
       accounts, not one query per account.
    """
    date_filter = filters.to_prisma_filter()

    # ── Base where clause ─────────────────────────────────────────────────────
    where: dict = {"isActive": True}
    if name:
        where["accountName"] = {"contains": name, "mode": "insensitive"}

    # ── Total active account count (for pagination metadata) ──────────────────
    total_accounts = await db.pmakaccount.count(where=where)

    # ── Pagination ────────────────────────────────────────────────────────────
    skip = pagination.skip if pagination else 0
    take = pagination.take if pagination else 50

    # ── Build nested include where (no `order` — not supported in includes) ───
    txn_include:    dict = {}
    inhouse_include: dict = {}
    if date_filter:
        txn_include    = {"where": {"date": date_filter}}
        inhouse_include = {"where": {"date": date_filter}}

    # ── Single query: accounts + all their period transactions + inhouse deals ─
    accounts = await db.pmakaccount.find_many(
        where=where,
        skip=skip,
        take=take,
        order={"accountName": "asc"},
        include={
            "transactions": txn_include if txn_include else True,
            # FIXED: relation name is "inhouseDeals" (matches schema.prisma)
            "inhouseDeals": inhouse_include if inhouse_include else True,
        },
    )

    # ── N+1 FIX: fetch latest transaction per account in ONE query ─────────────
    # We need the most recent remainingBalance for each account (all-time, not
    # period-scoped). Instead of one find_first per account, we fetch all latest
    # transactions for all accounts on this page at once, then key by accountId.
    account_ids = [a.id for a in accounts]
    latest_balance_map: dict[str, float] = {}

    if account_ids:
        # Fetch latest transaction for each account on this page
        all_latest = await db.pmaktransaction.find_many(
            where={"accountId": {"in": account_ids}},
            order={"date": "desc"},
        )
        # Keep only the first (latest) per accountId
        for txn in all_latest:
            if txn.accountId not in latest_balance_map:
                latest_balance_map[txn.accountId] = float(txn.remainingBalance)

    # ── Build response ────────────────────────────────────────────────────────
    combined_balance      = 0.0
    combined_credit       = 0.0
    combined_debit        = 0.0
    combined_transactions = 0
    combined_inhouse      = 0
    combined_inhouse_amt  = 0.0
    combined_by_status    = _empty_inhouse_by_status()
    account_summaries     = []

    for acct in accounts:
        # Sort in Python — prisma-client-py does not support order inside include
        txns  = sorted(
            acct.transactions or [],
            key=lambda t: t.createdAt,
            reverse=True,
        )
        deals = sorted(
            acct.inhouseDeals or [],
            key=lambda d: d.createdAt,
            reverse=True,
        )

        current_balance   = latest_balance_map.get(acct.id, 0.0)
        period_credit     = sum(float(t.credit)      for t in txns)
        period_debit      = sum(float(t.debit)       for t in txns)
        inhouse_by_status = _build_inhouse_by_status(deals)
        inhouse_total_amt = sum(float(d.orderAmount) for d in deals)

        combined_balance      += current_balance
        combined_credit       += period_credit
        combined_debit        += period_debit
        combined_transactions += len(txns)
        combined_inhouse      += len(deals)
        combined_inhouse_amt  += inhouse_total_amt

        for status_key, v in inhouse_by_status.items():
            combined_by_status[status_key]["count"]       += v["count"]
            combined_by_status[status_key]["totalAmount"] += v["totalAmount"]

        account_summaries.append({
            "id":               acct.id,
            "accountName":      acct.accountName,
            "isActive":         acct.isActive,
            "currentBalance":   current_balance,
            "periodCredit":     period_credit,
            "periodDebit":      period_debit,
            "transactionCount": len(txns),
            "inhouseCount":     len(deals),
            "inhouseByStatus":  inhouse_by_status,
            # Most recent 5 — already sorted newest-first by Python sort above
            "recentTransactions": [_serialize_txn(t, acct.accountName) for t in txns[:5]],
            "recentInhouse":      [_serialize_inhouse(d, acct.accountName) for d in deals[:5]],
        })

    total_pages = max(1, -(-total_accounts // take))  # ceiling division

    return {
        "filter": filters.meta(),
        "totals": {
            "totalBalance":       combined_balance,
            "totalCredit":        combined_credit,
            "totalDebit":         combined_debit,
            "totalTransactions":  combined_transactions,
            "totalInhouse":       combined_inhouse,
            "totalInhouseAmount": combined_inhouse_amt,
            "inhouseByStatus":    combined_by_status,
            "activeAccountCount": total_accounts,
        },
        "pagination": {
            "page":       pagination.page if pagination else 1,
            "pageSize":   take,
            "total":      total_accounts,
            "totalPages": total_pages,
        },
        "accounts": account_summaries,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Ledger Transactions
# ─────────────────────────────────────────────────────────────────────────────

async def add_transaction(db: Prisma, data: PmakTransactionCreate):
    account = await db.pmakaccount.find_first(
        where={
            "accountName": {"equals": data.account_name, "mode": "insensitive"},
            "isActive":    True,
        }
    )
    if not account:
        raise HTTPException(
            status_code=404,
            detail=f"Active PMAK account '{data.account_name}' not found",
        )

    txn = await db.pmaktransaction.create(
        data={
            "date":             _to_dt(data.date),
            "details":          data.details,
            "accountFrom":      data.accountFrom,
            "accountTo":        data.accountTo,
            "debit":            data.debit,
            "credit":           data.credit,
            "remainingBalance": data.remaining_balance,
            "status":           data.status.value,
            "account":          {"connect": {"id": account.id}},
        },
    )
    return _serialize_txn(txn, account.accountName)


async def get_account_transactions(
    db:          Prisma,
    account_id:  str,
    date_filter: dict,
    pagination:  PageParams = None,
):
    account = await db.pmakaccount.find_unique(where={"id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="PMAK account not found")

    where: dict = {"accountId": account_id}
    if date_filter:
        where["date"] = date_filter

    skip = pagination.skip if pagination else 0
    take = pagination.take if pagination else 50

    total = await db.pmaktransaction.count(where=where)
    txns  = await db.pmaktransaction.find_many(
        where=where,
        order={"date": "desc"},
        skip=skip,
        take=take,
    )

    # Overall latest balance (not period-scoped)
    latest = await db.pmaktransaction.find_first(
        where={"accountId": account_id},
        order={"date": "desc"},
    )
    current_balance = float(latest.remainingBalance) if latest else 0.0
    period_credit   = sum(float(t.credit) for t in txns)
    period_debit    = sum(float(t.debit)  for t in txns)

    return {
        "account":        {
            "id":          account.id,
            "accountName": account.accountName,
            "isActive":    account.isActive,
        },
        "currentBalance": current_balance,
        "periodCredit":   period_credit,
        "periodDebit":    period_debit,
        "pagination": {
            "page":       pagination.page if pagination else 1,
            "pageSize":   take,
            "total":      total,
            "totalPages": max(1, -(-total // take)),
        },
        "transactions": [_serialize_txn(t, account.accountName) for t in txns],
    }


async def update_transaction_status(
    db:             Prisma,
    transaction_id: str,
    data:           PmakTransactionStatusUpdate,
):
    txn = await db.pmaktransaction.find_unique(where={"id": transaction_id})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    update_data: dict = {}
    if data.status is not None:
        update_data["status"] = data.status.value

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = await db.pmaktransaction.update(
        where={"id": transaction_id},
        data=update_data,
    )
    account = await db.pmakaccount.find_unique(where={"id": updated.accountId})
    return _serialize_txn(updated, account.accountName if account else "")


async def delete_transaction(db: Prisma, transaction_id: str):
    txn = await db.pmaktransaction.find_unique(where={"id": transaction_id})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.pmaktransaction.delete(where={"id": transaction_id})


# ─────────────────────────────────────────────────────────────────────────────
# Inhouse Deals
# ─────────────────────────────────────────────────────────────────────────────

async def create_inhouse_deal(db: Prisma, data: PmakInhouseCreate):
    account = await db.pmakaccount.find_first(
        where={
            "accountName": {"equals": data.account_name, "mode": "insensitive"},
            "isActive":    True,
        }
    )
    if not account:
        raise HTTPException(
            status_code=404,
            detail=f"Active PMAK account '{data.account_name}' not found",
        )

    deal = await db.pmakinhouse.create(
        data={
            "date":        _to_dt(data.date),
            "details":     data.details,
            "buyerName":   data.buyer_name,
            "sellerName":  data.seller_name,
            "orderAmount": data.order_amount,
            "orderStatus": data.order_status.value,
            "account":     {"connect": {"id": account.id}},
        },
    )
    return _serialize_inhouse(deal, account.accountName)


async def get_account_inhouse_deals(
    db:          Prisma,
    account_id:  str,
    date_filter: dict,
    pagination:  PageParams = None,
):
    account = await db.pmakaccount.find_unique(where={"id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="PMAK account not found")

    where: dict = {"accountId": account_id}
    if date_filter:
        where["date"] = date_filter

    skip = pagination.skip if pagination else 0
    take = pagination.take if pagination else 50

    total = await db.pmakinhouse.count(where=where)
    deals = await db.pmakinhouse.find_many(
        where=where,
        order={"date": "desc"},
        skip=skip,
        take=take,
    )

    inhouse_by_status = _build_inhouse_by_status(deals)
    total_amount      = sum(float(d.orderAmount) for d in deals)

    return {
        "account": {
            "id":          account.id,
            "accountName": account.accountName,
            "isActive":    account.isActive,
        },
        "inhouseByStatus": inhouse_by_status,
        "totalAmount":     total_amount,
        "pagination": {
            "page":       pagination.page if pagination else 1,
            "pageSize":   take,
            "total":      total,
            "totalPages": max(1, -(-total // take)),
        },
        "deals": [_serialize_inhouse(d, account.accountName) for d in deals],
    }


async def update_inhouse_deal(
    db:      Prisma,
    deal_id: str,
    data:    PmakInhouseStatusUpdate,
):
    deal = await db.pmakinhouse.find_unique(where={"id": deal_id})
    if not deal:
        raise HTTPException(status_code=404, detail="Inhouse deal not found")

    update_data: dict = {}
    if data.order_status is not None:
        update_data["orderStatus"] = data.order_status.value
    if data.details is not None:
        update_data["details"] = data.details

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = await db.pmakinhouse.update(
        where={"id": deal_id},
        data=update_data,
    )
    account = await db.pmakaccount.find_unique(where={"id": updated.accountId})
    return _serialize_inhouse(updated, account.accountName if account else "")


async def delete_inhouse_deal(db: Prisma, deal_id: str):
    deal = await db.pmakinhouse.find_unique(where={"id": deal_id})
    if not deal:
        raise HTTPException(status_code=404, detail="Inhouse deal not found")
    await db.pmakinhouse.delete(where={"id": deal_id})


# ─────────────────────────────────────────────────────────────────────────────
# Excel Export — single account
# ─────────────────────────────────────────────────────────────────────────────

_HEADER_FILL = PatternFill("solid", fgColor="1F3864")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_ALT_FILL    = PatternFill("solid", fgColor="DCE6F1")
_CENTER      = Alignment(horizontal="center", vertical="center")
_LEFT        = Alignment(horizontal="left",   vertical="center", wrap_text=True)


def _apply_header(ws, headers: list[str], col_widths: list[int]) -> None:
    ws.row_dimensions[1].height = 22
    for idx, (h, w) in enumerate(zip(headers, col_widths), start=1):
        cell           = ws.cell(row=1, column=idx, value=h)
        cell.font      = _HEADER_FONT
        cell.fill      = _HEADER_FILL
        cell.alignment = _CENTER
        ws.column_dimensions[get_column_letter(idx)].width = w


async def export_account_excel(
    db:         Prisma,
    account_id: str,
    filters:    DateRangeFilter,
) -> tuple[bytes, str]:
    """Two-sheet workbook: Ledger + Inhouse Deals."""
    account = await db.pmakaccount.find_unique(where={"id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="PMAK account not found")

    date_filter = filters.to_prisma_filter()
    txn_where:  dict = {"accountId": account_id}
    deal_where: dict = {"accountId": account_id}
    if date_filter:
        txn_where["date"]  = date_filter
        deal_where["date"] = date_filter

    txns  = await db.pmaktransaction.find_many(where=txn_where,  order={"date": "asc"})
    deals = await db.pmakinhouse.find_many(    where=deal_where, order={"date": "asc"})

    wb  = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Ledger"
    _apply_header(ws1, [
        "Date", "Details", "Account From", "Account To",
        "Debit", "Credit", "Balance", "Status",
    ], [12, 36, 20, 20, 12, 12, 14, 12])

    for row_idx, t in enumerate(txns, start=2):
        fill = _ALT_FILL if row_idx % 2 == 0 else None
        vals = [
            t.date.date().isoformat() if hasattr(t.date, "date") else str(t.date),
            t.details or "",
            t.accountFrom or "",
            t.accountTo   or "",
            float(t.debit),
            float(t.credit),
            float(t.remainingBalance),
            t.status if isinstance(t.status, str) else t.status.value,
        ]
        for col_idx, val in enumerate(vals, start=1):
            cell           = ws1.cell(row=row_idx, column=col_idx, value=val)
            cell.alignment = _CENTER if col_idx in (1, 5, 6, 7, 8) else _LEFT
            if fill:
                cell.fill = fill
    ws1.freeze_panes = "A2"

    ws2 = wb.create_sheet("Inhouse Deals")
    _apply_header(ws2, [
        "Date", "Buyer", "Seller", "Amount", "Status", "Details",
    ], [12, 24, 24, 14, 14, 40])

    for row_idx, d in enumerate(deals, start=2):
        fill = _ALT_FILL if row_idx % 2 == 0 else None
        vals = [
            d.date.date().isoformat() if hasattr(d.date, "date") else str(d.date),
            d.buyerName,
            d.sellerName,
            float(d.orderAmount),
            d.orderStatus if isinstance(d.orderStatus, str) else d.orderStatus.value,
            d.details or "",
        ]
        for col_idx, val in enumerate(vals, start=1):
            cell           = ws2.cell(row=row_idx, column=col_idx, value=val)
            cell.alignment = _CENTER if col_idx in (1, 4, 5) else _LEFT
            if fill:
                cell.fill = fill
    ws2.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    safe_name = account.accountName.replace(" ", "_").replace("/", "-")
    period    = filters.meta()["dateRange"]["from"] or "all"
    filename  = f"pmak_{safe_name}_{period}.xlsx"
    return buffer.read(), filename


# ─────────────────────────────────────────────────────────────────────────────
# Internal serialisers
# ─────────────────────────────────────────────────────────────────────────────

def _serialize_txn(txn, account_name: str) -> dict:
    return {
        "id":               txn.id,
        "accountId":        txn.accountId,
        "accountName":      account_name,
        "date":             txn.date.date() if hasattr(txn.date, "date") else txn.date,
        "details":          txn.details,
        "accountFrom":      txn.accountFrom,
        "accountTo":        txn.accountTo,
        "debit":            txn.debit,
        "credit":           txn.credit,
        "remainingBalance": txn.remainingBalance,
        "status":           txn.status if isinstance(txn.status, str) else txn.status.value,
        "createdAt":        txn.createdAt,
    }


def _serialize_inhouse(deal, account_name: str) -> dict:
    return {
        "id":          deal.id,
        "accountId":   deal.accountId,
        "accountName": account_name,
        "date":        deal.date.date() if hasattr(deal.date, "date") else deal.date,
        "details":     deal.details,
        "buyerName":   deal.buyerName,
        "sellerName":  deal.sellerName,
        "orderAmount": deal.orderAmount,
        "orderStatus": deal.orderStatus if isinstance(deal.orderStatus, str) else deal.orderStatus.value,
        "createdAt":   deal.createdAt,
        "updatedAt":   deal.updatedAt,
    }