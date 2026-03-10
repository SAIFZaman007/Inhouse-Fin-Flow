"""
app/modules/dashboard/service.py
==================================
Dashboard KPI aggregation — 9 top-level metrics with full drill-down detail.

═══════════════════════════════════════════════════════════════════════════════
KPI FORMULA TABLE (per PDF spec)
═══════════════════════════════════════════════════════════════════════════════
┌─────────────────────────┬────────────────────────────────────────────────────┐
│ KPI                     │ Formula                                            │
├─────────────────────────┼────────────────────────────────────────────────────┤
│ 1. Total Revenue        │ Total Avail Withdraw + Not Cleared + Payoneer Bal  │
│ 2. Total Avail Withdraw │ Σ Fiverr availableWithdraw + Σ Upwork avail        │
│ 3. Not Cleared          │ Σ Fiverr notCleared + Σ Upwork pending             │
│ 4. Active Orders        │ Σ Fiverr activeOrders (Upwork has no active field) │
│ 5. Payoneer Balance     │ Σ latest remainingBalance per active account       │
│ 6. PMAK Balance         │ Σ latest remainingBalance per active account       │
│ 7. Dollar Exchange      │ Σ totalBdt + live rate conversion                  │
│ 8. HR Expense           │ Latest remainingBalance in HR ledger               │
│ 9. Inventory            │ Item count + Σ totalPrice                          │
└─────────────────────────┴────────────────────────────────────────────────────┘
"""
import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from prisma import Prisma

logger = logging.getLogger(__name__)


# ─── helpers ─────────────────────────────────────────────────────────────────

def _f(val: Any) -> float:
    """Safely convert Decimal / None → float."""
    if val is None:
        return 0.0
    return float(val)


def _dt_filter(d_from: date, d_to: date) -> dict:
    """
    Convert Python date range to Prisma-compatible datetime filter.

    CRITICAL: prisma-client-py's _builder.py cannot json.dumps() datetime.date
    objects — raises TypeError. Pass datetime objects instead.
    """
    return {
        "gte": datetime.combine(d_from, time.min),
        "lte": datetime.combine(d_to,   time.max),
    }


# ─── main entry point ────────────────────────────────────────────────────────

async def get_dashboard_summary(db: Prisma) -> dict:
    """
    Aggregate all 9 KPIs for the admin dashboard.
    Each section is fetched independently with isolated error handling so
    one failing module never takes down the entire dashboard response.
    """
    result: dict = {}

    # ── Fetch current daily rate (set by HR) ──────────────────────────────────
    current_rate: float | None = None
    daily_rate_info: dict = {}
    try:
        rate_rec = await db.dailyrate.find_first(order={"date": "desc"})
        if rate_rec:
            current_rate = _f(rate_rec.rate)
            daily_rate_info = {
                "rate":      current_rate,
                "date":      rate_rec.date.isoformat(),
                "setBy":     rate_rec.setBy or "HR",
                "note":      rate_rec.note or "",
            }
    except Exception as exc:
        logger.warning("Dashboard: DailyRate fetch failed (non-critical): %s", exc)

    # ── 1, 2, 3, 4: Fiverr ───────────────────────────────────────────────────
    fiverr_avail    = Decimal("0")
    fiverr_cleared  = Decimal("0")
    fiverr_active   = 0
    fiverr_profiles_breakdown = []

    try:
        fiverr_profiles = await db.fiverrprofile.find_many(
            where={"isActive": True},
            include={"entries": {"take": 5}},
            order={"profileName": "asc"},
        )
        for p in fiverr_profiles:
            entries = sorted(p.entries, key=lambda e: e.date, reverse=True) if p.entries else []
            latest  = entries[0] if entries else None

            avail   = latest.availableWithdraw if latest else Decimal("0")
            cleared = latest.notCleared        if latest else Decimal("0")
            active  = latest.activeOrders      if latest else 0

            fiverr_avail   += avail
            fiverr_cleared += cleared
            fiverr_active  += active

            fiverr_profiles_breakdown.append({
                "id":                p.id,
                "profileName":       p.profileName,
                "availableWithdraw": _f(avail),
                "notCleared":        _f(cleared),
                "activeOrders":      active,
                "latestDate":        latest.date.isoformat() if latest else None,
                "recentEntries": [
                    {
                        "date":              e.date.isoformat(),
                        "availableWithdraw": _f(e.availableWithdraw),
                        "notCleared":        _f(e.notCleared),
                        "activeOrders":      e.activeOrders,
                        "submitted":         _f(e.submitted),
                        "withdrawn":         _f(e.withdrawn),
                        "sellerPlus":        e.sellerPlus,
                        "promotion":         _f(e.promotion),
                    }
                    for e in entries[:5]
                ],
            })
    except Exception as exc:
        logger.error("Dashboard: Fiverr section failed: %s", exc, exc_info=True)
        result["_errors"] = result.get("_errors", []) + ["fiverr"]

    # ── Upwork ────────────────────────────────────────────────────────────────
    upwork_avail    = Decimal("0")
    upwork_cleared  = Decimal("0")
    upwork_profiles_breakdown = []

    try:
        upwork_profiles = await db.upworkprofile.find_many(
            where={"isActive": True},
            include={"entries": {"take": 5}},
            order={"profileName": "asc"},
        )
        for p in upwork_profiles:
            entries = sorted(p.entries, key=lambda e: e.date, reverse=True) if p.entries else []
            latest  = entries[0] if entries else None

            avail   = latest.availableWithdraw if latest else Decimal("0")
            pending = latest.pending           if latest else Decimal("0")

            upwork_avail   += avail
            upwork_cleared += pending

            upwork_profiles_breakdown.append({
                "id":                p.id,
                "profileName":       p.profileName,
                "availableWithdraw": _f(avail),
                "pending":           _f(pending),
                "inReview":          _f(latest.inReview)       if latest else 0.0,
                "workInProgress":    _f(latest.workInProgress) if latest else 0.0,
                "connects":          latest.connects            if latest else 0,
                "upworkPlus":        latest.upworkPlus          if latest else False,
                "latestDate":        latest.date.isoformat()    if latest else None,
                "recentEntries": [
                    {
                        "date":              e.date.isoformat(),
                        "availableWithdraw": _f(e.availableWithdraw),
                        "pending":           _f(e.pending),
                        "inReview":          _f(e.inReview),
                        "workInProgress":    _f(e.workInProgress),
                        "withdrawn":         _f(e.withdrawn),
                        "connects":          e.connects,
                        "upworkPlus":        e.upworkPlus,
                    }
                    for e in entries[:5]
                ],
            })
    except Exception as exc:
        logger.error("Dashboard: Upwork section failed: %s", exc, exc_info=True)
        result["_errors"] = result.get("_errors", []) + ["upwork"]

    # ── 5. Payoneer Balance ───────────────────────────────────────────────────
    payoneer_balance = Decimal("0")
    payoneer_breakdown = []

    try:
        payoneer_accounts = await db.payoneeraccount.find_many(
            where={"isActive": True},
            include={"transactions": {"take": 10}},
            order={"accountName": "asc"},
        )
        for acc in payoneer_accounts:
            txns           = sorted(acc.transactions, key=lambda t: t.date, reverse=True)
            latest_balance = txns[0].remainingBalance if txns else Decimal("0")
            payoneer_balance += latest_balance

            payoneer_breakdown.append({
                "id":               acc.id,
                "accountName":      acc.accountName,
                "remainingBalance": _f(latest_balance),
                "recentTransactions": [
                    {
                        "id":               t.id,
                        "date":             t.date.isoformat(),
                        "details":          t.details,
                        "accountFrom":      t.accountFrom,
                        "accountTo":        t.accountTo,
                        "debit":            _f(t.debit),
                        "credit":           _f(t.credit),
                        "remainingBalance": _f(t.remainingBalance),
                    }
                    for t in txns[:10]
                ],
            })
    except Exception as exc:
        logger.error("Dashboard: Payoneer section failed: %s", exc, exc_info=True)
        result["_errors"] = result.get("_errors", []) + ["payoneer"]

    # ── 6. PMAK Balance ───────────────────────────────────────────────────────
    pmak_balance = Decimal("0")
    pmak_breakdown = []

    try:
        pmak_accounts = await db.pmakaccount.find_many(
            where={"isActive": True},
            include={"transactions": {"take": 10}},
            order={"accountName": "asc"},
        )
        for acc in pmak_accounts:
            txns           = sorted(acc.transactions, key=lambda t: t.date, reverse=True)
            latest_balance = txns[0].remainingBalance if txns else Decimal("0")
            pmak_balance  += latest_balance

            pmak_breakdown.append({
                "id":               acc.id,
                "accountName":      acc.accountName,
                "remainingBalance": _f(latest_balance),
                "recentTransactions": [
                    {
                        "id":               t.id,
                        "date":             t.date.isoformat(),
                        "details":          t.details,
                        "accountFrom":      t.accountFrom,
                        "accountTo":        t.accountTo,
                        "debit":            _f(t.debit),
                        "credit":           _f(t.credit),
                        "remainingBalance": _f(t.remainingBalance),
                        "status":           t.status,
                        "notes":            t.notes,
                    }
                    for t in txns[:10]
                ],
            })
    except Exception as exc:
        logger.error("Dashboard: PMAK section failed: %s", exc, exc_info=True)
        result["_errors"] = result.get("_errors", []) + ["pmak"]

    # ── 7. Dollar Exchange ────────────────────────────────────────────────────
    #
    # Schema facts: enum PaymentStatus { RECEIVED  DUE }
    # All filters use "RECEIVED" (not "RCV") to match the Prisma enum exactly.
    #
    # NEW: Each record now includes totalBdtLive = dollar_amount × current_rate
    #
    dollar_exchange_total_bdt = Decimal("0")
    dollar_exchange_breakdown: dict = {}

    try:
        exchange_records = await db.dollarexchange.find_many(
            order={"date": "desc"},
            take=50,
        )

        # Aggregate by status — enum values: "RECEIVED" | "DUE"
        # NOTE: prisma-client-py has NO .aggregate() — use query_raw() instead.
        # Table: dollar_exchanges  (@@map); columns quoted in camelCase as Prisma generates them.
        _de_rows = await db.query_raw(
            """
            SELECT
                COALESCE(SUM("totalBdt"), 0)                                                    AS total,
                COALESCE(SUM(CASE WHEN "paymentStatus" = 'RECEIVED' THEN "totalBdt" END), 0)   AS received,
                COALESCE(SUM(CASE WHEN "paymentStatus" = 'DUE'      THEN "totalBdt" END), 0)   AS due,
                COUNT(*) FILTER (WHERE "paymentStatus" = 'DUE')                                 AS due_count,
                COUNT(*) FILTER (WHERE "paymentStatus" = 'RECEIVED')                            AS rcv_count
            FROM dollar_exchanges
            """
        )
        _de = _de_rows[0] if _de_rows else {}
        dollar_exchange_total_bdt = Decimal(str(_de.get("total",    0) or 0))
        _due_bdt  = float(_de.get("due",      0) or 0)
        _rcv_bdt  = float(_de.get("received", 0) or 0)
        due_count = int(_de.get("due_count",  0) or 0)
        rcv_count = int(_de.get("rcv_count",  0) or 0)

        def _dollar_amount(r: Any) -> float:
            """Extract the dollar amount from a record (credit takes priority)."""
            c = _f(r.credit)
            d = _f(r.debit)
            return c if c > 0 else d

        dollar_exchange_breakdown = {
            "totalBdt":    _f(dollar_exchange_total_bdt),
            "dueBdt":      _due_bdt,
            "receivedBdt": _rcv_bdt,
            "dueCount":    due_count,
            "rcvCount":    rcv_count,
            # Live-rate totals
            "currentRate":      current_rate,
            "dailyRate":        daily_rate_info,
            "totalBdtLive":     round(
                sum(_dollar_amount(r) for r in exchange_records) * current_rate, 2
            ) if current_rate else None,
            "recentRecords": [
                {
                    "id":            r.id,
                    "date":          r.date.isoformat(),
                    "details":       r.details,
                    "accountFrom":   r.accountFrom,
                    "accountTo":     r.accountTo,
                    "debit":         _f(r.debit),
                    "credit":        _f(r.credit),
                    "rate":          _f(r.rate),
                    "totalBdt":      _f(r.totalBdt),
                    # Live conversion: dollar_amount × current daily rate
                    "totalBdtLive":  round(_dollar_amount(r) * current_rate, 2)
                                     if current_rate else None,
                    "paymentStatus": r.paymentStatus,
                }
                for r in exchange_records
            ],
        }
    except Exception as exc:
        logger.error("Dashboard: DollarExchange section failed: %s", exc, exc_info=True)
        result["_errors"] = result.get("_errors", []) + ["dollarExchange"]

    # ── 8. HR Expense ─────────────────────────────────────────────────────────
    hr_remaining_balance = Decimal("0")
    hr_breakdown: dict = {}

    try:
        hr_records = await db.hrexpense.find_many(
            order={"date": "desc"},
            take=20,
        )
        if hr_records:
            latest_hr            = sorted(hr_records, key=lambda e: e.date, reverse=True)[0]
            hr_remaining_balance = latest_hr.remainingBalance

        hr_breakdown = {
            "remainingBalance": _f(hr_remaining_balance),
            "recentRecords": [
                {
                    "id":               e.id,
                    "date":             e.date.isoformat(),
                    "details":          e.details,
                    "accountFrom":      e.accountFrom,
                    "accountTo":        e.accountTo,
                    "debit":            _f(e.debit),
                    "credit":           _f(e.credit),
                    "remainingBalance": _f(e.remainingBalance),
                }
                for e in hr_records
            ],
        }
    except Exception as exc:
        logger.error("Dashboard: HRExpense section failed: %s", exc, exc_info=True)
        result["_errors"] = result.get("_errors", []) + ["hrExpense"]

    # ── 9. Inventory ──────────────────────────────────────────────────────────
    inventory_breakdown: dict = {}

    try:
        inventory_items = await db.inventory.find_many(
            order={"date": "desc"},
            take=20,
        )
        total_count = await db.inventory.count()
        # NOTE: prisma-client-py has NO .aggregate() — use query_raw() instead.
        # Table: inventory (@@map); "totalPrice" quoted camelCase as Prisma generates it.
        _inv_rows   = await db.query_raw('SELECT COALESCE(SUM("totalPrice"), 0) AS total_value FROM inventory')
        total_value = Decimal(str((_inv_rows[0] if _inv_rows else {}).get("total_value", 0) or 0))

        inventory_breakdown = {
            "totalItems":  total_count,
            "totalValue":  _f(total_value),
            "recentItems": [
                {
                    "id":         i.id,
                    "date":       i.date.isoformat(),
                    "itemName":   i.itemName,
                    "category":   i.category,
                    "quantity":   i.quantity,
                    "unitPrice":  _f(i.unitPrice),
                    "totalPrice": _f(i.totalPrice),
                    "condition":  i.condition,
                    "assignedTo": i.assignedTo,
                }
                for i in inventory_items
            ],
        }
    except Exception as exc:
        logger.error("Dashboard: Inventory section failed: %s", exc, exc_info=True)
        result["_errors"] = result.get("_errors", []) + ["inventory"]

    # ── Outside Orders (contextual) ───────────────────────────────────────────
    outside_orders_breakdown: dict = {}

    try:
        outside_orders = await db.outsideorder.find_many(
            order={"date": "desc"},
            take=10,
        )
        outside_orders_breakdown = {
            "total": await db.outsideorder.count(),
            "orders": [
                {
                    "id":            o.id,
                    "date":          o.date.isoformat(),
                    "clientName":    o.clientName,
                    "orderDetails":  o.orderDetails,
                    "orderStatus":   o.orderStatus,
                    "orderAmount":   _f(o.orderAmount),
                    "receiveAmount": _f(o.receiveAmount),
                    "dueAmount":     _f(o.dueAmount),
                }
                for o in outside_orders
            ],
        }
    except Exception as exc:
        logger.error("Dashboard: OutsideOrders section failed: %s", exc, exc_info=True)
        result["_errors"] = result.get("_errors", []) + ["outsideOrders"]

    # ── Derived KPIs ──────────────────────────────────────────────────────────
    total_available_withdraw = fiverr_avail   + upwork_avail
    total_not_cleared        = fiverr_cleared + upwork_cleared
    total_active_orders      = fiverr_active
    total_revenue            = total_available_withdraw + total_not_cleared + payoneer_balance

    # ── Assemble final response ───────────────────────────────────────────────
    result.update({
        # ── KPI 1: Total Revenue ──────────────────────────────────────────────
        "totalRevenue": {
            "value": _f(total_revenue),
            "breakdown": {
                "totalAvailableWithdraw": _f(total_available_withdraw),
                "totalNotCleared":        _f(total_not_cleared),
                "payoneerBalance":        _f(payoneer_balance),
                "fiverrProfiles":         fiverr_profiles_breakdown,
                "upworkProfiles":         upwork_profiles_breakdown,
                "payoneerAccounts": [
                    {"accountName": a["accountName"], "remainingBalance": a["remainingBalance"]}
                    for a in payoneer_breakdown
                ],
            },
        },

        # ── KPI 2: Total Available Withdraw ───────────────────────────────────
        "totalAvailableWithdraw": {
            "value": _f(total_available_withdraw),
            "breakdown": {
                "fiverr": [
                    {"profileName": p["profileName"], "availableWithdraw": p["availableWithdraw"]}
                    for p in fiverr_profiles_breakdown
                ],
                "upwork": [
                    {"profileName": p["profileName"], "availableWithdraw": p["availableWithdraw"]}
                    for p in upwork_profiles_breakdown
                ],
            },
        },

        # ── KPI 3: Not Cleared ────────────────────────────────────────────────
        "notCleared": {
            "value": _f(total_not_cleared),
            "breakdown": {
                "fiverr": [
                    {"profileName": p["profileName"], "notCleared": p["notCleared"]}
                    for p in fiverr_profiles_breakdown
                ],
                "upwork": [
                    {"profileName": p["profileName"], "pending": p["pending"]}
                    for p in upwork_profiles_breakdown
                ],
            },
        },

        # ── KPI 4: Active Orders ──────────────────────────────────────────────
        "activeOrders": {
            "value": total_active_orders,
            "breakdown": {
                "fiverr": [
                    {"profileName": p["profileName"], "activeOrders": p["activeOrders"]}
                    for p in fiverr_profiles_breakdown
                ],
            },
        },

        # ── KPI 5: Payoneer Balance ───────────────────────────────────────────
        "payoneerBalance": {
            "value":     _f(payoneer_balance),
            "breakdown": payoneer_breakdown,
        },

        # ── KPI 6: PMAK Balance ───────────────────────────────────────────────
        "pmakBalance": {
            "value":     _f(pmak_balance),
            "breakdown": pmak_breakdown,
        },

        # ── KPI 7: Dollar Exchange ────────────────────────────────────────────
        "dollarExchange": dollar_exchange_breakdown,

        # ── KPI 8: HR Expense ─────────────────────────────────────────────────
        "hrExpense": hr_breakdown,

        # ── KPI 9: Inventory ──────────────────────────────────────────────────
        "inventory": inventory_breakdown,

        # ── Contextual: Outside Orders ────────────────────────────────────────
        "outsideOrders": outside_orders_breakdown,

        # ── Meta ──────────────────────────────────────────────────────────────
        "meta": {
            "generatedAt": datetime.utcnow().isoformat() + "Z",
            "dailyRate":   daily_rate_info,
        },
    })

    return result