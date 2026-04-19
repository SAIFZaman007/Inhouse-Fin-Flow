"""
app/modules/pmak/service.py
════════════════════════════════════════════════════════════════════════════════
v6.3 — Enterprise Edition
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
    PmakInhouseFullUpdate,
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


def _serialize_inhouse_with_account(d) -> dict:
    """Serialise a PmakInhouse row that was fetched with include={"account": True}."""
    return {
        "id":          d.id,
        "accountId":   d.accountId,
        "accountName": d.account.accountName if d.account else "",
        "date":        d.date.date() if hasattr(d.date, "date") else d.date,
        "details":     d.details,
        "buyerName":   d.buyerName,
        "sellerName":  d.sellerName,
        "orderAmount": d.orderAmount,
        "orderStatus": d.orderStatus if isinstance(d.orderStatus, str) else d.orderStatus.value,
        "createdAt":   d.createdAt,
        "updatedAt":   d.updatedAt,
    }


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
    """
    date_filter = filters.to_prisma_filter()

    where: dict = {"isActive": True}
    if name:
        where["accountName"] = {"contains": name, "mode": "insensitive"}

    total_accounts = await db.pmakaccount.count(where=where)

    skip = pagination.skip if pagination else 0
    take = pagination.take if pagination else 50

    txn_include:     dict = {}
    inhouse_include: dict = {}
    if date_filter:
        txn_include     = {"where": {"date": date_filter}}
        inhouse_include = {"where": {"date": date_filter}}

    accounts = await db.pmakaccount.find_many(
        where=where,
        skip=skip,
        take=take,
        order={"accountName": "asc"},
        include={
            "transactions": txn_include if txn_include else True,
            "inhouseDeals": inhouse_include if inhouse_include else True,
        },
    )

    # ── Latest stored balance per account (single query, no N+1) ─────────────
    # Order by createdAt DESC — date is @db.Date (day-level only) and cannot
    # break ties between same-day transactions. createdAt is a full-precision
    # timestamp that always identifies the true latest row per account.
    account_ids = [a.id for a in accounts]
    latest_balance_map: dict[str, float] = {}
    if account_ids:
        all_latest = await db.pmaktransaction.find_many(
            where={"accountId": {"in": account_ids}},
            order={"createdAt": "desc"},
        )
        for txn in all_latest:
            if txn.accountId not in latest_balance_map:
                latest_balance_map[txn.accountId] = float(txn.remainingBalance)

    # ── All-time inhouse order totals per account (single query, no N+1) ─────
    # Not period-scoped — we want the lifetime deal volume per account for the
    # accounts table column (totalInhouseOrderAmount).
    all_time_inhouse_map: dict[str, float] = {}
    if account_ids:
        all_inhouse = await db.pmakinhouse.find_many(
            where={"accountId": {"in": account_ids}},
        )
        for deal in all_inhouse:
            all_time_inhouse_map[deal.accountId] = (
                all_time_inhouse_map.get(deal.accountId, 0.0) + float(deal.orderAmount)
            )

    combined_balance      = 0.0
    combined_credit       = 0.0
    combined_debit        = 0.0
    combined_transactions = 0
    combined_inhouse      = 0
    combined_inhouse_amt  = 0.0
    combined_by_status    = _empty_inhouse_by_status()
    account_summaries     = []

    for acct in accounts:
        txns  = sorted(acct.transactions or [], key=lambda t: t.createdAt, reverse=True)
        deals = sorted(acct.inhouseDeals or [], key=lambda d: d.createdAt, reverse=True)

        # currentBalance = remainingBalance of the most recent transaction.
        # That stored value already IS the running total (computed at write-time as
        # previous_balance − debit + credit). Adding period figures again would
        # double-count them. Zero is the correct default when no transactions exist.
        latest_stored_balance = latest_balance_map.get(acct.id, 0.0)
        period_credit         = sum(float(t.credit) for t in txns)
        period_debit          = sum(float(t.debit)  for t in txns)
        current_balance       = round(latest_stored_balance, 2)

        inhouse_by_status        = _build_inhouse_by_status(deals)
        inhouse_total_amt        = sum(float(d.orderAmount) for d in deals)
        total_inhouse_order_amt  = round(all_time_inhouse_map.get(acct.id, 0.0), 2)

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
            "id":                      acct.id,
            "accountName":             acct.accountName,
            "isActive":                acct.isActive,
            "currentBalance":          current_balance,
            "periodCredit":            period_credit,
            "periodDebit":             period_debit,
            "transactionCount":        len(txns),
            "inhouseCount":            len(deals),
            "totalInhouseOrderAmount": total_inhouse_order_amt,   # ← NEW
            "inhouseByStatus":         inhouse_by_status,
            "recentTransactions": [_serialize_txn(t, acct.accountName) for t in txns[:5]],
            "recentInhouse":      [_serialize_inhouse(d, acct.accountName) for d in deals[:5]],
        })

    total_pages = max(1, -(-total_accounts // take))

    return {
        "filter": filters.meta(),
        "totals": {
            "totalBalance":       round(combined_balance, 2),
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
    """
    POST /transactions — Add a ledger entry.

    remainingBalance is auto-computed server-side:
      latest_balance − debit + credit

    The latest balance is resolved by ordering on (createdAt DESC) so that
    same-day transactions are always sequenced correctly — `date` is a
    @db.Date (day-level precision) and cannot break ties on its own.

    [FIX-C] The caller may pass `remaining_balance` explicitly to override the
    auto-computed value (e.g. for manual balance corrections), BUT only a
    non-zero, non-None value is treated as a deliberate override.  A value of
    exactly 0 is interpreted as "not provided" — this prevents tools like
    Swagger UI from accidentally short-circuiting the auto-computation when
    they echo back the field's numeric default (0) in the request body.

    Three-layer defence ensures the response always matches the DB:
      1. computed_balance written to the DB via create()
      2. Transaction re-fetched via find_unique() after create()
      3. computed_balance injected directly into the response dict
    """
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

    # ── Resolve the latest stored balance (createdAt tiebreaker) ─────────────
    # `date` is @db.Date — day-level only. Multiple transactions on the same
    # calendar day would be indistinguishable without the createdAt tiebreaker.
    latest_txn = await db.pmaktransaction.find_first(
        where={"accountId": account.id},
        order={"createdAt": "desc"},
    )
    latest_balance = float(latest_txn.remainingBalance) if latest_txn else 0.0

    # ── Compute remainingBalance; honour caller override only when non-zero ───
    caller_override = (
        data.remaining_balance is not None
        and data.remaining_balance != Decimal("0")
    )

    if caller_override:
        computed_balance = Decimal(str(data.remaining_balance))
    else:
        computed_balance = Decimal(str(round(
            latest_balance - float(data.debit) + float(data.credit), 2
        )))

    # ── Persist ───────────────────────────────────────────────────────────────
    txn = await db.pmaktransaction.create(
        data={
            "date":             _to_dt(data.date),
            "details":          data.details,
            "accountFrom":      data.accountFrom,
            "accountTo":        data.accountTo,
            "debit":            data.debit,
            "credit":           data.credit,
            "remainingBalance": computed_balance,
            "status":           data.status.value,
            "account":          {"connect": {"id": account.id}},
        },
    )

    # ── Re-fetch to get the exact persisted DB state (belt-and-suspenders) ───
    # Prisma's create() return object can have ORM-coercion artefacts on Decimal
    # fields.  A find_unique() immediately after the write guarantees we read
    # exactly what was committed to the database.
    persisted_txn = await db.pmaktransaction.find_unique(where={"id": txn.id})

    # ── Serialise; inject computed_balance as the authoritative balance ───────
    # Three-layer defence: DB write (computed_balance) → re-fetch → override.
    # The override is the final safety net in case of any ORM round-trip delta.
    response = _serialize_txn(persisted_txn, account.accountName)
    response["remainingBalance"] = computed_balance
    return response


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

    # Dynamic balance — same formula as list_accounts [FIX-1]
    # Order by createdAt DESC (not date DESC) to correctly resolve the latest
    # row when multiple transactions share the same calendar day.
    latest = await db.pmaktransaction.find_first(
        where={"accountId": account_id},
        order={"createdAt": "desc"},
    )
    # currentBalance = remainingBalance of the most recent transaction.
    # That stored value was written as: previous_balance − debit + credit, so it
    # already IS the full running total. Re-applying period figures would double-count.
    latest_stored   = float(latest.remainingBalance) if latest else 0.0
    period_credit   = sum(float(t.credit) for t in txns)
    period_debit    = sum(float(t.debit)  for t in txns)
    current_balance = round(latest_stored, 2)

    return {
        "account":        {"id": account.id, "accountName": account.accountName, "isActive": account.isActive},
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
# Inhouse Deals — per-account
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
        "account":         {"id": account.id, "accountName": account.accountName, "isActive": account.isActive},
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


# ─────────────────────────────────────────────────────────────────────────────
# Inhouse Deals — ALL accounts (GET /pmak/inhouse)
# ─────────────────────────────────────────────────────────────────────────────

async def list_all_inhouse_deals(
    db:           Prisma,
    filters:      DateRangeFilter,
    pagination:   PageParams,
    account_name: Optional[str] = None,
    buyer_name:   Optional[str] = None,
    seller_name:  Optional[str] = None,
    order_status: Optional[str] = None,
):
    """
    Cross-account flat deal list with combined totals.

    Returns:
      filter    — period metadata
      totals    — totalDeals, totalAmount, byStatus (all 4 statuses with count + totalAmount)
      pagination — page, pageSize, total, totalPages
      deals     — paginated flat list, each row includes accountName

    Filters (all combinable):
      account_name  — case-insensitive substring on PmakAccount.accountName
      buyer_name    — case-insensitive substring on PmakInhouse.buyerName
      seller_name   — case-insensitive substring on PmakInhouse.sellerName
      order_status  — exact enum: PENDING | IN_PROGRESS | COMPLETED | CANCELLED
      period / from / to / year / month — standard DateRangeFilter
    """
    date_filter = filters.to_prisma_filter()

    where: dict = {}

    if date_filter:
        where["date"] = date_filter

    if buyer_name:
        where["buyerName"] = {"contains": buyer_name, "mode": "insensitive"}

    if seller_name:
        where["sellerName"] = {"contains": seller_name, "mode": "insensitive"}

    if order_status:
        valid = {"PENDING", "IN_PROGRESS", "COMPLETED", "CANCELLED"}
        normalised = order_status.upper()
        if normalised not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid order_status '{order_status}'. "
                       f"Valid values: {', '.join(sorted(valid))}",
            )
        where["orderStatus"] = normalised

    account_filter: dict = {"isActive": True}
    if account_name:
        account_filter["accountName"] = {"contains": account_name, "mode": "insensitive"}
    where["account"] = {"is": account_filter}

    total = await db.pmakinhouse.count(where=where)

    deals = await db.pmakinhouse.find_many(
        where=where,
        order={"date": "desc"},
        skip=pagination.skip,
        take=pagination.take,
        include={"account": True},
    )

    all_for_totals = await db.pmakinhouse.find_many(where=where)

    total_amount       = sum(float(d.orderAmount) for d in all_for_totals)
    combined_by_status = _empty_inhouse_by_status()
    for d in all_for_totals:
        key = d.orderStatus if isinstance(d.orderStatus, str) else d.orderStatus.value
        if key in combined_by_status:
            combined_by_status[key]["count"]       += 1
            combined_by_status[key]["totalAmount"] += float(d.orderAmount)

    return {
        "filter": filters.meta(),
        "totals": {
            "totalDeals":  total,
            "totalAmount": round(total_amount, 2),
            "byStatus":    combined_by_status,
        },
        "pagination": {
            "page":       pagination.page,
            "pageSize":   pagination.take,
            "total":      total,
            "totalPages": max(1, -(-total // pagination.take)),
        },
        "deals": [_serialize_inhouse_with_account(d) for d in deals],
    }


async def update_inhouse_deal(
    db:      Prisma,
    deal_id: str,
    data:    PmakInhouseFullUpdate,
):
    """
    PATCH /inhouse/{deal_id} — Full optional-field update.

    [FIX-3] All seven inhouse fields are now individually patchable.
    If account_name is supplied the deal is re-linked to the new account.
    Sending an empty body {} is idempotent — returns current state unchanged.
    """
    deal = await db.pmakinhouse.find_unique(
        where={"id": deal_id},
        include={"account": True},
    )
    if not deal:
        raise HTTPException(status_code=404, detail="Inhouse deal not found")

    update_data: dict = {}

    # Re-assign to a different account if requested
    new_account = None
    if data.account_name is not None:
        new_account = await db.pmakaccount.find_first(
            where={
                "accountName": {"equals": data.account_name, "mode": "insensitive"},
                "isActive":    True,
            }
        )
        if not new_account:
            raise HTTPException(
                status_code=404,
                detail=f"Active PMAK account '{data.account_name}' not found",
            )
        update_data["account"] = {"connect": {"id": new_account.id}}

    if data.date is not None:
        update_data["date"] = _to_dt(data.date)
    if data.details is not None:
        update_data["details"] = data.details
    if data.buyer_name is not None:
        update_data["buyerName"] = data.buyer_name
    if data.seller_name is not None:
        update_data["sellerName"] = data.seller_name
    if data.order_amount is not None:
        update_data["orderAmount"] = data.order_amount
    if data.order_status is not None:
        update_data["orderStatus"] = data.order_status.value

    # Idempotent — return current state if nothing changed
    if not update_data:
        account_name = deal.account.accountName if deal.account else ""
        return _serialize_inhouse(deal, account_name)

    updated = await db.pmakinhouse.update(
        where={"id": deal_id},
        data=update_data,
    )

    # Resolve account name for serialisation
    if new_account:
        resolved_account_name = new_account.accountName
    elif deal.account:
        resolved_account_name = deal.account.accountName
    else:
        acct = await db.pmakaccount.find_unique(where={"id": updated.accountId})
        resolved_account_name = acct.accountName if acct else ""

    return _serialize_inhouse(updated, resolved_account_name)


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


# ─────────────────────────────────────────────────────────────────────────────
# v5 additions — PATCH /accounts/{account_id}  &  PATCH /transactions/{id}
# ─────────────────────────────────────────────────────────────────────────────

async def update_account(db: Prisma, account_id: str, data: PmakAccountCreate):
    """
    PATCH /accounts/{account_id} — rename or toggle isActive on a PMAK account.
    Raises 404 if the account does not exist.
    Raises 409 if the new name collides with an existing account.
    """
    account = await db.pmakaccount.find_unique(where={"id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="PMAK account not found")

    if data.accountName and data.accountName != account.accountName:
        conflict = await db.pmakaccount.find_first(
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

    updated = await db.pmakaccount.update(
        where={"id": account_id},
        data={"accountName": data.accountName},
    )
    return {
        "id":          updated.id,
        "accountName": updated.accountName,
        "isActive":    updated.isActive,
    }


async def update_transaction(
    db:             Prisma,
    transaction_id: str,
    data:           PmakTransactionCreate,
):
    """
    PATCH /transactions/{transaction_id} — partial update of any transaction field.

    remainingBalance auto-recalculation when debit/credit changes.

    If the caller updates `debit` and/or `credit` but does NOT supply an
    explicit `remaining_balance` override, the service now automatically
    recomputes the running balance using the reverse of the ledger formula:

        balance_before_this_txn = old_remainingBalance + old_debit − old_credit
        new_remainingBalance     = balance_before_this_txn − new_debit + new_credit

    This guarantees the balance stored in the DB and returned in the response
    always reflects the actual debit/credit values on the row, regardless of
    whether the caller remembered to supply `remaining_balance`.

    The caller may still pass `remaining_balance` explicitly (non-zero, non-None)
    to force a manual correction — that value takes precedence.

    Raises 404 if the transaction does not exist.
    """
    txn = await db.pmaktransaction.find_unique(where={"id": transaction_id})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    patch: dict = {}

    if data.date is not None:
        patch["date"] = _to_dt(data.date)
    if data.details is not None:
        patch["details"] = data.details
    if data.accountFrom is not None:
        patch["accountFrom"] = data.accountFrom
    if data.accountTo is not None:
        patch["accountTo"] = data.accountTo
    if data.debit is not None:
        patch["debit"] = data.debit
    if data.credit is not None:
        patch["credit"] = data.credit

    # ── remainingBalance resolution (three-way priority) ─────────────────────
    # Priority 1: explicit non-zero caller override → trust it as a correction
    # Priority 2: debit or credit changed → auto-recompute from stored state
    # Priority 3: neither → leave remainingBalance unchanged in the DB

    computed_balance: Optional[Decimal] = None

    caller_override = (
        data.remaining_balance is not None
        and data.remaining_balance != Decimal("0")
    )

    if caller_override:
        # [Priority 1] Manual balance correction supplied by the caller.
        computed_balance           = Decimal(str(data.remaining_balance))
        patch["remainingBalance"]  = computed_balance

    elif "debit" in patch or "credit" in patch:
        # [Priority 2] Debit or credit changed — auto-derive the new balance.
        #
        # Reverse the stored formula to recover the balance BEFORE this entry:
        #   stored formula:  remainingBalance = balance_before − debit + credit
        #   reversed:        balance_before   = remainingBalance + debit − credit
        #
        # Then apply the updated values:
        #   new_remainingBalance = balance_before − new_debit + new_credit
        old_remaining   = float(txn.remainingBalance)
        old_debit       = float(txn.debit)
        old_credit      = float(txn.credit)
        balance_before  = old_remaining + old_debit - old_credit

        new_debit  = float(patch.get("debit",  txn.debit))
        new_credit = float(patch.get("credit", txn.credit))

        computed_balance           = Decimal(str(round(
            balance_before - new_debit + new_credit, 2
        )))
        patch["remainingBalance"]  = computed_balance

    if data.status is not None:
        patch["status"] = data.status.value

    # Idempotent — nothing changed
    if not patch:
        account = await db.pmakaccount.find_unique(where={"id": txn.accountId})
        return _serialize_txn(txn, account.accountName if account else "")

    updated = await db.pmaktransaction.update(
        where={"id": transaction_id},
        data=patch,
    )
    account = await db.pmakaccount.find_unique(where={"id": updated.accountId})

    response = _serialize_txn(updated, account.accountName if account else "")

    # ── Inject computed balance into response (belt-and-suspenders) ───────────
    # If we auto-computed or accepted a caller override, inject it directly so
    # the response always reflects the exact value written to the DB, regardless
    # of any ORM Decimal coercion in the update() return object.
    if computed_balance is not None:
        response["remainingBalance"] = computed_balance

    return response


# ── Name aliases — router uses short names; keep both sides in sync ───────────
add_inhouse         = create_inhouse_deal
update_inhouse      = update_inhouse_deal
delete_inhouse      = delete_inhouse_deal
get_all_inhouse     = list_all_inhouse_deals
get_account_inhouse = get_account_inhouse_deals