"""
MAKTech Financial Flow — Database Seeder
=========================================
Comprehensive seed for ALL models in schema.prisma with realistic demo data.

Models covered:
  ✅ User                  (CEO · Director · HR · BDev)
  ✅ FiverrProfile         (3 profiles)
  ✅ FiverrEntry           (5 daily snapshots per profile — all 9 fields)
  ✅ FiverrOrder           (4 orders per profile — buyerName, orderId, amount)
  ✅ UpworkProfile         (2 profiles)
  ✅ UpworkEntry           (5 daily snapshots per profile — all 8 fields)
  ✅ UpworkOrder           (4 orders per profile — clientName, orderId, amount)
  ✅ PayoneerAccount       (2 accounts)
  ✅ PayoneerTransaction   (7 ledger entries per account — all fields)
  ✅ PmakAccount           (2 accounts)
  ✅ PmakTransaction       (7 entries — all fields incl. status/notes/buyer/seller)
  ✅ OutsideOrder          (6 orders — all 13 schema fields, all statuses covered)
  ✅ DollarExchange        (6 records — paymentStatus: RECEIVED | DUE)
  ✅ DailyRate             (5 HR-managed USD→BDT rates)
  ✅ CardSharing           (3 cards — cardNo + cardCvc Fernet-encrypted)
  ✅ HrExpense             (11 ledger entries — 3 temporal windows: historical/last-month/this-month)
  ✅ Inventory             (12 items — 3 temporal windows: historical/last-month/this-month)

BEHAVIOUR:
  Every run = full RESET then fresh seed (no stale data ever).
  All passwords: 123456.
  Date fields always use datetime.datetime (UTC midnight) — never date.
  prisma-client-py JSON builder cannot serialise bare date objects.

Run with:
  poetry run python app/Scripts/seed.py     (direct, from project root)
  poetry run python -m app.Scripts.seed     (module, from project root)
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

# ── Path fix ──────────────────────────────────────────────────────────────────
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from prisma import Prisma
from app.core.security import encrypt_value, hash_password


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _dt(days_ago: int = 0) -> datetime:
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return base - timedelta(days=days_ago)


def _pw(plain: str = "123456") -> str:
    return hash_password(str(plain))


def _header(title: str) -> None:
    bar = "─" * 58
    print(f"\n┌{bar}┐")
    print(f"│  {title:<56}│")
    print(f"└{bar}┘")


def _ok(label: str, detail: str = "") -> None:
    print(f"  ✅  {label}{'  ' + detail if detail else ''}")


def _del(label: str, count: int) -> None:
    print(f"  🗑   {label:<32} {count} records deleted")


# ══════════════════════════════════════════════════════════════════════════════
#  RESET
# ══════════════════════════════════════════════════════════════════════════════

async def reset_all(db: Prisma) -> None:
    _header("🗑  RESET — Clearing All Tables")
    for name, model in [
        ("Invitation",           db.invitation),
        ("DailyRate",            db.dailyrate),
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
    ]:
        _del(name, await model.delete_many())


# ══════════════════════════════════════════════════════════════════════════════
#  USERS
# ══════════════════════════════════════════════════════════════════════════════

async def seed_users(db: Prisma) -> None:
    _header("👤 Users  (password: 123456 for all)")
    for u in [
        {"name": "Ariful Islam (CEO)",       "email": "ceo@maktech.com",      "role": "CEO",      "passwordHash": _pw(), "isActive": True},
        {"name": "Mahfuz Rahman (Director)",  "email": "director@maktech.com", "role": "DIRECTOR", "passwordHash": _pw(), "isActive": True},
        {"name": "Nusrat Jahan (HR)",         "email": "hr@maktech.com",       "role": "HR",       "passwordHash": _pw(), "isActive": True},
        {"name": "Tanvir Ahmed (BDev)",       "email": "bdev@maktech.com",     "role": "BDEV",     "passwordHash": _pw(), "isActive": True},
    ]:
        await db.user.create(data=u)
        _ok(u["role"], f"email={u['email']}  password=123456")


# ══════════════════════════════════════════════════════════════════════════════
#  FIVERR
# ══════════════════════════════════════════════════════════════════════════════

async def seed_fiverr(db: Prisma) -> None:
    """
    3 profiles × 5 entries × 4 orders.
    FiverrEntry  ALL fields: date, profileId, availableWithdraw, notCleared,
                             activeOrders, submitted, withdrawn, sellerPlus, promotion
    FiverrOrder  ALL fields: date, profileId, buyerName, orderId, amount
    """
    _header("🟢 Fiverr")

    profiles = [
        {
            "profileName": "maktech_design",
            "entries": [
                # (days_ago, avail,    notCleared, activeOrders, submitted, withdrawn, sellerPlus, promotion)
                (0,  1250.00,  320.00, 5, 180.00, 400.00, True,  75.00),
                (1,  1180.00,  295.00, 4, 160.00, 350.00, True,  60.00),
                (2,  1100.00,  250.00, 6, 200.00, 300.00, True,  80.00),
                (3,   980.00,  210.00, 3, 140.00, 250.00, True,  55.00),
                (7,   850.00,  180.00, 2, 120.00, 200.00, False,  0.00),
            ],
            "orders": [
                # (buyerName,     orderId,          amount, days_ago)
                ("BuyerAlpha",    "FO-2024-D001",   120.00, 1),
                ("BuyerBeta",     "FO-2024-D002",    85.00, 2),
                ("BuyerGamma",    "FO-2024-D003",   200.00, 0),
                ("BuyerDelta",    "FO-2024-D004",   150.00, 4),
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
                ("DevClient_A",   "FO-2024-V001",   350.00, 0),
                ("DevClient_B",   "FO-2024-V002",   180.00, 1),
                ("DevClient_C",   "FO-2024-V003",   420.00, 2),
                ("DevClient_D",   "FO-2024-V004",   275.00, 5),
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
                ("SEO_ClientX",   "FO-2024-S001",    95.00, 0),
                ("SEO_ClientY",   "FO-2024-S002",   140.00, 3),
                ("SEO_ClientZ",   "FO-2024-S003",    65.00, 1),
                ("SEO_ClientW",   "FO-2024-S004",   110.00, 6),
            ],
        },
    ]

    for p in profiles:
        profile = await db.fiverrprofile.create(data={"profileName": p["profileName"]})
        _ok(f"FiverrProfile  {p['profileName']}")

        for days_ago, avail, not_cleared, active_orders, submitted, withdrawn, seller_plus, promo in p["entries"]:
            await db.fiverrentry.create(data={
                "profileId":         profile.id,
                "date":              _dt(days_ago),
                "availableWithdraw": avail,
                "notCleared":        not_cleared,
                "activeOrders":      active_orders,
                "submitted":         submitted,
                "withdrawn":         withdrawn,
                "sellerPlus":        seller_plus,
                "promotion":         promo,
            })
            _ok(f"  FiverrEntry  {p['profileName']} @-{days_ago}d", f"avail=${avail}")

        for buyer_name, order_id, amount, days_ago_o in p["orders"]:
            await db.fiverrorder.create(data={
                "profileId": profile.id,
                "date":      _dt(days_ago_o),
                "buyerName": buyer_name,
                "orderId":   order_id,
                "amount":    amount,
            })
            _ok(f"  FiverrOrder  {order_id}", f"buyer={buyer_name}  ${amount}")


# ══════════════════════════════════════════════════════════════════════════════
#  UPWORK
# ══════════════════════════════════════════════════════════════════════════════

async def seed_upwork(db: Prisma) -> None:
    """
    2 profiles × 5 entries × 4 orders.
    UpworkEntry  ALL fields: date, profileId, availableWithdraw, pending, inReview,
                             workInProgress, withdrawn, connects, upworkPlus
    UpworkOrder  ALL fields: date, profileId, clientName, orderId, amount
    """
    _header("🔵 Upwork")

    profiles = [
        {
            "profileName": "maktech_upwork_main",
            "entries": [
                # (days_ago, avail,    pending,  inReview, wip,      withdrawn, connects, upworkPlus)
                (0,  3200.00, 480.00, 650.00, 1200.00, 900.00,  80, True),
                (1,  2950.00, 420.00, 580.00, 1100.00, 800.00,  75, True),
                (2,  2700.00, 370.00, 510.00,  980.00, 720.00,  70, True),
                (3,  2450.00, 310.00, 440.00,  860.00, 640.00,  65, True),
                (7,  2100.00, 250.00, 360.00,  720.00, 560.00,  58, True),
            ],
            "orders": [
                # (clientName,              orderId,          amount,  days_ago)
                ("TechStartup Ltd",          "UW-2024-M001",  500.00, 0),
                ("Creative Agency BD",       "UW-2024-M002",  320.00, 2),
                ("Global Corp PLC",          "UW-2024-M003",  750.00, 1),
                ("Innovation Labs Inc",      "UW-2024-M004",  410.00, 5),
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
                ("SmallBiz Owner",           "UW-2024-S001",  180.00, 0),
                ("Freelance Buyer",          "UW-2024-S002",   95.00, 1),
                ("E-commerce Store",         "UW-2024-S003",  260.00, 3),
                ("Retail Brand BD",          "UW-2024-S004",  145.00, 6),
            ],
        },
    ]

    for p in profiles:
        profile = await db.upworkprofile.create(data={"profileName": p["profileName"]})
        _ok(f"UpworkProfile  {p['profileName']}")

        for days_ago, avail, pending, in_review, wip, withdrawn, connects, upwork_plus in p["entries"]:
            await db.upworkentry.create(data={
                "profileId":         profile.id,
                "date":              _dt(days_ago),
                "availableWithdraw": avail,
                "pending":           pending,
                "inReview":          in_review,
                "workInProgress":    wip,
                "withdrawn":         withdrawn,
                "connects":          connects,
                "upworkPlus":        upwork_plus,
            })
            _ok(f"  UpworkEntry  {p['profileName']} @-{days_ago}d", f"avail=${avail}")

        for client_name, order_id, amount, days_ago_o in p["orders"]:
            await db.upworkorder.create(data={
                "profileId":  profile.id,
                "date":       _dt(days_ago_o),
                "clientName": client_name,
                "orderId":    order_id,
                "amount":     amount,
            })
            _ok(f"  UpworkOrder  {order_id}", f"client={client_name}  ${amount}")


# ══════════════════════════════════════════════════════════════════════════════
#  PAYONEER
# ══════════════════════════════════════════════════════════════════════════════

async def seed_payoneer(db: Prisma) -> None:
    """
    2 accounts × 7 transactions.
    PayoneerTransaction ALL fields: date, accountId, details, accountFrom,
                                    accountTo, debit, credit, remainingBalance
    """
    _header("💳 Payoneer")

    accounts = [
        {
            "accountName": "Payoneer - MAKTech Main",
            "transactions": [
                # (days_ago, details,                                            from,                   to,                  debit,   credit,   balance)
                (30, "Initial deposit from Fiverr withdrawal",          "Fiverr maktech_design",  "Payoneer Main",      0.00,  1500.00, 1500.00),
                (25, "Service fee deduction",                           "Payoneer Main",           "Payoneer Fee",      12.50,     0.00, 1487.50),
                (20, "Received from Upwork withdrawal",                 "Upwork maktech_main",     "Payoneer Main",      0.00,   900.00, 2387.50),
                (15, "Transfer to PMAK Main account",                   "Payoneer Main",           "PMAK Main",        800.00,     0.00, 1587.50),
                (10, "Fiverr monthly withdrawal — dev profile",         "Fiverr maktech_dev",      "Payoneer Main",      0.00,  1200.00, 2787.50),
                ( 5, "Exchange to BDT via local agent",                 "Payoneer Main",           "Exchanger Kamal",  500.00,     0.00, 2287.50),
                ( 0, "Received from Upwork project completion",         "Upwork maktech_main",     "Payoneer Main",      0.00,   650.00, 2937.50),
            ],
        },
        {
            "accountName": "Payoneer - MAKTech Sub",
            "transactions": [
                (28, "Initial load from card sharing deposit",          "Card Vendor",             "Payoneer Sub",       0.00,   400.00,  400.00),
                (22, "Subscription — Adobe Creative Cloud",             "Payoneer Sub",            "Adobe Inc",         54.99,     0.00,  345.01),
                (18, "Client payment received — overseas",              "Client Overseas",         "Payoneer Sub",       0.00,   250.00,  595.01),
                (12, "Tool license renewal — dev tools",                "Payoneer Sub",            "Software Co",       89.00,     0.00,  506.01),
                ( 6, "Top up from Fiverr SEO profile",                  "Fiverr maktech_seo",      "Payoneer Sub",       0.00,   300.00,  806.01),
                ( 1, "International transfer fee",                      "Payoneer Sub",            "Payoneer Fee",       5.50,     0.00,  800.51),
                ( 0, "Upwork sub-profile withdrawal",                   "Upwork maktech_sub",      "Payoneer Sub",       0.00,   195.00,  995.51),
            ],
        },
    ]

    for acc in accounts:
        account = await db.payoneeraccount.create(data={"accountName": acc["accountName"], "isActive": True})
        _ok(f"PayoneerAccount  {acc['accountName']}")

        for days_ago, details, acc_from, acc_to, debit, credit, balance in acc["transactions"]:
            await db.payoneertransaction.create(data={
                "accountId":        account.id,
                "date":             _dt(days_ago),
                "details":          details,
                "accountFrom":      acc_from,
                "accountTo":        acc_to,
                "debit":            debit,
                "credit":           credit,
                "remainingBalance": balance,
            })
            _ok(f"  PayoneerTx", f"'{details[:44]}'  balance=${balance:,.2f}")


# ══════════════════════════════════════════════════════════════════════════════
#  PMAK
# ══════════════════════════════════════════════════════════════════════════════

async def seed_pmak(db: Prisma) -> None:
    """
    2 accounts × 7 transactions.
    PmakTransaction ALL fields: date, accountId, details, accountFrom, accountTo,
                                debit, credit, remainingBalance, status, notes, buyer, seller
    """
    _header("🏦 PMAK")

    accounts = [
        {
            "accountName": "PMAK - Main BDT Account",
            "transactions": [
                # (days_ago, details,                               from,              to,           debit,     credit,     balance,    status,      notes,                                    buyer,              seller)
                (30, "Fund received from Payoneer exchange",    "Payoneer Main",  "PMAK Main",       0.00,  88000.00,  88000.00, "CLEARED",  "Verified against Payoneer statement",    None,               "Exchanger Kamal"),
                (25, "Office rent payment — March",             "PMAK Main",      "Landlord",    25000.00,      0.00,  63000.00, "CLEARED",  "March rent — receipt on file",           "MAKTech Office",   "Landlord Rahim"),
                (20, "Salary disbursement — March payroll",     "PMAK Main",      "Staff",       30000.00,      0.00,  33000.00, "CLEARED",  "3 staff — HR approved Mar payroll",      "HR Department",    "Staff Accounts"),
                (15, "New fund from dollar exchange broker",    "Exchanger",      "PMAK Main",       0.00,  55000.00,  88000.00, "CLEARED",  "Rate 110 BDT/USD — receipt attached",    None,               "Broker Salam"),
                (10, "Internet & utilities — March",            "PMAK Main",      "DESCO/ISP",    4500.00,      0.00,  83500.00, "CLEARED",  "March utility bills — all paid",         "MAKTech Office",   "DESCO & ISP"),
                ( 5, "Equipment purchase — pending delivery",   "PMAK Main",      "Tech Vendor",  12000.00,     0.00,  71500.00, "ON_HOLD",  "Awaiting delivery confirmation",         "MAKTech Office",   "Tech Vendor Ltd"),
                ( 0, "Top up from Payoneer Sub withdrawal",     "Payoneer Sub",   "PMAK Main",       0.00,  40000.00, 111500.00, "PENDING",  "Pending BDev verification",              None,               "Exchanger Hasan"),
            ],
        },
        {
            "accountName": "PMAK - Petty Cash",
            "transactions": [
                (28, "Initial allocation from main account",    "PMAK Main",      "Petty Cash",      0.00,  10000.00,  10000.00, "CLEARED",  "Approved by Director — Q1 petty cash",   "PMAK Main",        None),
                (21, "Office supplies — stationery & printer",  "Petty Cash",     "Shop",         2500.00,      0.00,   7500.00, "CLEARED",  "Stationery and printer cartridges",      "MAKTech Office",   "Office Supplies BD"),
                (14, "Transport & meals — client visit",        "Petty Cash",     "Staff",        1800.00,      0.00,   5700.00, "CLEARED",  "Client visit Gulshan + team lunch",      "Sales Team",       "Various"),
                ( 7, "Replenishment from main — approved",      "PMAK Main",      "Petty Cash",      0.00,   8000.00,  13700.00, "CLEARED",  "Approved by HR — standard top-up",       "PMAK Main",        None),
                ( 4, "Emergency IT repair — laptop screen",     "Petty Cash",     "Tech Shop",    3200.00,      0.00,  10500.00, "CLEARED",  "Laptop screen replacement — Dev Rahim",  "MAKTech Office",   "Tech Repair Dhaka"),
                ( 1, "Courier & shipping charges",              "Petty Cash",     "Courier",       850.00,      0.00,   9650.00, "PENDING",  "Awaiting BDev status update",            "MAKTech Office",   "Sundarban Courier"),
                ( 0, "Miscellaneous — pending review",          "Petty Cash",     "Various",      1200.00,      0.00,   8450.00, "PENDING",  "BDev to verify receipts this week",      "Office Admin",     "Various Vendors"),
            ],
        },
    ]

    for acc in accounts:
        account = await db.pmakaccount.create(data={"accountName": acc["accountName"], "isActive": True})
        _ok(f"PmakAccount  {acc['accountName']}")

        for (days_ago, details, acc_from, acc_to,
             debit, credit, balance, status, notes, buyer, seller) in acc["transactions"]:
            await db.pmaktransaction.create(data={
                "accountId":        account.id,
                "date":             _dt(days_ago),
                "details":          details,
                "accountFrom":      acc_from,
                "accountTo":        acc_to,
                "debit":            debit,
                "credit":           credit,
                "remainingBalance": balance,
                "status":           status,
                "notes":            notes,
                "buyer":            buyer,
                "seller":           seller,
            })
            _ok(f"  PmakTx", f"'{details[:40]}'  [{status}]  balance=৳{balance:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
#  OUTSIDE ORDERS
# ══════════════════════════════════════════════════════════════════════════════

async def seed_outside_orders(db: Prisma) -> None:
    """
    6 orders — ALL OrderStatus values: COMPLETED, IN_PROGRESS, PENDING, CANCELLED.
    OutsideOrder ALL 13 fields.
    """
    _header("📦 Outside Orders")

    orders = [
        {
            "date":                 _dt(25),
            "clientId":             "CLT-001",
            "clientName":           "Rahman Enterprise",
            "clientLink":           "https://facebook.com/rahmanenterprise",
            "orderDetails":         "Full website redesign with SEO optimisation and 6-month technical support",
            "orderSheet":           None,
            "assignTeam":           "Design & Dev Team",
            "orderStatus":          "COMPLETED",
            "orderAmount":          85000.00,
            "receiveAmount":        85000.00,
            "dueAmount":            0.00,
            "paymentMethod":        "Bank Transfer",
            "paymentMethodDetails": "Dutch Bangla Bank  A/C: 1234567890",
        },
        {
            "date":                 _dt(15),
            "clientId":             "CLT-002",
            "clientName":           "Karim Solutions Ltd",
            "clientLink":           "https://linkedin.com/company/karim-solutions",
            "orderDetails":         "Social media management — 3 platforms, 30 posts/month, analytics reporting",
            "orderSheet":           None,
            "assignTeam":           "Marketing Team",
            "orderStatus":          "IN_PROGRESS",
            "orderAmount":          45000.00,
            "receiveAmount":        22500.00,
            "dueAmount":            22500.00,
            "paymentMethod":        "bKash",
            "paymentMethodDetails": "bKash Personal: 01712-345678",
        },
        {
            "date":                 _dt(8),
            "clientId":             "CLT-003",
            "clientName":           "Hasan Digital Agency",
            "clientLink":           "mailto:hasan@digitalagency.com",
            "orderDetails":         "WordPress e-commerce site with WooCommerce + bKash/Nagad payment gateway",
            "orderSheet":           None,
            "assignTeam":           "Dev Team",
            "orderStatus":          "PENDING",
            "orderAmount":          60000.00,
            "receiveAmount":        15000.00,
            "dueAmount":            45000.00,
            "paymentMethod":        "Nagad",
            "paymentMethodDetails": "Nagad Business: 01812-456789",
        },
        {
            "date":                 _dt(20),
            "clientId":             "CLT-004",
            "clientName":           "Taslim Brothers Import",
            "clientLink":           "+8801911-234567",
            "orderDetails":         "Product photography — 200 SKUs, edited, web-ready, delivered in 5 business days",
            "orderSheet":           None,
            "assignTeam":           "Design Team",
            "orderStatus":          "COMPLETED",
            "orderAmount":          18000.00,
            "receiveAmount":        18000.00,
            "dueAmount":            0.00,
            "paymentMethod":        "Cash",
            "paymentMethodDetails": "Cash payment at office — receipt issued",
        },
        {
            "date":                 _dt(5),
            "clientId":             "CLT-005",
            "clientName":           "BDTech Startup Hub",
            "clientLink":           "https://bdtechhub.com",
            "orderDetails":         "Mobile app UI/UX design — 40 screens, Figma deliverable + clickable prototype",
            "orderSheet":           None,
            "assignTeam":           "Design Team",
            "orderStatus":          "IN_PROGRESS",
            "orderAmount":          75000.00,
            "receiveAmount":        37500.00,
            "dueAmount":            37500.00,
            "paymentMethod":        "Bank Transfer",
            "paymentMethodDetails": "BRAC Bank  A/C: 9876543210",
        },
        {
            "date":                 _dt(3),
            "clientId":             "CLT-006",
            "clientName":           "Apex Garments Ltd",
            "clientLink":           "https://apexgarments.com.bd",
            "orderDetails":         "Annual brand identity package — cancelled after initial design review",
            "orderSheet":           None,
            "assignTeam":           "Design Team",
            "orderStatus":          "CANCELLED",
            "orderAmount":          30000.00,
            "receiveAmount":        5000.00,
            "dueAmount":            0.00,
            "paymentMethod":        "bKash",
            "paymentMethodDetails": "bKash Business: 01900-123456 — advance refunded",
        },
    ]

    for o in orders:
        await db.outsideorder.create(data=o)
        _ok(f"OutsideOrder  {o['clientId']}", f"{o['clientName']}  ৳{o['orderAmount']:,.0f}  [{o['orderStatus']}]")


# ══════════════════════════════════════════════════════════════════════════════
#  DOLLAR EXCHANGE
# ══════════════════════════════════════════════════════════════════════════════

async def seed_dollar_exchange(db: Prisma) -> None:
    """
    6 exchange records — 4× RECEIVED, 2× DUE.
    enum PaymentStatus { RECEIVED  DUE }  — exact strings, no aliases.
    totalBdt = exchange_amount × rate  (computed before insert).
    """
    _header("💱 Dollar Exchange")

    exchanges = [
        # (days_ago, details,                                      from,              to,                  debit,    credit,  rate,    status)
        (28, "Sold $500 to local exchanger — Motijheel",   "Payoneer Main",   "Exchanger Kamal",   500.00,    0.00, 109.50, "RECEIVED"),
        (21, "Sold $300 to broker — Gulshan",              "Payoneer Main",   "Broker Rahim",      300.00,    0.00, 110.00, "RECEIVED"),
        (15, "Sold $800 — rate locked before weekend",     "Payoneer Sub",    "Exchanger Hasan",   800.00,    0.00, 109.75, "RECEIVED"),
        ( 9, "Bought $200 — emergency top-up",             "Exchanger Ali",   "Payoneer Main",       0.00,  200.00, 111.00, "RECEIVED"),
        ( 4, "Sold $600 to preferred broker",              "Payoneer Main",   "Broker Salam",      600.00,    0.00, 110.25, "DUE"),
        ( 0, "Sold $1,000 — today's live rate",            "Payoneer Main",   "Exchanger Kamal",  1000.00,    0.00, 110.50, "DUE"),
    ]

    for days_ago, details, acc_from, acc_to, debit, credit, rate, status in exchanges:
        exchange_amount = credit if credit > 0 else debit
        total_bdt       = round(exchange_amount * rate, 2)
        await db.dollarexchange.create(data={
            "date":          _dt(days_ago),
            "details":       details,
            "accountFrom":   acc_from,
            "accountTo":     acc_to,
            "debit":         debit,
            "credit":        credit,
            "rate":          rate,
            "totalBdt":      total_bdt,
            "paymentStatus": status,
        })
        _ok(f"DollarExchange", f"${exchange_amount:.0f} × {rate} = ৳{total_bdt:,.2f}  [{status}]")


# ══════════════════════════════════════════════════════════════════════════════
#  DAILY RATE
# ══════════════════════════════════════════════════════════════════════════════

async def seed_daily_rate(db: Prisma) -> None:
    _header("📈 Daily Rate  (USD → BDT)")

    for days_ago, rate, set_by, note in [
        (7,  109.25, "hr@maktech.com", "Weekly rate — market open"),
        (5,  109.75, "hr@maktech.com", "Slight uptick — midweek adjustment"),
        (3,  110.00, "hr@maktech.com", "Thursday rate — market stable"),
        (1,  110.25, "hr@maktech.com", "Friday closing rate"),
        (0,  110.50, "hr@maktech.com", "Today's live rate — use for all BDT conversions"),
    ]:
        await db.dailyrate.create(data={"date": _dt(days_ago), "rate": rate, "setBy": set_by, "note": note})
        _ok(f"DailyRate  -{days_ago}d", f"৳{rate} / $1  (set by {set_by})")


# ══════════════════════════════════════════════════════════════════════════════
#  CARD SHARING
# ══════════════════════════════════════════════════════════════════════════════

async def seed_card_sharing(db: Prisma) -> None:
    """cardNo and cardCvc are Fernet-encrypted before insert."""
    _header("🃏 Card Sharing  (cardNo & cardCvc encrypted)")

    for c in [
        {
            "serialNo": "CS-001", "details": "Primary virtual card — tool subscriptions (Notion, Canva, Figma)",
            "payoneerAccount": "Payoneer - MAKTech Main", "cardNo": "4111111111111111",
            "cardExpire": "09/26", "cardCvc": "123", "cardVendor": "Notion, Canva, Figma",
            "cardLimit": 500.00, "cardPaymentRcv": 320.00, "cardRcvBank": "Payoneer Main Balance",
            "mailDetails": "cards@maktech.com", "screenshotPath": None,
        },
        {
            "serialNo": "CS-002", "details": "Ads card — Facebook & Google campaigns",
            "payoneerAccount": "Payoneer - MAKTech Sub", "cardNo": "5500000000000004",
            "cardExpire": "12/25", "cardCvc": "456", "cardVendor": "Facebook Ads, Google Ads",
            "cardLimit": 1000.00, "cardPaymentRcv": 875.00, "cardRcvBank": "Payoneer Sub Balance",
            "mailDetails": "ads@maktech.com", "screenshotPath": None,
        },
        {
            "serialNo": "CS-003", "details": "Emergency backup card — Director access only",
            "payoneerAccount": "Payoneer - MAKTech Main", "cardNo": "378282246310005",
            "cardExpire": "06/27", "cardCvc": "789", "cardVendor": "Emergency Use",
            "cardLimit": 250.00, "cardPaymentRcv": 0.00, "cardRcvBank": None,
            "mailDetails": "backup@maktech.com", "screenshotPath": None,
        },
    ]:
        await db.cardsharing.create(data={
            "serialNo":        c["serialNo"],
            "details":         c["details"],
            "payoneerAccount": c["payoneerAccount"],
            "cardNo":          encrypt_value(c["cardNo"]),
            "cardExpire":      c["cardExpire"],
            "cardCvc":         encrypt_value(c["cardCvc"]),
            "cardVendor":      c["cardVendor"],
            "cardLimit":       c["cardLimit"],
            "cardPaymentRcv":  c["cardPaymentRcv"],
            "cardRcvBank":     c["cardRcvBank"],
            "mailDetails":     c["mailDetails"],
            "screenshotPath":  c["screenshotPath"],
        })
        _ok(f"CardSharing  {c['serialNo']}", f"vendor={c['cardVendor'][:28]}  limit=${c['cardLimit']}  [ENCRYPTED]")


# ══════════════════════════════════════════════════════════════════════════════
#  HR EXPENSE
# ══════════════════════════════════════════════════════════════════════════════

async def seed_hr_expense(db: Prisma) -> None:
    """
    11 HR ledger entries with a running balance across 3 temporal windows.

    Window A — THIS MONTH (days_ago  0–9 ):  March 2026 entries
    Window B — LAST MONTH (days_ago 10–40):  February entries
    Window C — HISTORICAL (days_ago 41+  ):  older entries

    HrExpense ALL fields: date, details, accountFrom, accountTo,
                          debit, credit, remainingBalance
    """
    _header("💰 HR Expense")

    for days_ago, details, acc_from, acc_to, debit, credit, balance in [
        # ── Window C: HISTORICAL (days 41+) ──────────────────────────────────
        # (days_ago, details,                                 from,         to,                  debit,     credit,    balance)
        (60, "February salary — Nusrat Jahan (HR)",     "PMAK Main",  "HR Nusrat",         18000.00,     0.00, 182000.00),
        (60, "February salary — Rahim (Developer)",     "PMAK Main",  "Dev Rahim",         22000.00,     0.00, 160000.00),
        (60, "February salary — Karim (Designer)",      "PMAK Main",  "Designer Karim",    20000.00,     0.00, 140000.00),
        # ── Window B: LAST MONTH (days 10-40) ────────────────────────────────
        (25, "Festival bonus — all staff",              "PMAK Main",  "All Staff",         15000.00,     0.00, 125000.00),
        (20, "Medical allowance reimbursement",         "PMAK Main",  "HR Nusrat",          2500.00,     0.00, 122500.00),
        (15, "Advance salary — Dev Rahim (emergency)",  "PMAK Main",  "Dev Rahim",          5000.00,     0.00, 117500.00),
        # ── Window A: THIS MONTH (days 0-9) ──────────────────────────────────
        ( 9, "March salary — Nusrat Jahan (HR)",        "PMAK Main",  "HR Nusrat",         18000.00,     0.00,  99500.00),
        ( 9, "March salary — Rahim (Developer)",        "PMAK Main",  "Dev Rahim",         22000.00,     0.00,  77500.00),
        ( 9, "March salary — Karim (Designer)",         "PMAK Main",  "Designer Karim",    20000.00,     0.00,  57500.00),
        ( 7, "Performance bonus — Karim (Designer)",    "PMAK Main",  "Designer Karim",     3000.00,     0.00,  54500.00),
        ( 0, "Fund allocated for April salaries",       "PMAK Main",  "HR Fund",               0.00, 60000.00, 114500.00),
    ]:
        await db.hrexpense.create(data={
            "date":             _dt(days_ago),
            "details":          details,
            "accountFrom":      acc_from,
            "accountTo":        acc_to,
            "debit":            debit,
            "credit":           credit,
            "remainingBalance": balance,
        })
        _ok(f"HrExpense", f"'{details[:44]}'  balance=৳{balance:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
#  INVENTORY
# ══════════════════════════════════════════════════════════════════════════════

async def seed_inventory(db: Prisma) -> None:
    """
    12 items spread across 3 temporal windows so every standard period
    (daily, weekly, monthly, yearly) returns meaningful data.

    Window A — THIS MONTH (days_ago  0–9 ):  new procurements in March 2026
    Window B — LAST MONTH (days_ago 10–40):  February / late-Jan purchases
    Window C — HISTORICAL (days_ago 41+  ):  older assets on record

    totalPrice = qty × unitPrice (computed before insert).
    """
    _header("📋 Inventory")

    for days_ago, item_name, category, qty, unit_price, condition, assigned_to, notes in [
        # ── Window A: THIS MONTH (days 0-9) ──────────────────────────────────
        # (days_ago, itemName,                              category,      qty, unitPrice,   condition,  assignedTo,       notes)
        ( 0, "Ergonomic Keyboard — Logitech K800",   "Accessories",  3,   4500.00, "New",    "Dev Team",    "March 2026 — typing comfort upgrade"),
        ( 2, "USB-C Hub — Anker 13-in-1",            "Accessories",  5,   3200.00, "New",    "All Team",    "March 2026 — desk cable management"),
        ( 5, "Office Chair — ErgoMax Pro",            "Furniture",    2,  28000.00, "New",    "HR & CEO",    "March 2026 — executive seating upgrade"),
        ( 8, "NVMe SSD 1TB — Samsung 980 Pro",        "Hardware",     4,   8500.00, "New",    "Dev Team",    "March 2026 — storage upgrade for dev machines"),
        # ── Window B: LAST MONTH (days 10-40) ────────────────────────────────
        (15, "Standing Desk Converter",               "Furniture",    2,   9800.00, "New",    "Dev Team",    "Feb 2026 — ergonomic upgrade, HR recommended"),
        (30, "TP-Link Wi-Fi 6 Router AX3000",         "Network",      1,  12000.00, "New",    "Office",      "Feb 2026 — main router, replaced old unit"),
        # ── Window C: HISTORICAL (days 41+) ──────────────────────────────────
        (45, "UPS Battery Backup 1500VA",             "Hardware",     2,  14500.00, "New",    "Office",      "Jan 2026 — power backup for workstations"),
        (55, "Dell 27\" 4K Monitor",                  "Hardware",     4,  42000.00, "New",    "All Team",    "Jan 2026 — one per workstation, 4K accuracy"),
        (55, "Logitech MX Master 3 Mouse",            "Accessories",  5,   8500.00, "New",    "All Team",    "Jan 2026 — wireless ergonomic mouse"),
        (60, "Apple MacBook Pro 14\" M3",             "Hardware",     2, 195000.00, "New",    "Dev Team",    "Jan 2026 — primary dev machines"),
        (90, "Adobe Creative Cloud — Annual",         "Software",     3,  28000.00, "Active", "Design Team", "Dec 2025 — renewed, expires Dec 2026"),
        (120,"Office Desk — L-Shape",                 "Furniture",    3,  18500.00, "Good",   "Office",      "Nov 2025 — new office setup Q4"),
    ]:
        total = round(qty * unit_price, 2)
        await db.inventory.create(data={
            "date":        _dt(days_ago),
            "itemName":    item_name,
            "category":    category,
            "quantity":    qty,
            "unitPrice":   unit_price,
            "totalPrice":  total,
            "condition":   condition,
            "assignedTo":  assigned_to,
            "notes":       notes,
        })
        _ok(f"Inventory", f"'{item_name[:38]}'  qty={qty}  total=৳{total:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

async def print_summary(db: Prisma) -> None:
    _header("📊 Final Record Counts")
    total = 0
    for label, count in [
        ("Users",                  await db.user.count()),
        ("Fiverr Profiles",        await db.fiverrprofile.count()),
        ("Fiverr Entries",         await db.fiverrentry.count()),
        ("Fiverr Orders",          await db.fiverrorder.count()),
        ("Upwork Profiles",        await db.upworkprofile.count()),
        ("Upwork Entries",         await db.upworkentry.count()),
        ("Upwork Orders",          await db.upworkorder.count()),
        ("Payoneer Accounts",      await db.payoneeraccount.count()),
        ("Payoneer Transactions",  await db.payoneertransaction.count()),
        ("PMAK Accounts",          await db.pmakaccount.count()),
        ("PMAK Transactions",      await db.pmaktransaction.count()),
        ("Outside Orders",         await db.outsideorder.count()),
        ("Dollar Exchanges",       await db.dollarexchange.count()),
        ("Daily Rates",            await db.dailyrate.count()),
        ("Card Sharing",           await db.cardsharing.count()),
        ("HR Expenses",            await db.hrexpense.count()),
        ("Inventory Items",        await db.inventory.count()),
        ("Invitations",            await db.invitation.count()),
    ]:
        print(f"  · {label:<30} {count:>4} records")
        total += count
    print(f"  {'─' * 42}")
    print(f"  {'TOTAL':<30} {total:>4} records")


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
        await reset_all(db)
        await seed_users(db)
        await seed_fiverr(db)
        await seed_upwork(db)
        await seed_payoneer(db)
        await seed_pmak(db)
        await seed_outside_orders(db)
        await seed_dollar_exchange(db)
        await seed_daily_rate(db)
        await seed_card_sharing(db)
        await seed_hr_expense(db)
        await seed_inventory(db)
        await print_summary(db)

        print()
        print("╔══════════════════════════════════════════════════════╗")
        print("║         Done! Database is fresh and ready.           ║")
        print("╠══════════════════════════════════════════════════════╣")
        print("║  CEO      →  ceo@maktech.com        /  123456        ║")
        print("║  Director →  director@maktech.com   /  123456        ║")
        print("║  HR       →  hr@maktech.com         /  123456        ║")
        print("║  BDev     →  bdev@maktech.com       /  123456        ║")
        print("║                                                      ║")
        print("║  API Docs →  https://fin-flow.maktechlaravel.cloud   ║")
        print("╚══════════════════════════════════════════════════════╝")
        print()

    finally:
        await db.disconnect()


# ── Entry point — works for BOTH invocation styles ───────────────────────────
if __name__ == "__main__":
    asyncio.run(main())   # direct:  poetry run python app/Scripts/seed.py
else:
    asyncio.run(main())   # module:  poetry run python -m app.Scripts.seed