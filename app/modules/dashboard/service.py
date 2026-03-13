"""
app/modules/dashboard/service.py
==================================
Enterprise Dashboard — full KPI summary with per-module drill-down and
time-period filtering (DAILY | WEEKLY | MONTHLY | YEARLY).

Modules covered:
  ✅ Fiverr Profiles      — availableWithdraw, notCleared, activeOrders, activeOrderAmount
  ✅ Upwork Profiles      — availableWithdraw, pending, inReview, workInProgress
  ✅ Outside Orders       — orderAmount, receiveAmount, dueAmount (by status)
  ✅ Card Sharing         — cardLimit, cardPaymentReceive
  ✅ Payoneer             — balance (last remainingBalance per account)
  ✅ PMAK                 — balance + inhouse totals
  ✅ Dollar Exchange      — totalBdt exchanged, DUE vs RECEIVED
  ✅ HR Expense           — debit/credit totals
  ✅ Inventory            — total item count, total value

Filter strategy
---------------
  period=daily    → rows WHERE date = :ref_date          (default: today)
  period=weekly   → rows WHERE date BETWEEN week_start AND week_end
  period=monthly  → rows WHERE YEAR(date)=:year AND MONTH(date)=:month
  period=yearly   → rows WHERE YEAR(date)=:year

All filters are ADDITIVE:  each section of the dashboard respects the same
date window so the frontend can show a fully consistent time-scoped view.

Usage from router:
    from .service import get_dashboard_summary
    data = await get_dashboard_summary(db, period="weekly", export_date="2025-03-10")
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal

from prisma import Prisma

logger = logging.getLogger(__name__)

# ── Types ────────────────────────────────────────────────────────────────────
Period = Literal["daily", "weekly", "monthly", "yearly", "all"]

_ZERO = Decimal("0")


# ── Date-window helpers ───────────────────────────────────────────────────────

def _parse_date(raw: str | None) -> date:
    """Parse an ISO date string or return today."""
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return date.today()


def _date_window(
    period: Period,
    ref_date: date | None = None,
    year: int | None = None,
    month: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> tuple[date | None, date | None]:
    """
    Return (start, end) inclusive date range for the requested period.
    Returns (None, None) for period='all' — callers must omit the date filter.

    Priority: explicit from/to > period > all
    """
    # Explicit override always wins
    if from_date and to_date:
        return from_date, to_date

    today = date.today()

    if period == "daily":
        d = ref_date or today
        return d, d

    if period == "weekly":
        d = ref_date or today
        # Monday-anchored ISO week
        start = d - timedelta(days=d.weekday())
        end   = start + timedelta(days=6)
        return start, end

    if period == "monthly":
        y = year or today.year
        m = month or today.month
        start = date(y, m, 1)
        # Last day of month
        if m == 12:
            end = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(y, m + 1, 1) - timedelta(days=1)
        return start, end

    if period == "yearly":
        y = year or today.year
        return date(y, 1, 1), date(y, 12, 31)

    # period == "all"
    return None, None


def _to_dt_start(d: date) -> datetime:
    """
    Convert a date → datetime at the very start of that day.
    Required because all schema date fields are declared as `DateTime @db.Date`
    and prisma-client-py's JSON serializer only accepts datetime.datetime,
    NOT datetime.date — passing a bare date raises TypeError at query-build time.
    """
    return datetime.combine(d, time.min)


def _to_dt_end(d: date) -> datetime:
    """Convert a date → datetime at the very end of that day (23:59:59.999999)."""
    return datetime.combine(d, time.max)


def _prisma_date_filter(start: date | None, end: date | None) -> dict:
    """
    Build a Prisma WHERE clause fragment for a date range.

    Always uses gte/lte with datetime objects — never bare date objects —
    because prisma-client-py cannot JSON-serialise datetime.date.
    Returns {} for period='all' so callers can omit the filter entirely.
    """
    if start is None:
        return {}
    return {
        "date": {
            "gte": _to_dt_start(start),
            "lte": _to_dt_end(end if end is not None else start),
        }
    }


def _d(v) -> Decimal:
    """Safely coerce a Prisma Decimal/None to Python Decimal."""
    if v is None:
        return _ZERO
    return Decimal(str(v))


# ── Section builders ──────────────────────────────────────────────────────────

async def _fiverr_summary(
    db: Prisma,
    date_filter: dict,
) -> dict[str, Any]:
    """
    Per-profile snapshot + aggregated totals.
    Uses FiverrEntry (daily snapshots) for balance figures and
    FiverrOrder (individual orders) for revenue within the window.
    """
    profiles = await db.fiverrprofile.find_many(
        where={"isActive": True},
        include={
            "entries": {
                "where": date_filter if date_filter else {},
                "order_by": {"date": "desc"},
            },
            "orders": {
                "where": date_filter if date_filter else {},
            },
        },
    )

    profile_list = []
    total_available  = _ZERO
    total_not_cleared = _ZERO
    total_active_orders = 0
    total_active_order_amount = _ZERO
    total_revenue    = _ZERO  # sum of afterFiverr in window

    for p in profiles:
        # Latest entry in the window = most recent snapshot
        latest = p.entries[0] if p.entries else None

        avail   = _d(latest.availableWithdraw)  if latest else _ZERO
        not_cl  = _d(latest.notCleared)          if latest else _ZERO
        act_ord = latest.activeOrders             if latest else 0
        act_amt = _d(latest.activeOrderAmount)   if latest else _ZERO

        # Revenue = sum of afterFiverr for individual orders in window
        revenue = sum((_d(o.afterFiverr) for o in p.orders), _ZERO)

        total_available          += avail
        total_not_cleared        += not_cl
        total_active_orders      += act_ord
        total_active_order_amount += act_amt
        total_revenue            += revenue

        profile_list.append({
            "profileId":          p.id,
            "profileName":        p.profileName,
            "availableWithdraw":  float(avail),
            "notCleared":         float(not_cl),
            "activeOrders":       act_ord,
            "activeOrderAmount":  float(act_amt),
            "revenueInPeriod":    float(revenue),
            "entryCount":         len(p.entries),
        })

    return {
        "totals": {
            "availableWithdraw":  float(total_available),
            "notCleared":         float(total_not_cleared),
            "activeOrders":       total_active_orders,
            "activeOrderAmount":  float(total_active_order_amount),
            "revenueInPeriod":    float(total_revenue),
        },
        "Fiverr_profiles": profile_list,
    }


async def _upwork_summary(
    db: Prisma,
    date_filter: dict,
) -> dict[str, Any]:
    profiles = await db.upworkprofile.find_many(
        where={"isActive": True},
        include={
            "entries": {
                "where": date_filter if date_filter else {},
                "order_by": {"date": "desc"},
            },
            "orders": {
                "where": date_filter if date_filter else {},
            },
        },
    )

    profile_list = []
    total_available  = _ZERO
    total_pending    = _ZERO
    total_in_review  = _ZERO
    total_wip        = _ZERO
    total_revenue    = _ZERO

    for p in profiles:
        latest  = p.entries[0] if p.entries else None
        avail   = _d(latest.availableWithdraw) if latest else _ZERO
        pending = _d(latest.pending)            if latest else _ZERO
        review  = _d(latest.inReview)           if latest else _ZERO
        wip     = _d(latest.workInProgress)     if latest else _ZERO
        revenue = sum((_d(o.afterUpwork) for o in p.orders), _ZERO)

        total_available += avail
        total_pending   += pending
        total_in_review += review
        total_wip       += wip
        total_revenue   += revenue

        profile_list.append({
            "profileId":         p.id,
            "profileName":       p.profileName,
            "availableWithdraw": float(avail),
            "pending":           float(pending),
            "inReview":          float(review),
            "workInProgress":    float(wip),
            "revenueInPeriod":   float(revenue),
            "entryCount":        len(p.entries),
        })

    return {
        "totals": {
            "availableWithdraw": float(total_available),
            "pending":           float(total_pending),
            "inReview":          float(total_in_review),
            "workInProgress":    float(total_wip),
            "revenueInPeriod":   float(total_revenue),
        },
        "Upwork_profiles": profile_list,
    }


async def _outside_orders_summary(
    db: Prisma,
    date_filter: dict,
) -> dict[str, Any]:
    where = {**date_filter}
    orders = await db.outsideorder.find_many(where=where)

    total_order   = _ZERO
    total_receive = _ZERO
    total_due     = _ZERO
    by_status: dict[str, int] = {}

    for o in orders:
        total_order   += _d(o.orderAmount)
        total_receive += _d(o.receiveAmount)
        total_due     += _d(o.dueAmount)
        by_status[o.orderStatus] = by_status.get(o.orderStatus, 0) + 1

    # Active = PENDING + IN_PROGRESS
    active_count = by_status.get("PENDING", 0) + by_status.get("IN_PROGRESS", 0)

    return {
        "totals": {
            "orderAmount":   float(total_order),
            "receiveAmount": float(total_receive),
            "dueAmount":     float(total_due),
            "orderCount":    len(orders),
            "activeOrders":  active_count,
        },
        "byStatus": {
            "PENDING":     by_status.get("PENDING", 0),
            "IN_PROGRESS": by_status.get("IN_PROGRESS", 0),
            "COMPLETED":   by_status.get("COMPLETED", 0),
            "CANCELLED":   by_status.get("CANCELLED", 0),
        },
    }


async def _card_sharing_summary(
    db: Prisma,
    date_filter: dict,
) -> dict[str, Any]:
    cards = await db.cardsharing.find_many(where={**date_filter})

    total_limit   = _ZERO
    total_payment = _ZERO

    for c in cards:
        total_limit   += _d(c.cardLimit)
        total_payment += _d(c.cardPaymentReceive)

    return {
        "totals": {
            "cardCount":          len(cards),
            "totalCardLimit":     float(total_limit),
            "totalPaymentReceived": float(total_payment),
            "outstanding":        float(total_limit - total_payment),
        },
    }


async def _payoneer_summary(
    db: Prisma,
    date_filter: dict,
) -> dict[str, Any]:
    """
    Balance = the most recent remainingBalance per account.
    Within a date window we take the last entry in that window;
    for 'all' we take the latest overall.
    """
    accounts = await db.payoneeraccount.find_many(
        where={"isActive": True},
        include={
            "transactions": {
                "where": date_filter if date_filter else {},
                "order_by": {"date": "desc"},
                "take": 1,
            },
        },
    )

    account_list = []
    total_balance = _ZERO

    for a in accounts:
        latest_tx = a.transactions[0] if a.transactions else None
        balance   = _d(latest_tx.remainingBalance) if latest_tx else _ZERO
        total_balance += balance
        account_list.append({
            "accountId":   a.id,
            "accountName": a.accountName,
            "balance":     float(balance),
            "lastUpdated": latest_tx.date.isoformat() if latest_tx else None,
        })

    return {
        "totals": {
            "totalBalance": float(total_balance),
            "accountCount": len(accounts),
        },
        "accounts": account_list,
    }


async def _pmak_summary(
    db: Prisma,
    date_filter: dict,
) -> dict[str, Any]:
    accounts = await db.pmakaccount.find_many(
        where={"isActive": True},
        include={
            "transactions": {
                "where": date_filter if date_filter else {},
                "order_by": {"date": "desc"},
                "take": 1,
            },
            "inhouseDeals": {
                "where": date_filter if date_filter else {},
            },
        },
    )

    account_list = []
    total_balance = _ZERO
    total_inhouse = _ZERO
    inhouse_by_status: dict[str, int] = {}

    for a in accounts:
        latest_tx = a.transactions[0] if a.transactions else None
        balance   = _d(latest_tx.remainingBalance) if latest_tx else _ZERO
        inhouse   = sum((_d(d.orderAmount) for d in a.inhouseDeals), _ZERO)

        total_balance += balance
        total_inhouse += inhouse

        for deal in a.inhouseDeals:
            inhouse_by_status[deal.orderStatus] = inhouse_by_status.get(deal.orderStatus, 0) + 1

        account_list.append({
            "accountId":      a.id,
            "accountName":    a.accountName,
            "balance":        float(balance),
            "inhouseTotal":   float(inhouse),
            "inhouseCount":   len(a.inhouseDeals),
        })

    return {
        "totals": {
            "totalBalance":     float(total_balance),
            "totalInhouse":     float(total_inhouse),
            "inhouseByStatus":  inhouse_by_status,
        },
        "accounts": account_list,
    }


async def _dollar_exchange_summary(
    db: Prisma,
    date_filter: dict,
) -> dict[str, Any]:
    rows = await db.dollarexchange.find_many(where={**date_filter})

    total_usd_exchanged = _ZERO
    total_bdt           = _ZERO
    due_usd             = _ZERO
    received_usd        = _ZERO

    for r in rows:
        # Net USD moved on this transaction
        net_usd = _d(r.debit) + _d(r.credit)
        total_usd_exchanged += net_usd
        total_bdt           += _d(r.totalBdt)

        if r.paymentStatus == "DUE":
            due_usd      += net_usd
        else:
            received_usd += net_usd

    return {
        "totals": {
            "totalUsdExchanged": float(total_usd_exchanged),
            "totalBdt":          float(total_bdt),
            "dueUsd":            float(due_usd),
            "receivedUsd":       float(received_usd),
            "transactionCount":  len(rows),
        },
    }


async def _hr_expense_summary(
    db: Prisma,
    date_filter: dict,
) -> dict[str, Any]:
    rows = await db.hrexpense.find_many(where={**date_filter})

    total_debit  = _ZERO
    total_credit = _ZERO
    latest_balance = _ZERO

    for r in rows:
        total_debit  += _d(r.debit)
        total_credit += _d(r.credit)
        latest_balance = _d(r.remainingBalance)  # last row wins

    return {
        "totals": {
            "totalDebit":      float(total_debit),
            "totalCredit":     float(total_credit),
            "netExpense":      float(total_debit - total_credit),
            "latestBalance":   float(latest_balance),
            "transactionCount": len(rows),
        },
    }


async def _inventory_summary(
    db: Prisma,
    date_filter: dict,
) -> dict[str, Any]:
    items = await db.inventory.find_many(where={**date_filter})

    total_value    = _ZERO
    total_quantity = 0
    by_category: dict[str, int] = {}

    for i in items:
        total_value    += _d(i.totalPrice)
        total_quantity += i.quantity
        cat = i.category or "Uncategorized"
        by_category[cat] = by_category.get(cat, 0) + 1

    return {
        "totals": {
            "itemCount":     len(items),
            "totalQuantity": total_quantity,
            "totalValue":    float(total_value),
        },
        "byCategory": by_category,
    }


# ── Top-level aggregator ──────────────────────────────────────────────────────

async def get_dashboard_summary(
    db: Prisma,
    period: Period = "all",
    ref_date_str: str | None = None,
    year: int | None = None,
    month: int | None = None,
    from_date_str: str | None = None,
    to_date_str: str | None = None,
) -> dict[str, Any]:
    """
    Returns a fully structured dashboard payload containing all modules.

    Parameters
    ----------
    period       : "daily" | "weekly" | "monthly" | "yearly" | "all"
    ref_date_str : ISO date string used as reference for daily/weekly (defaults to today)
    year         : year for monthly/yearly filter
    month        : month (1–12) for monthly filter
    from_date_str: explicit range start (ISO date) — overrides period
    to_date_str  : explicit range end   (ISO date) — overrides period
    """
    ref_date  = _parse_date(ref_date_str)
    from_date = _parse_date(from_date_str) if from_date_str else None
    to_date   = _parse_date(to_date_str)   if to_date_str   else None

    start, end = _date_window(period, ref_date, year, month, from_date, to_date)
    date_filter = _prisma_date_filter(start, end)

    # ── Metadata ─────────────────────────────────────────────────────────────
    filter_meta: dict[str, Any] = {
        "period":     period,
        "dateRange": {
            "from": start.isoformat() if start else None,
            "to":   end.isoformat()   if end   else None,
        },
    }

    # ── Fetch all modules concurrently ────────────────────────────────────────
    import asyncio

    (
        fiverr,
        upwork,
        outside,
        card,
        payoneer,
        pmak,
        dollar,
        hr,
        inventory,
    ) = await asyncio.gather(
        _fiverr_summary(db, date_filter),
        _upwork_summary(db, date_filter),
        _outside_orders_summary(db, date_filter),
        _card_sharing_summary(db, date_filter),
        _payoneer_summary(db, date_filter),
        _pmak_summary(db, date_filter),
        _dollar_exchange_summary(db, date_filter),
        _hr_expense_summary(db, date_filter),
        _inventory_summary(db, date_filter),
    )

    # ── Cross-module KPI roll-ups ─────────────────────────────────────────────
    total_available_withdraw = (
        fiverr["totals"]["availableWithdraw"]
        + upwork["totals"]["availableWithdraw"]
    )
    total_not_cleared = fiverr["totals"]["notCleared"]
    total_active_orders = (
        fiverr["totals"]["activeOrders"]
        + outside["totals"]["activeOrders"]
    )
    total_revenue = (
        fiverr["totals"]["revenueInPeriod"]
        + upwork["totals"]["revenueInPeriod"]
        + outside["totals"]["receiveAmount"]
    )

    return {
        "filter":   filter_meta,
        "kpis": {
            "totalRevenue":          round(total_revenue, 2),
            "totalAvailableWithdraw": round(total_available_withdraw, 2),
            "totalNotCleared":        round(total_not_cleared, 2),
            "totalActiveOrders":      total_active_orders,
            "payoneerBalance":        payoneer["totals"]["totalBalance"],
            "pmakBalance":            pmak["totals"]["totalBalance"],
            "dollarExchangeTotal":    dollar["totals"]["totalUsdExchanged"],
            "hrExpenseTotal":         hr["totals"]["netExpense"],
        },
        "modules": {
            "fiverr":         fiverr,
            "upwork":         upwork,
            "outsideOrders":  outside,
            "cardSharing":    card,
            "payoneer":       payoneer,
            "pmak":           pmak,
            "dollarExchange": dollar,
            "hrExpense":      hr,
            "inventory":      inventory,
        },
    }