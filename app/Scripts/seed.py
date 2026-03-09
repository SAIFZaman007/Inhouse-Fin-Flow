"""
MAKTech Financial Flow — Comprehensive Seed Script
====================================================
Seeds ALL models defined in schema.prisma with realistic demo data.

Models covered:
  ✅ User                  (CEO + Director + HR)
  ✅ FiverrProfile         (3 profiles)
  ✅ FiverrEntry           (5 daily snapshots per profile)
  ✅ FiverrOrder           (3 buyer orders per profile)
  ✅ UpworkProfile         (2 profiles)
  ✅ UpworkEntry           (5 daily snapshots per profile)
  ✅ UpworkOrder           (3 client orders per profile)
  ✅ PayoneerAccount       (2 accounts)
  ✅ PayoneerTransaction   (7 ledger entries per account)
  ✅ PmakAccount           (2 accounts)
  ✅ PmakTransaction       (5-7 ledger entries per account)
  ✅ OutsideOrder          (5 client orders, all statuses)
  ✅ DollarExchange        (6 exchange records)
  ✅ CardSharing           (3 cards, card no + CVC encrypted)
  ✅ HrExpense             (8 ledger entries)
  ✅ Inventory             (7 items)

BEHAVIOUR:
  ▶ Every run = full RESET then fresh seed (no stale data ever)
  ▶ All passwords: 123456

Run with:
  poetry run python Scripts/seed.py      (Windows / from project root)
  poetry run python -m scripts.seed      (module style)
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

# ── Path fix: works whether run as script or as module ────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prisma import Prisma
from app.core.security import encrypt_value, hash_password


# ══════════════════════════════════════════════════════════════════════════════
#  CORE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _dt(days_ago: int = 0) -> datetime:
    """
    Return a timezone-aware datetime (UTC midnight) for N days ago.
    Prisma Python requires datetime.datetime — NOT datetime.date.
    Using UTC midnight keeps @db.Date fields consistent.
    """
    base = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return base - timedelta(days=days_ago)


def _pw(plain: str = "123456") -> str:
    """bcrypt-hash a password for storage."""
    return hash_password(str(plain))


# ── Pretty console output ─────────────────────────────────────────────────────

def _header(title: str) -> None:
    bar = "─" * 56
    print(f"\n┌{bar}┐")
    print(f"│  {title:<54}│")
    print(f"└{bar}┘")


def _ok(label: str, detail: str = "") -> None:
    suffix = f"  {detail}" if detail else ""
    print(f"  ✅  {label}{suffix}")


def _del(label: str, count: int) -> None:
    print(f"  🗑   {label:<30} {count} records deleted")


# ══════════════════════════════════════════════════════════════════════════════
#  RESET — always runs first
# ══════════════════════════════════════════════════════════════════════════════

async def reset_all(db: Prisma) -> None:
    """
    Wipe every table in correct dependency order (children before parents).
    Runs automatically on every seed execution.
    """
    _header("🗑  RESET — Clearing All Tables")

    # Order: children first, then parents
    steps = [
        ("Invitation",           db.invitation),
        ("FiverrOrder",          db.fiverrorder),
        ("FiverrEntry",          db.fiverrentry),
        ("FiverrProfile",        db.fiverrprofile),
        ("UpworkOrder",          db.upworkorder),
        ("UpworkEntry",          db.upworkentry),
        ("UpworkProfile",        db.upworkprofile),
        ("PayoneerTransaction",  db.payoneertransaction),
        ("PayoneerAccount",      db.payoneeraccount),
        ("PmakTransaction",      db.pmaktransaction),
        ("PmakAccount",          db.pmakaccount),
        ("OutsideOrder",         db.outsideorder),
        ("DollarExchange",       db.dollarexchange),
        ("CardSharing",          db.cardsharing),
        ("HrExpense",            db.hrexpense),
        ("Inventory",            db.inventory),
        ("User",                 db.user),
    ]
    for name, model in steps:
        n = await model.delete_many()
        _del(name, n)


# ══════════════════════════════════════════════════════════════════════════════
#  USERS
# ══════════════════════════════════════════════════════════════════════════════

async def seed_users(db: Prisma) -> None:
    _header("👤 Users  (password: 123456 for all)")

    users = [
        {
            "name":         "Ariful Islam (CEO)",
            "email":        "ceo@maktech.com",
            "role":         "CEO",
            "passwordHash": _pw("123456"),
            "isActive":     True,
        },
        {
            "name":         "Mahfuz Rahman (Director)",
            "email":        "director@maktech.com",
            "role":         "DIRECTOR",
            "passwordHash": _pw("123456"),
            "isActive":     True,
        },
        {
            "name":         "Nusrat Jahan (HR)",
            "email":        "hr@maktech.com",
            "role":         "HR",
            "passwordHash": _pw("123456"),
            "isActive":     True,
        },
    ]

    for u in users:
        await db.user.create(data=u)
        _ok(f"{u['role']}", f"email={u['email']}  password=123456")


# ══════════════════════════════════════════════════════════════════════════════
#  FIVERR
# ══════════════════════════════════════════════════════════════════════════════

async def seed_fiverr(db: Prisma) -> None:
    """
    3 profiles → 5 daily entries each → 3 orders each.

    Schema field names used exactly:
      FiverrProfile : profileName
      FiverrEntry   : date(datetime), availableWithdraw, notCleared,
                      activeOrders, submitted, withdrawn, sellerPlus, promotion
      FiverrOrder   : date(datetime), buyerName, orderId, amount
    """
    _header("🟢 Fiverr")

    profiles = [
        {
            "profileName": "maktech_design",
            "entries": [
                # (days_ago, avail,   notCleared, activeOrders, submitted, withdrawn, sellerPlus, promotion)
                (0,  1250.00, 320.00, 5, 180.00, 400.00, True,  75.00),
                (1,  1180.00, 295.00, 4, 160.00, 350.00, True,  60.00),
                (2,  1100.00, 250.00, 6, 200.00, 300.00, True,  80.00),
                (3,   980.00, 210.00, 3, 140.00, 250.00, True,  55.00),
                (7,   850.00, 180.00, 2, 120.00, 200.00, False,  0.00),
            ],
            "orders": [
                # (buyerName, orderId, amount, days_ago)
                ("BuyerAlpha",  "FO-2024-0001", 120.00, 1),
                ("BuyerBeta",   "FO-2024-0002",  85.00, 2),
                ("BuyerGamma",  "FO-2024-0003", 200.00, 0),
            ],
        },
        {
            "profileName": "maktech_dev",
            "entries": [
                (0,  2400.00, 580.00, 8, 320.00, 750.00, True,  120.00),
                (1,  2200.00, 510.00, 7, 290.00, 680.00, True,  100.00),
                (2,  2050.00, 460.00, 6, 260.00, 600.00, True,   90.00),
                (3,  1900.00, 400.00, 5, 230.00, 530.00, True,   80.00),
                (7,  1650.00, 330.00, 4, 200.00, 450.00, False,   0.00),
            ],
            "orders": [
                ("DevClient_A", "FO-2024-0010", 350.00, 0),
                ("DevClient_B", "FO-2024-0011", 180.00, 1),
                ("DevClient_C", "FO-2024-0012", 420.00, 2),
            ],
        },
        {
            "profileName": "maktech_seo",
            "entries": [
                (0,  780.00, 190.00, 3, 110.00, 230.00, False, 30.00),
                (1,  720.00, 170.00, 3,  95.00, 200.00, False, 25.00),
                (2,  660.00, 145.00, 2,  80.00, 175.00, False, 20.00),
                (3,  590.00, 120.00, 2,  70.00, 150.00, False, 15.00),
                (7,  510.00,  95.00, 1,  60.00, 120.00, False,  0.00),
            ],
            "orders": [
                ("SEO_ClientX", "FO-2024-0020",  95.00, 0),
                ("SEO_ClientY", "FO-2024-0021", 140.00, 3),
                ("SEO_ClientZ", "FO-2024-0022",  65.00, 1),
            ],
        },
    ]

    for p in profiles:
        profile = await db.fiverrprofile.create(data={"profileName": p["profileName"]})
        _ok(f"FiverrProfile  {p['profileName']}")

        for e in p["entries"]:
            days_ago, avail, not_cleared, active_orders, submitted, withdrawn, seller_plus, promotion = e
            await db.fiverrentry.create(
                data={
                    "profileId":         profile.id,
                    "date":              _dt(days_ago),          # ← datetime.datetime
                    "availableWithdraw": avail,
                    "notCleared":        not_cleared,
                    "activeOrders":      active_orders,
                    "submitted":         submitted,
                    "withdrawn":         withdrawn,
                    "sellerPlus":        seller_plus,
                    "promotion":         promotion,
                }
            )
            _ok(f"  FiverrEntry  {p['profileName']} @ -{days_ago}d", f"avail=${avail}")

        for buyer_name, order_id, amount, days_ago_o in p["orders"]:
            await db.fiverrorder.create(
                data={
                    "profileId": profile.id,
                    "date":      _dt(days_ago_o),               # ← datetime.datetime
                    "buyerName": buyer_name,
                    "orderId":   order_id,
                    "amount":    amount,
                }
            )
            _ok(f"  FiverrOrder  {order_id}", f"buyer={buyer_name}  ${amount}")


# ══════════════════════════════════════════════════════════════════════════════
#  UPWORK
# ══════════════════════════════════════════════════════════════════════════════

async def seed_upwork(db: Prisma) -> None:
    """
    2 profiles → 5 daily entries each → 3 orders each.

    Schema field names used exactly:
      UpworkProfile : profileName
      UpworkEntry   : date(datetime), availableWithdraw, pending, inReview,
                      workInProgress, withdrawn, connects, upworkPlus
      UpworkOrder   : date(datetime), clientName, orderId, amount
    """
    _header("🔵 Upwork")

    profiles = [
        {
            "profileName": "maktech_upwork_main",
            "entries": [
                # (days_ago, avail,   pending,  inReview,  wip,     withdrawn, connects, upworkPlus)
                (0,  3200.00, 480.00, 650.00, 1200.00, 900.00,  80, True),
                (1,  2950.00, 420.00, 580.00, 1100.00, 800.00,  75, True),
                (2,  2700.00, 370.00, 510.00,  980.00, 720.00,  70, True),
                (3,  2450.00, 310.00, 440.00,  860.00, 640.00,  65, True),
                (7,  2100.00, 250.00, 360.00,  720.00, 560.00,  58, True),
            ],
            "orders": [
                # (clientName, orderId, amount, days_ago)
                ("TechStartup Ltd",    "UW-2024-0001", 500.00, 0),
                ("Creative Agency BD", "UW-2024-0002", 320.00, 2),
                ("Global Corp PLC",    "UW-2024-0003", 750.00, 1),
            ],
        },
        {
            "profileName": "maktech_upwork_sub",
            "entries": [
                (0,  1100.00, 220.00, 310.00, 450.00, 380.00, 40, False),
                (1,   980.00, 190.00, 270.00, 400.00, 340.00, 38, False),
                (2,   880.00, 160.00, 230.00, 360.00, 300.00, 35, False),
                (3,   780.00, 130.00, 190.00, 310.00, 260.00, 32, False),
                (7,   650.00, 100.00, 150.00, 250.00, 200.00, 28, False),
            ],
            "orders": [
                ("SmallBiz Owner",   "UW-2024-0010", 180.00, 0),
                ("Freelance Buyer",  "UW-2024-0011",  95.00, 1),
                ("E-commerce Store", "UW-2024-0012", 260.00, 3),
            ],
        },
    ]

    for p in profiles:
        profile = await db.upworkprofile.create(data={"profileName": p["profileName"]})
        _ok(f"UpworkProfile  {p['profileName']}")

        for e in p["entries"]:
            days_ago, avail, pending, in_review, wip, withdrawn, connects, upwork_plus = e
            await db.upworkentry.create(
                data={
                    "profileId":        profile.id,
                    "date":             _dt(days_ago),           # ← datetime.datetime
                    "availableWithdraw": avail,
                    "pending":          pending,
                    "inReview":         in_review,
                    "workInProgress":   wip,
                    "withdrawn":        withdrawn,
                    "connects":         connects,
                    "upworkPlus":       upwork_plus,
                }
            )
            _ok(f"  UpworkEntry  {p['profileName']} @ -{days_ago}d", f"avail=${avail}")

        for client_name, order_id, amount, days_ago_o in p["orders"]:
            await db.upworkorder.create(
                data={
                    "profileId":  profile.id,
                    "date":       _dt(days_ago_o),               # ← datetime.datetime
                    "clientName": client_name,
                    "orderId":    order_id,
                    "amount":     amount,
                }
            )
            _ok(f"  UpworkOrder  {order_id}", f"client={client_name}  ${amount}")


# ══════════════════════════════════════════════════════════════════════════════
#  PAYONEER
# ══════════════════════════════════════════════════════════════════════════════

async def seed_payoneer(db: Prisma) -> None:
    """
    2 accounts → running ledger transactions each.

    Schema field names used exactly:
      PayoneerAccount     : accountName
      PayoneerTransaction : date(datetime), details, accountFrom, accountTo,
                            debit, credit, remainingBalance
    """
    _header("💳 Payoneer")

    accounts = [
        {
            "accountName": "Payoneer - MAKTech Main",
            "transactions": [
                # (days_ago, details,                                    from,            to,              debit,   credit,   balance)
                (30, "Initial deposit from Fiverr withdrawal",   "Fiverr",         "Payoneer Main",    0,      1500.00, 1500.00),
                (25, "Service fee deduction",                    "Payoneer Main",  "Payoneer Fee",    12.50,      0,    1487.50),
                (20, "Received from Upwork withdrawal",          "Upwork",         "Payoneer Main",    0,       900.00, 2387.50),
                (15, "Transfer to PMAK account",                 "Payoneer Main",  "PMAK Main",      800.00,     0,    1587.50),
                (10, "Fiverr monthly withdrawal",                "Fiverr",         "Payoneer Main",    0,      1200.00, 2787.50),
                ( 5, "Exchange to BDT via local agent",          "Payoneer Main",  "Exchanger",      500.00,     0,    2287.50),
                ( 0, "Received from Upwork project",             "Upwork",         "Payoneer Main",    0,       650.00, 2937.50),
            ],
        },
        {
            "accountName": "Payoneer - MAKTech Sub",
            "transactions": [
                (28, "Initial load from card sharing",           "Card Vendor",    "Payoneer Sub",     0,       400.00,  400.00),
                (22, "Subscription payment — Adobe",             "Payoneer Sub",   "Adobe Inc",       54.99,      0,     345.01),
                (18, "Client payment received",                  "Client Overseas","Payoneer Sub",     0,       250.00,  595.01),
                (12, "Tool license renewal",                     "Payoneer Sub",   "Software Co",     89.00,      0,     506.01),
                ( 6, "Top up from Fiverr",                       "Fiverr",         "Payoneer Sub",     0,       300.00,  806.01),
                ( 1, "International transfer fee",               "Payoneer Sub",   "Fee",              5.50,      0,     800.51),
            ],
        },
    ]

    for acc in accounts:
        account = await db.payoneeraccount.create(data={"accountName": acc["accountName"]})
        _ok(f"PayoneerAccount  {acc['accountName']}")

        for tx in acc["transactions"]:
            days_ago, details, acc_from, acc_to, debit, credit, balance = tx
            await db.payoneertransaction.create(
                data={
                    "accountId":        account.id,
                    "date":             _dt(days_ago),           # ← datetime.datetime
                    "details":          details,
                    "accountFrom":      acc_from,
                    "accountTo":        acc_to,
                    "debit":            debit,
                    "credit":           credit,
                    "remainingBalance": balance,
                }
            )
            _ok(f"  PayoneerTx", f"'{details[:40]}'  balance=${balance}")


# ══════════════════════════════════════════════════════════════════════════════
#  PMAK
# ══════════════════════════════════════════════════════════════════════════════

async def seed_pmak(db: Prisma) -> None:
    """
    2 accounts → running ledger transactions each.

    Schema field names used exactly:
      PmakAccount     : accountName
      PmakTransaction : date(datetime), details, accountFrom, accountTo,
                        debit, credit, remainingBalance
    """
    _header("🏦 PMAK")

    accounts = [
        {
            "accountName": "PMAK - Main BDT Account",
            "transactions": [
                # (days_ago, details,                                    from,            to,              debit,    credit,    balance)
                (30, "Fund received from Payoneer exchange",  "Payoneer Main",  "PMAK Main",         0,    88000.00,  88000.00),
                (25, "Office rent payment",                   "PMAK Main",      "Landlord",      25000.00,      0,    63000.00),
                (20, "Salary disbursement - March",           "PMAK Main",      "Staff",         30000.00,      0,    33000.00),
                (15, "New fund from dollar exchange",         "Exchanger",      "PMAK Main",         0,    55000.00,  88000.00),
                (10, "Internet & utilities",                  "PMAK Main",      "DESCO/ISP",      4500.00,      0,    83500.00),
                ( 5, "Equipment purchase",                    "PMAK Main",      "Vendor",        12000.00,      0,    71500.00),
                ( 0, "Top up from Payoneer withdrawal",       "Payoneer Sub",   "PMAK Main",         0,    40000.00, 111500.00),
            ],
        },
        {
            "accountName": "PMAK - Petty Cash",
            "transactions": [
                (28, "Initial allocation from main",          "PMAK Main",      "Petty Cash",        0,    10000.00,  10000.00),
                (21, "Office supplies",                       "Petty Cash",     "Shop",           2500.00,      0,     7500.00),
                (14, "Transport & meals",                     "Petty Cash",     "Staff",          1800.00,      0,     5700.00),
                ( 7, "Replenishment from main",               "PMAK Main",      "Petty Cash",        0,     8000.00,  13700.00),
                ( 2, "Miscellaneous expenses",                "Petty Cash",     "Various",        3200.00,      0,    10500.00),
            ],
        },
    ]

    for acc in accounts:
        account = await db.pmakaccount.create(data={"accountName": acc["accountName"]})
        _ok(f"PmakAccount  {acc['accountName']}")

        for tx in acc["transactions"]:
            days_ago, details, acc_from, acc_to, debit, credit, balance = tx
            await db.pmaktransaction.create(
                data={
                    "accountId":        account.id,
                    "date":             _dt(days_ago),           # ← datetime.datetime
                    "details":          details,
                    "accountFrom":      acc_from,
                    "accountTo":        acc_to,
                    "debit":            debit,
                    "credit":           credit,
                    "remainingBalance": balance,
                }
            )
            _ok(f"  PmakTx", f"'{details[:40]}'  balance=৳{balance:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
#  OUTSIDE ORDERS
# ══════════════════════════════════════════════════════════════════════════════

async def seed_outside_orders(db: Prisma) -> None:
    """
    5 orders covering all three OrderStatus values.

    Schema field names used exactly:
      OutsideOrder: date(datetime), clientId, clientName, clientLink,
                    orderDetails, orderSheet, assignTeam, orderStatus,
                    orderAmount, receiveAmount, dueAmount,
                    paymentMethod, paymentMethodDetails
    """
    _header("📦 Outside Orders")

    orders = [
        {
            "date":                _dt(25),                      # ← datetime.datetime
            "clientId":            "CLT-001",
            "clientName":          "Rahman Enterprise",
            "clientLink":          "https://facebook.com/rahmanenterprise",
            "orderDetails":        "Full website redesign with SEO optimization and 6-month support",
            "orderSheet":          None,
            "assignTeam":          "Design & Dev Team",
            "orderStatus":         "COMPLETED",
            "orderAmount":         85000.00,
            "receiveAmount":       85000.00,
            "dueAmount":           0.00,
            "paymentMethod":       "Bank Transfer",
            "paymentMethodDetails":"Dutch Bangla Bank  A/C: 1234567890",
        },
        {
            "date":                _dt(15),
            "clientId":            "CLT-002",
            "clientName":          "Karim Solutions Ltd",
            "clientLink":          "https://linkedin.com/company/karim-solutions",
            "orderDetails":        "Social media management — 3 platforms, 30 posts/month",
            "orderSheet":          None,
            "assignTeam":          "Marketing Team",
            "orderStatus":         "IN_PROGRESS",
            "orderAmount":         45000.00,
            "receiveAmount":       22500.00,
            "dueAmount":           22500.00,
            "paymentMethod":       "bKash",
            "paymentMethodDetails":"bKash Personal: 01712-345678",
        },
        {
            "date":                _dt(8),
            "clientId":            "CLT-003",
            "clientName":          "Hasan Digital Agency",
            "clientLink":          "mailto:hasan@digitalagency.com",
            "orderDetails":        "WordPress e-commerce site with payment gateway integration",
            "orderSheet":          None,
            "assignTeam":          "Dev Team",
            "orderStatus":         "PENDING",
            "orderAmount":         60000.00,
            "receiveAmount":       15000.00,
            "dueAmount":           45000.00,
            "paymentMethod":       "Nagad",
            "paymentMethodDetails":"Nagad Business: 01812-456789",
        },
        {
            "date":                _dt(20),
            "clientId":            "CLT-004",
            "clientName":          "Taslim Brothers Import",
            "clientLink":          "+8801911-234567",
            "orderDetails":        "Product photography — 200 SKUs, edited and delivered in 5 days",
            "orderSheet":          None,
            "assignTeam":          "Design Team",
            "orderStatus":         "COMPLETED",
            "orderAmount":         18000.00,
            "receiveAmount":       18000.00,
            "dueAmount":           0.00,
            "paymentMethod":       "Cash",
            "paymentMethodDetails":"Cash payment at office",
        },
        {
            "date":                _dt(5),
            "clientId":            "CLT-005",
            "clientName":          "BDTech Startup Hub",
            "clientLink":          "https://bdtechhub.com",
            "orderDetails":        "Mobile app UI/UX design — 40 screens, Figma deliverable",
            "orderSheet":          None,
            "assignTeam":          "Design Team",
            "orderStatus":         "IN_PROGRESS",
            "orderAmount":         75000.00,
            "receiveAmount":       37500.00,
            "dueAmount":           37500.00,
            "paymentMethod":       "Bank Transfer",
            "paymentMethodDetails":"BRAC Bank  A/C: 9876543210",
        },
    ]

    for o in orders:
        await db.outsideorder.create(data=o)
        _ok(
            f"OutsideOrder  {o['clientId']}",
            f"{o['clientName']}  ৳{o['orderAmount']:,.0f}  [{o['orderStatus']}]",
        )


# ══════════════════════════════════════════════════════════════════════════════
#  DOLLAR EXCHANGE
# ══════════════════════════════════════════════════════════════════════════════

async def seed_dollar_exchange(db: Prisma) -> None:
    """
    6 exchange records — mix of RECEIVED and DUE.

    Schema field names used exactly:
      DollarExchange: date(datetime), details, accountFrom, accountTo,
                      debit, credit, rate, totalBdt, paymentStatus
    totalBdt = exchange_amount × rate  (computed here before insert)
    """
    _header("💱 Dollar Exchange")

    exchanges = [
        # (days_ago, details,                                  from,            to,               debit,   credit,  rate,    status)
        (28, "Sold $500 to local exchanger — Motijheel", "Payoneer Main", "Exchanger Kamal", 500.00,    0,    109.50, "RECEIVED"),
        (21, "Sold $300 to broker — Gulshan",            "Payoneer Main", "Broker Rahim",    300.00,    0,    110.00, "RECEIVED"),
        (15, "Sold $800 — rate locked before weekend",   "Payoneer Sub",  "Exchanger Hasan", 800.00,    0,    109.75, "RECEIVED"),
        ( 9, "Bought $200 — emergency rate",             "Exchanger Ali", "Payoneer Main",      0,  200.00, 111.00, "RECEIVED"),
        ( 4, "Sold $600 to preferred broker",            "Payoneer Main", "Broker Salam",    600.00,    0,    110.25, "DUE"),
        ( 0, "Sold $1000 — today's rate",                "Payoneer Main", "Exchanger Kamal",1000.00,   0,    110.50, "DUE"),
    ]

    for ex in exchanges:
        days_ago, details, acc_from, acc_to, debit, credit, rate, status = ex
        exchange_amount = credit if credit > 0 else debit
        total_bdt = round(exchange_amount * rate, 2)

        await db.dollarexchange.create(
            data={
                "date":          _dt(days_ago),              # ← datetime.datetime
                "details":       details,
                "accountFrom":   acc_from,
                "accountTo":     acc_to,
                "debit":         debit,
                "credit":        credit,
                "rate":          rate,
                "totalBdt":      total_bdt,
                "paymentStatus": status,
            }
        )
        _ok(
            f"DollarExchange",
            f"${exchange_amount:.0f} × {rate} = ৳{total_bdt:,.2f}  [{status}]",
        )


# ══════════════════════════════════════════════════════════════════════════════
#  CARD SHARING
# ══════════════════════════════════════════════════════════════════════════════

async def seed_card_sharing(db: Prisma) -> None:
    """
    3 cards. cardNo and cardCvc are Fernet-encrypted before DB insert.

    Schema field names used exactly:
      CardSharing: serialNo(String), details, payoneerAccount,
                   cardNo(encrypted), cardExpire, cardCvc(encrypted),
                   cardVendor, cardLimit, cardPaymentRcv,
                   cardRcvBank, mailDetails, screenshotPath
    """
    _header("🃏 Card Sharing  (card no & CVC encrypted)")

    cards = [
        {
            "serialNo":        "CS-001",
            "details":         "Primary virtual card for tool subscriptions",
            "payoneerAccount": "Payoneer - MAKTech Main",
            "cardNo":          "4111111111111111",   # plain — encrypted below
            "cardExpire":      "09/26",
            "cardCvc":         "123",                # plain — encrypted below
            "cardVendor":      "Notion, Canva, Figma",
            "cardLimit":       500.00,
            "cardPaymentRcv":  320.00,
            "cardRcvBank":     "Payoneer Main Balance",
            "mailDetails":     "cards@maktech.com",
            "screenshotPath":  None,
        },
        {
            "serialNo":        "CS-002",
            "details":         "Secondary card for ads — Facebook & Google",
            "payoneerAccount": "Payoneer - MAKTech Sub",
            "cardNo":          "5500000000000004",
            "cardExpire":      "12/25",
            "cardCvc":         "456",
            "cardVendor":      "Facebook Ads, Google Ads",
            "cardLimit":       1000.00,
            "cardPaymentRcv":  875.00,
            "cardRcvBank":     "Payoneer Sub Balance",
            "mailDetails":     "ads@maktech.com",
            "screenshotPath":  None,
        },
        {
            "serialNo":        "CS-003",
            "details":         "Emergency backup — Director access only",
            "payoneerAccount": "Payoneer - MAKTech Main",
            "cardNo":          "378282246310005",
            "cardExpire":      "06/27",
            "cardCvc":         "789",
            "cardVendor":      "Emergency Use",
            "cardLimit":       250.00,
            "cardPaymentRcv":  0.00,
            "cardRcvBank":     None,
            "mailDetails":     "backup@maktech.com",
            "screenshotPath":  None,
        },
    ]

    for c in cards:
        await db.cardsharing.create(
            data={
                "serialNo":        c["serialNo"],
                "details":         c["details"],
                "payoneerAccount": c["payoneerAccount"],
                "cardNo":          encrypt_value(c["cardNo"]),   # Fernet encrypted
                "cardExpire":      c["cardExpire"],
                "cardCvc":         encrypt_value(c["cardCvc"]),  # Fernet encrypted
                "cardVendor":      c["cardVendor"],
                "cardLimit":       c["cardLimit"],
                "cardPaymentRcv":  c["cardPaymentRcv"],
                "cardRcvBank":     c["cardRcvBank"],
                "mailDetails":     c["mailDetails"],
                "screenshotPath":  c["screenshotPath"],
            }
        )
        _ok(
            f"CardSharing  {c['serialNo']}",
            f"vendor={c['cardVendor'][:28]}  limit=${c['cardLimit']}  [ENCRYPTED]",
        )


# ══════════════════════════════════════════════════════════════════════════════
#  HR EXPENSE
# ══════════════════════════════════════════════════════════════════════════════

async def seed_hr_expense(db: Prisma) -> None:
    """
    8 HR ledger entries with a running balance.

    Schema field names used exactly:
      HrExpense: date(datetime), details, accountFrom, accountTo,
                 debit, credit, remainingBalance
    """
    _header("💰 HR Expense")

    expenses = [
        # (days_ago, details,                              from,        to,              debit,    credit,    balance)
        (30, "March salary — Nusrat Jahan (HR)",     "PMAK Main", "HR Nusrat",    18000.00,     0,    82000.00),
        (30, "March salary — Rahim (Developer)",     "PMAK Main", "Dev Rahim",    22000.00,     0,    60000.00),
        (30, "March salary — Karim (Designer)",      "PMAK Main", "Designer Karim",20000.00,    0,    40000.00),
        (25, "Festival bonus — all staff",           "PMAK Main", "All Staff",    15000.00,     0,    25000.00),
        (20, "Medical allowance reimbursement",      "PMAK Main", "HR Nusrat",     2500.00,     0,    22500.00),
        (15, "April advance salary — emergency",     "PMAK Main", "Dev Rahim",     5000.00,     0,    17500.00),
        ( 7, "Performance bonus — Karim",            "PMAK Main", "Designer Karim", 3000.00,    0,    14500.00),
        ( 0, "Fund allocated for April salaries",    "PMAK Main", "HR Fund",           0,   60000.00, 74500.00),
    ]

    for exp in expenses:
        days_ago, details, acc_from, acc_to, debit, credit, balance = exp
        await db.hrexpense.create(
            data={
                "date":             _dt(days_ago),               # ← datetime.datetime
                "details":          details,
                "accountFrom":      acc_from,
                "accountTo":        acc_to,
                "debit":            debit,
                "credit":           credit,
                "remainingBalance": balance,
            }
        )
        _ok(f"HrExpense", f"'{details[:42]}'  balance=৳{balance:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
#  INVENTORY
# ══════════════════════════════════════════════════════════════════════════════

async def seed_inventory(db: Prisma) -> None:
    """
    7 inventory items across multiple categories.
    totalPrice = quantity × unitPrice  (computed, then stored).

    Schema field names used exactly:
      Inventory: date(datetime), itemName, category, quantity,
                 unitPrice, totalPrice, condition, assignedTo, notes
    """
    _header("📋 Inventory")

    items = [
        # (days_ago, itemName,                              category,     qty, unitPrice,  condition, assignedTo,     notes)
        (60,  "Apple MacBook Pro 14\" M3",           "Hardware",    2, 195000.00, "New",    "Dev Team",    "Primary dev machines — March 2024"),
        (55,  "Dell 27\" 4K Monitor",                "Hardware",    4,  42000.00, "New",    "All Team",    "One per workstation"),
        (55,  "Logitech MX Master 3 Mouse",          "Accessories", 5,   8500.00, "New",    "All Team",    "Wireless ergonomic mouse"),
        (90,  "Adobe Creative Cloud — Annual",       "Software",    3,  28000.00, "Active", "Design Team", "Renewed Jan 2024 — expires Jan 2025"),
        (120, "Office Desk (L-Shape)",               "Furniture",   3,  18500.00, "Good",   "Office",      "New office setup"),
        (30,  "TP-Link Wi-Fi 6 Router AX3000",       "Network",     1,  12000.00, "New",    "Office",      "Main office router — replaces old unit"),
        (45,  "UPS Battery Backup 1500VA",           "Hardware",    2,  14500.00, "New",    "Office",      "Power backup for critical workstations"),
    ]

    for item in items:
        days_ago, item_name, category, qty, unit_price, condition, assigned_to, notes = item
        total = round(qty * unit_price, 2)

        await db.inventory.create(
            data={
                "date":        _dt(days_ago),                    # ← datetime.datetime
                "itemName":    item_name,
                "category":    category,
                "quantity":    qty,
                "unitPrice":   unit_price,
                "totalPrice":  total,
                "condition":   condition,
                "assignedTo":  assigned_to,
                "notes":       notes,
            }
        )
        _ok(f"Inventory", f"'{item_name[:36]}'  qty={qty}  total=৳{total:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

async def print_summary(db: Prisma) -> None:
    _header("📊 Final Record Counts")

    rows = [
        ("Users",                 await db.user.count()),
        ("Fiverr Profiles",       await db.fiverrprofile.count()),
        ("Fiverr Entries",        await db.fiverrentry.count()),
        ("Fiverr Orders",         await db.fiverrorder.count()),
        ("Upwork Profiles",       await db.upworkprofile.count()),
        ("Upwork Entries",        await db.upworkentry.count()),
        ("Upwork Orders",         await db.upworkorder.count()),
        ("Payoneer Accounts",     await db.payoneeraccount.count()),
        ("Payoneer Transactions", await db.payoneertransaction.count()),
        ("PMAK Accounts",         await db.pmakaccount.count()),
        ("PMAK Transactions",     await db.pmaktransaction.count()),
        ("Outside Orders",        await db.outsideorder.count()),
        ("Dollar Exchanges",      await db.dollarexchange.count()),
        ("Card Sharing",          await db.cardsharing.count()),
        ("HR Expenses",           await db.hrexpense.count()),
        ("Inventory Items",       await db.inventory.count()),
        ("Invitations",           await db.invitation.count()),
    ]

    total = 0
    for label, count in rows:
        print(f"  · {label:<28} {count:>4} records")
        total += count
    print(f"  {'─' * 40}")
    print(f"  {'TOTAL':<28} {total:>4} records")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║     MAKTech Financial Flow — Database Seeder         ║")
    print("╠══════════════════════════════════════════════════════╣")
    print("║  MODE: RESET → fresh seed on every run              ║")
    print("║  Passwords: 123456  (all accounts)                   ║")
    print("╚══════════════════════════════════════════════════════╝")

    db = Prisma()
    await db.connect()

    try:
        # ── Always reset first — no stale data ever ───────────────────────
        await reset_all(db)

        # ── Seed in dependency order ──────────────────────────────────────
        await seed_users(db)
        await seed_fiverr(db)
        await seed_upwork(db)
        await seed_payoneer(db)
        await seed_pmak(db)
        await seed_outside_orders(db)
        await seed_dollar_exchange(db)
        await seed_card_sharing(db)
        await seed_hr_expense(db)
        await seed_inventory(db)

        # ── Summary ───────────────────────────────────────────────────────
        await print_summary(db)

        print()
        print("╔══════════════════════════════════════════════════════╗")
        print("║  ✅  Done! Database is fresh and ready.              ║")
        print("╠══════════════════════════════════════════════════════╣")
        print("║  CEO      →  ceo@maktech.com        /  123456        ║")
        print("║  Director →  director@maktech.com   /  123456        ║")
        print("║  HR       →  hr@maktech.com         /  123456        ║")
        print("║                                                      ║")
        print("║  API Docs →  https://fin-flow.maktechlaravel.cloud   ║")
        print("╚══════════════════════════════════════════════════════╝")
        print()

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())