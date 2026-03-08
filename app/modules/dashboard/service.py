"""
app/modules/dashboard/service.py

ROOT CAUSES fixed (all errors from GET /api/v1/dashboard/summary):

  1. "Field 'snapshots' either does not exist or is not a relational field on FiverrProfile"
     → Schema relation is named `entries` (FiverrEntry[]), not `snapshots`
     → Also: prisma-client-py does NOT support `order` inside nested `include` dicts
     → Fix: use `include={"entries": {"take": 5}}` and sort in Python

  2. Same for UpworkProfile → `entries` not `snapshots`

  3. "Could not find field at findManyPayoneerAccount.orderBy.name"
     → prisma-client-py uses `order` not `order_by`, and field is `accountName` not `name`
     → Fix: order={"accountName": "asc"}

  4. Same for PmakAccount

  5. "'OutsideOrder' object has no attribute 'status'"
     → Schema field is `orderStatus` (OrderStatus enum), not `status`
     → Fix: access .orderStatus in Python and use orderStatus in Pydantic response model
"""
import logging
from decimal import Decimal

from prisma import Prisma

logger = logging.getLogger(__name__)


async def get_dashboard_summary(db: Prisma) -> dict:
    """
    Aggregate data from all modules for the dashboard summary.
    Each section is fetched independently with isolated error handling so
    one failing section never takes down the entire dashboard response.
    """
    result = {}

    # ── Fiverr ────────────────────────────────────────────────────────────────
    try:
        fiverr_profiles = await db.fiverrprofile.find_many(
            where={"isActive": True},
            include={"entries": {"take": 5}},
            order={"profileName": "asc"},
        )
        for p in fiverr_profiles:
            if p.entries:
                p.entries.sort(key=lambda e: e.date, reverse=True)

        result["fiverr"] = {
            "profile_count": len(fiverr_profiles),
            "profiles": [
                {
                    "id": p.id,
                    "profileName": p.profileName,
                    "latestEntry": _serialize_fiverr_entry(p.entries[0]) if p.entries else None,
                }
                for p in fiverr_profiles
            ],
        }
    except Exception as exc:
        logger.error("Dashboard: Fiverr section failed: %s", exc)
        result["fiverr"] = {"error": "unavailable"}

    # ── Upwork ────────────────────────────────────────────────────────────────
    try:
        upwork_profiles = await db.upworkprofile.find_many(
            where={"isActive": True},
            include={"entries": {"take": 5}},
            order={"profileName": "asc"},
        )
        for p in upwork_profiles:
            if p.entries:
                p.entries.sort(key=lambda e: e.date, reverse=True)

        result["upwork"] = {
            "profile_count": len(upwork_profiles),
            "profiles": [
                {
                    "id": p.id,
                    "profileName": p.profileName,
                    "latestEntry": _serialize_upwork_entry(p.entries[0]) if p.entries else None,
                }
                for p in upwork_profiles
            ],
        }
    except Exception as exc:
        logger.error("Dashboard: Upwork section failed: %s", exc)
        result["upwork"] = {"error": "unavailable"}

    # ── Payoneer ──────────────────────────────────────────────────────────────
    try:
        payoneer_accounts = await db.payoneeraccount.find_many(
            where={"isActive": True},
            include={"transactions": {"take": 5}},
            order={"accountName": "asc"},
        )
        for acc in payoneer_accounts:
            if acc.transactions:
                acc.transactions.sort(key=lambda t: t.date, reverse=True)

        result["payoneer"] = {
            "account_count": len(payoneer_accounts),
            "accounts": [
                {
                    "id": acc.id,
                    "accountName": acc.accountName,
                    "latestTransaction": _serialize_transaction(acc.transactions[0]) if acc.transactions else None,
                }
                for acc in payoneer_accounts
            ],
        }
    except Exception as exc:
        logger.error("Dashboard: Payoneer section failed: %s", exc)
        result["payoneer"] = {"error": "unavailable"}

    # ── PMAK ──────────────────────────────────────────────────────────────────
    try:
        pmak_accounts = await db.pmakaccount.find_many(
            where={"isActive": True},
            include={"transactions": {"take": 5}},
            order={"accountName": "asc"},  
        )
        for acc in pmak_accounts:
            if acc.transactions:
                acc.transactions.sort(key=lambda t: t.date, reverse=True)

        result["pmak"] = {
            "account_count": len(pmak_accounts),
            "accounts": [
                {
                    "id": acc.id,
                    "accountName": acc.accountName,
                    "latestTransaction": _serialize_transaction(acc.transactions[0]) if acc.transactions else None,
                }
                for acc in pmak_accounts
            ],
        }
    except Exception as exc:
        logger.error("Dashboard: PMAK section failed: %s", exc)
        result["pmak"] = {"error": "unavailable"}

    # ── Outside Orders ────────────────────────────────────────────────────────
    try:
        outside_orders = await db.outsideorder.find_many(
            order={"date": "desc"},
            take=10,
        )
        result["outsideOrders"] = {
            "total": len(outside_orders),
            "orders": [
                {
                    "id": o.id,
                    "date": o.date,
                    "clientName": o.clientName,
                    "orderDetails": o.orderDetails,
                    "orderStatus": o.orderStatus, 
                    "orderAmount": float(o.orderAmount),
                    "dueAmount": float(o.dueAmount),
                }
                for o in outside_orders
            ],
        }
    except Exception as exc:
        logger.error("Dashboard: OutsideOrders section failed: %s", exc)
        result["outsideOrders"] = {"error": "unavailable"}

    # ── Dollar Exchange summary ───────────────────────────────────────────────
    try:
        exchange_agg = await db.dollarexchange.aggregate(_sum={"totalBdt": True})
        due_count = await db.dollarexchange.count(where={"paymentStatus": "DUE"})
        result["dollarExchange"] = {
            "totalBdt": float(exchange_agg.sum.totalBdt or Decimal("0")),
            "dueCount": due_count,
        }
    except Exception as exc:
        logger.error("Dashboard: DollarExchange section failed: %s", exc)
        result["dollarExchange"] = {"error": "unavailable"}

    return result


# ── Private serialisation helpers ─────────────────────────────────────────────

def _serialize_fiverr_entry(entry) -> dict:
    return {
        "id": entry.id,
        "date": entry.date,
        "availableWithdraw": float(entry.availableWithdraw),
        "notCleared": float(entry.notCleared),
        "activeOrders": entry.activeOrders,
        "submitted": float(entry.submitted),
        "withdrawn": float(entry.withdrawn),
        "sellerPlus": entry.sellerPlus,
        "promotion": float(entry.promotion),
    }


def _serialize_upwork_entry(entry) -> dict:
    return {
        "id": entry.id,
        "date": entry.date,
        "availableWithdraw": float(entry.availableWithdraw),
        "pending": float(entry.pending),
        "inReview": float(entry.inReview),
        "workInProgress": float(entry.workInProgress),
        "withdrawn": float(entry.withdrawn),
        "connects": entry.connects,        
        "upworkPlus": entry.upworkPlus,
    }


def _serialize_transaction(tx) -> dict:
    return {
        "id": tx.id,
        "date": tx.date,
        "details": tx.details,
        "accountFrom": tx.accountFrom,   
        "accountTo": tx.accountTo,      
        "debit": float(tx.debit),
        "credit": float(tx.credit),
        "remainingBalance": float(tx.remainingBalance),
    }