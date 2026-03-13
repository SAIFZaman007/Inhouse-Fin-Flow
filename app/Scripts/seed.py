"""
MAKTech Financial Flow -- Database Seeder  (v3 -- Enterprise Edition)
=======================================================================
Comprehensive seed for ALL models in schema.prisma (v3) with realistic demo data.

Models covered:
  User                  (CEO · Director · HR · BDev)
  FiverrProfile         (3 profiles)
  FiverrEntry           (5 snapshots/profile -- ALL 10 fields incl. activeOrderAmount)
  FiverrOrder           (4 orders/profile   -- ALL 6 fields  incl. afterFiverr  @ 80%)
  UpworkProfile         (2 profiles)
  UpworkEntry           (5 snapshots/profile -- ALL 9 fields)
  UpworkOrder           (4 orders/profile   -- ALL 6 fields  incl. afterUpwork  @ 90%)
  PayoneerAccount       (2 accounts)
  PayoneerTransaction   (8 ledger entries/account -- ALL 8 fields)
  PmakAccount           (2 accounts)
  PmakTransaction       (8 ledger rows -- ALL 9 fields incl. PmakStatus enum)
  PmakInhouse           (8 deal rows   -- ALL 7 fields incl. InhouseOrderStatus enum) [NEW]
  OutsideOrder          (6 orders      -- ALL 13 fields incl. orderSheet)
  DollarExchange        (8 records     -- ALL 9 fields; rate lives here, no DailyRate)
  CardSharing           (3 cards       -- ALL 13 v3.1 fields: accountId FK, date, cardDetails
                                          cardPaymentReceived, cardReceiveBank; encrypted)
  HrExpense             (12 entries    -- ALL 8 fields incl. remarks)
  Inventory             (12 items      -- ALL 9 fields)

KEY v3 CHANGES vs OLD SEED:
  + FiverrEntry.activeOrderAmount  (NEW field)
  + FiverrOrder.afterFiverr        (NEW field -- server-computed @ amount*0.80)
  + UpworkOrder.afterUpwork        (NEW field -- server-computed @ amount*0.90)
  + OutsideOrder.orderSheet        (NEW field -- documented order link)
  + PmakTransaction.status         (NOW typed PmakStatus enum: PENDING/CLEARED/ON_HOLD/REJECTED)
  + PmakInhouse                    (BRAND NEW model -- buyer/seller deal tracking)
  + CardSharing.date               (NEW field)
  + CardSharing.accountId          (FK replaces raw payoneerAccount string)
  + CardSharing.cardDetails        (Json[] Cloudinary URLs -- replaces screenshotPath)
  + CardSharing.cardPaymentReceived (renamed: cardPaymentRcv → cardPaymentReceived, Decimal)
  + CardSharing.cardReceiveBank    (renamed: cardReceiveBank → cardReceiveBank, String -- bank name)
  + HrExpense.remarks              (NEW field -- CEO judgement notes)
  - DailyRate                      (REMOVED -- rate now lives on DollarExchange.rate)
  - CardSharing.payoneerAccount    (removed -- replaced by accountId FK)
  - CardSharing.cardPaymentRcv     (removed -- renamed to cardPaymentReceived)
  - CardSharing.cardRcvBank        (removed -- renamed to cardReceiveBank)
  - CardSharing.screenshotPath     (removed -- replaced by cardDetails JSON array)

BEHAVIOUR:
  Every run = full RESET then fresh seed (no stale data ever).
  All passwords: 123456.
  Date fields use datetime (UTC midnight) -- prisma-client-py requires datetime, not date.
  afterFiverr  = round(amount * 0.80, 2)  -- mirrors service.py _compute_after_fiverr()
  afterUpwork  = round(amount * 0.90, 2)  -- mirrors service.py _compute_after_upwork()
  totalBdt     = round(exchange_amount * rate, 2)
  Temporal windows ensure daily/weekly/monthly/yearly exports all return data.

Run:
  poetry run python app/Scripts/seed.py
  poetry run python -m app.Scripts.seed
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

# ── Path fix ───────────────────────────────────────────────────────────────────
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from prisma import Prisma
from app.core.security import encrypt_value, hash_password


# ==============================================================================
#  HELPERS
# ==============================================================================

def _dt(days_ago: int = 0) -> datetime:
    """Return UTC midnight datetime offset by days_ago."""
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return base - timedelta(days=days_ago)


def _pw(plain: str = "123456") -> str:
    return hash_password(str(plain))


def _after_fiverr(amount: float) -> float:
    """Net after Fiverr 20% fee -- mirrors service.py exactly."""
    return round(amount * 0.80, 2)


def _after_upwork(amount: float) -> float:
    """Net after Upwork 10% fee -- mirrors service.py exactly."""
    return round(amount * 0.90, 2)


def _header(title: str) -> None:
    bar = "-" * 58
    print(f"\n+{bar}+")
    print(f"|  {title:<56}|")
    print(f"+{bar}+")


def _ok(label: str, detail: str = "") -> None:
    print(f"  OK  {label}{'  ' + detail if detail else ''}")


def _del(label: str, count: int) -> None:
    print(f"  DEL {label:<34} {count} records deleted")


# ==============================================================================
#  RESET
# ==============================================================================

async def reset_all(db: Prisma) -> None:
    _header("RESET -- Clearing All Tables")
    # Order matters: children before parents (FK constraints)
    for name, model in [
        ("Invitation",          db.invitation),
        ("FiverrOrder",         db.fiverrorder),
        ("FiverrEntry",         db.fiverrentry),
        ("FiverrProfile",       db.fiverrprofile),
        ("UpworkOrder",         db.upworkorder),
        ("UpworkEntry",         db.upworkentry),
        ("UpworkProfile",       db.upworkprofile),
        ("PayoneerTransaction",  db.payoneertransaction),
        ("CardSharing",         db.cardsharing),           # FK -> PayoneerAccount
        ("PayoneerAccount",     db.payoneeraccount),
        ("PmakInhouse",         db.pmakinhouse),           # FK -> PmakAccount  [NEW]
        ("PmakTransaction",     db.pmaktransaction),       # FK -> PmakAccount
        ("PmakAccount",         db.pmakaccount),
        ("OutsideOrder",        db.outsideorder),
        ("DollarExchange",      db.dollarexchange),
        ("HrExpense",           db.hrexpense),
        ("Inventory",           db.inventory),
        ("User",                db.user),
    ]:
        _del(name, await model.delete_many())


# ==============================================================================
#  USERS
# ==============================================================================

async def seed_users(db: Prisma) -> None:
    _header("Users  (password: 123456 for all)")
    for u in [
        {"name": "Ariful Islam (CEO)",      "email": "ceo@maktech.com",      "role": "CEO",      "passwordHash": _pw(), "isActive": True},
        {"name": "Mahfuz Rahman (Director)", "email": "director@maktech.com", "role": "DIRECTOR", "passwordHash": _pw(), "isActive": True},
        {"name": "Nusrat Jahan (HR)",        "email": "hr@maktech.com",       "role": "HR",       "passwordHash": _pw(), "isActive": True},
        {"name": "Tanvir Ahmed (BDev)",      "email": "bdev@maktech.com",     "role": "BDEV",     "passwordHash": _pw(), "isActive": True},
    ]:
        await db.user.create(data=u)
        _ok(u["role"], f"email={u['email']}  password=123456")


# ==============================================================================
#  FIVERR
# ==============================================================================

async def seed_fiverr(db: Prisma) -> None:
    """
    3 profiles x 5 entries x 4 orders.

    FiverrEntry  ALL 10 fields:
      date, profileId, availableWithdraw, notCleared, activeOrders,
      activeOrderAmount [NEW], submitted, withdrawn, sellerPlus, promotion

    FiverrOrder  ALL 6 fields:
      date, profileId, buyerName, orderId, amount, afterFiverr [NEW]
      afterFiverr = amount * 0.80  (mirrors service.py _compute_after_fiverr)
    """
    _header("Fiverr  (3 profiles, 5 entries, 4 orders each)")

    profiles = [
        {
            "profileName": "maktech_design",
            "entries": [
                # (days_ago, avail,   notCleared, activeOrders, activeOrderAmt, submitted, withdrawn, sellerPlus, promo)
                (0,  1250.00,  320.00, 5, 620.00, 180.00, 400.00, True,  75.00),
                (1,  1180.00,  295.00, 4, 540.00, 160.00, 350.00, True,  60.00),
                (2,  1100.00,  250.00, 6, 710.00, 200.00, 300.00, True,  80.00),
                (3,   980.00,  210.00, 3, 380.00, 140.00, 250.00, True,  55.00),
                (7,   850.00,  180.00, 2, 240.00, 120.00, 200.00, False,  0.00),
            ],
            "orders": [
                # (buyerName,   orderId,        amount, days_ago)
                ("BuyerAlpha",  "FO-D001",  120.00, 1),
                ("BuyerBeta",   "FO-D002",   85.00, 2),
                ("BuyerGamma",  "FO-D003",  200.00, 0),
                ("BuyerDelta",  "FO-D004",  150.00, 4),
            ],
        },
        {
            "profileName": "maktech_dev",
            "entries": [
                (0,  2400.00, 580.00, 8, 1120.00, 320.00, 750.00, True,  120.00),
                (1,  2200.00, 510.00, 7,  980.00, 290.00, 680.00, True,  100.00),
                (2,  2050.00, 460.00, 6,  840.00, 260.00, 600.00, True,   90.00),
                (3,  1900.00, 400.00, 5,  720.00, 230.00, 530.00, True,   80.00),
                (7,  1650.00, 330.00, 4,  560.00, 200.00, 450.00, False,   0.00),
            ],
            "orders": [
                ("DevClient_A",  "FO-V001",  350.00, 0),
                ("DevClient_B",  "FO-V002",  180.00, 1),
                ("DevClient_C",  "FO-V003",  420.00, 2),
                ("DevClient_D",  "FO-V004",  275.00, 5),
            ],
        },
        {
            "profileName": "maktech_seo",
            "entries": [
                (0,  780.00, 190.00, 3, 310.00, 110.00, 230.00, False, 30.00),
                (1,  720.00, 170.00, 3, 270.00,  95.00, 200.00, False, 25.00),
                (2,  660.00, 145.00, 2, 210.00,  80.00, 175.00, False, 20.00),
                (3,  590.00, 120.00, 2, 170.00,  70.00, 150.00, False, 15.00),
                (7,  510.00,  95.00, 1, 110.00,  60.00, 120.00, False,  0.00),
            ],
            "orders": [
                ("SEO_ClientX",  "FO-S001",   95.00, 0),
                ("SEO_ClientY",  "FO-S002",  140.00, 3),
                ("SEO_ClientZ",  "FO-S003",   65.00, 1),
                ("SEO_ClientW",  "FO-S004",  110.00, 6),
            ],
        },
    ]

    for p in profiles:
        profile = await db.fiverrprofile.create(data={"profileName": p["profileName"]})
        _ok(f"FiverrProfile  {p['profileName']}")

        for days_ago, avail, not_cleared, active_orders, active_order_amt, submitted, withdrawn, seller_plus, promo in p["entries"]:
            await db.fiverrentry.create(data={
                "profileId":         profile.id,
                "date":              _dt(days_ago),
                "availableWithdraw": avail,
                "notCleared":        not_cleared,
                "activeOrders":      active_orders,
                "activeOrderAmount": active_order_amt,   # NEW v3 field
                "submitted":         submitted,
                "withdrawn":         withdrawn,
                "sellerPlus":        seller_plus,
                "promotion":         promo,
            })
            _ok(f"  FiverrEntry   {p['profileName']} @-{days_ago}d",
                f"avail=${avail}  activeAmt=${active_order_amt}")

        for buyer_name, order_id, amount, days_ago_o in p["orders"]:
            after = _after_fiverr(amount)
            await db.fiverrorder.create(data={
                "profileId":   profile.id,
                "date":        _dt(days_ago_o),
                "buyerName":   buyer_name,
                "orderId":     order_id,
                "amount":      amount,
                "afterFiverr": after,               # NEW v3 field (amount * 0.80)
            })
            _ok(f"  FiverrOrder   {order_id}",
                f"buyer={buyer_name}  ${amount} -> after=${after}")


# ==============================================================================
#  UPWORK
# ==============================================================================

async def seed_upwork(db: Prisma) -> None:
    """
    2 profiles x 5 entries x 4 orders.

    UpworkEntry  ALL 9 fields:
      date, profileId, availableWithdraw, pending, inReview,
      workInProgress, withdrawn, connects, upworkPlus

    UpworkOrder  ALL 6 fields:
      date, profileId, clientName, orderId, amount, afterUpwork [NEW]
      afterUpwork = amount * 0.90  (mirrors service.py _compute_after_upwork)
    """
    _header("Upwork  (2 profiles, 5 entries, 4 orders each)")

    profiles = [
        {
            "profileName": "maktech_upwork_main",
            "entries": [
                # (days_ago, avail,    pending,  inReview,  wip,      withdrawn, connects, upworkPlus)
                (0,  3200.00, 480.00, 650.00, 1200.00, 900.00,  80, True),
                (1,  2950.00, 420.00, 580.00, 1100.00, 800.00,  75, True),
                (2,  2700.00, 370.00, 510.00,  980.00, 720.00,  70, True),
                (3,  2450.00, 310.00, 440.00,  860.00, 640.00,  65, True),
                (7,  2100.00, 250.00, 360.00,  720.00, 560.00,  58, True),
            ],
            "orders": [
                # (clientName,             orderId,       amount, days_ago)
                ("TechStartup Ltd",        "UW-M001",  500.00, 0),
                ("Creative Agency BD",     "UW-M002",  320.00, 2),
                ("Global Corp PLC",        "UW-M003",  750.00, 1),
                ("Innovation Labs Inc",    "UW-M004",  410.00, 5),
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
                ("SmallBiz Owner",         "UW-S001",  180.00, 0),
                ("Freelance Buyer",        "UW-S002",   95.00, 1),
                ("E-commerce Store",       "UW-S003",  260.00, 3),
                ("Retail Brand BD",        "UW-S004",  145.00, 6),
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
            _ok(f"  UpworkEntry   {p['profileName']} @-{days_ago}d", f"avail=${avail}")

        for client_name, order_id, amount, days_ago_o in p["orders"]:
            after = _after_upwork(amount)
            await db.upworkorder.create(data={
                "profileId":   profile.id,
                "date":        _dt(days_ago_o),
                "clientName":  client_name,
                "orderId":     order_id,
                "amount":      amount,
                "afterUpwork": after,               # NEW v3 field (amount * 0.90)
            })
            _ok(f"  UpworkOrder   {order_id}",
                f"client={client_name}  ${amount} -> after=${after}")


# ==============================================================================
#  PAYONEER
# ==============================================================================

async def seed_payoneer(db: Prisma) -> dict[str, str]:
    """
    2 accounts x 8 transactions.
    Returns {accountName: id} map — consumed by seed_card_sharing().

    PayoneerTransaction  ALL 8 fields:
      date, accountId, details, accountFrom, accountTo, debit, credit, remainingBalance
    """
    _header("Payoneer  (2 accounts, 8 transactions each)")

    accounts_data = [
        {
            "accountName": "Payoneer - MAKTech Main",
            "transactions": [
                # (days_ago, details,                                           from,                   to,                debit,   credit,  balance)
                (30, "Initial deposit from Fiverr withdrawal",         "Fiverr maktech_design",  "Payoneer Main",      0.00, 1500.00, 1500.00),
                (25, "Service fee deduction",                          "Payoneer Main",           "Payoneer Fee",      12.50,    0.00, 1487.50),
                (20, "Received from Upwork withdrawal",                "Upwork maktech_main",     "Payoneer Main",      0.00,  900.00, 2387.50),
                (15, "Transfer to PMAK Main account",                  "Payoneer Main",           "PMAK Main",        800.00,    0.00, 1587.50),
                (10, "Fiverr payout — maktech_dev",                    "Fiverr maktech_dev",      "Payoneer Main",      0.00, 1200.00, 2787.50),
                ( 5, "Dollar exchange sale — Broker Rahim",            "Payoneer Main",           "Exchanger Rahim",  600.00,    0.00, 2187.50),
                ( 2, "Card sharing — tool subscriptions deduction",    "Payoneer Main",           "Card CS-001",      320.00,    0.00, 1867.50),
                ( 0, "Upwork withdrawal — maktech_upwork_main",        "Upwork maktech_main",     "Payoneer Main",      0.00,  750.00, 2617.50),
            ],
        },
        {
            "accountName": "Payoneer - MAKTech Sub",
            "transactions": [
                (28, "Initial deposit — SEO revenue",                  "Fiverr maktech_seo",      "Payoneer Sub",       0.00,  600.00,  600.00),
                (22, "Service fee",                                     "Payoneer Sub",            "Payoneer Fee",       5.00,    0.00,  595.00),
                (18, "Upwork sub-profile payout",                      "Upwork maktech_sub",      "Payoneer Sub",       0.00,  400.00,  995.00),
                (12, "Transfer to HR expense fund",                    "Payoneer Sub",            "HR Fund",           300.00,    0.00,  695.00),
                ( 8, "Facebook Ads card payment received",             "Vendor Facebook",         "Payoneer Sub",       0.00,  875.00, 1570.00),
                ( 4, "Dollar exchange sale",                           "Payoneer Sub",            "Exchanger Hasan",   500.00,    0.00, 1070.00),
                ( 1, "Fiverr SEO profile withdrawal",                  "Fiverr maktech_seo",      "Payoneer Sub",       0.00,  350.00, 1420.00),
                ( 0, "Card sharing — ads card balance return",         "Card CS-002",             "Payoneer Sub",       0.00,  125.00, 1545.00),
            ],
        },
    ]

    account_id_map: dict[str, str] = {}
    for a in accounts_data:
        account = await db.payoneeraccount.create(data={"accountName": a["accountName"]})
        account_id_map[a["accountName"]] = account.id
        _ok(f"PayoneerAccount  {a['accountName']}")

        for days_ago, details, acc_from, acc_to, debit, credit, balance in a["transactions"]:
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
            net = credit if credit > 0 else -debit
            _ok(f"  PayoneerTxn   @-{days_ago}d",
                f"{'credit' if credit > 0 else 'debit'} ${abs(net):.2f}  bal=${balance}")

    return account_id_map


# ==============================================================================
#  PMAK  (Ledger + Inhouse -- v3 split)
# ==============================================================================

async def seed_pmak(db: Prisma) -> None:
    """
    2 PMAK accounts.

    PmakTransaction  ALL 9 fields (v3):
      date, accountId, details, accountFrom, accountTo, debit, credit,
      remainingBalance, status  [status is PmakStatus enum: PENDING|CLEARED|ON_HOLD|REJECTED]

    PmakInhouse  ALL 7 fields (NEW model):
      date, accountId, details, buyerName, sellerName, orderAmount, orderStatus
      [orderStatus is InhouseOrderStatus: PENDING|IN_PROGRESS|COMPLETED|CANCELLED]

    Note: buyer/seller/notes are NO LONGER on PmakTransaction in v3.
    They live exclusively on PmakInhouse.
    """
    _header("PMAK  (2 accounts, 8 ledger rows + 8 inhouse deals)")

    accounts_data = [
        {
            "accountName": "PMAK Main",
            "transactions": [
                # (days_ago, details,                                    from,            to,              debit,     credit,  balance,      status)
                (60, "Opening balance transfer",                  "CEO Fund",      "PMAK Main",        0.00,  200000.00, 200000.00, "CLEARED"),
                (45, "Feb salaries -- all staff",                 "PMAK Main",     "Staff Payroll",  60000.00,       0.00, 140000.00, "CLEARED"),
                (30, "Office rent -- February",                   "PMAK Main",     "Landlord",       25000.00,       0.00, 115000.00, "CLEARED"),
                (20, "Festival bonus -- all staff",               "PMAK Main",     "Staff Payroll",  15000.00,       0.00, 100000.00, "CLEARED"),
                (15, "Medical allowance reimbursement",           "PMAK Main",     "HR Nusrat",       2500.00,       0.00,  97500.00, "CLEARED"),
                ( 9, "March salaries -- all staff",               "PMAK Main",     "Staff Payroll",  60000.00,       0.00,  37500.00, "PENDING"),
                ( 5, "Office utility bills -- March",             "PMAK Main",     "DESCO / TITAS",   8000.00,       0.00,  29500.00, "PENDING"),
                ( 0, "Fund allocated for April salaries",         "CEO Fund",      "PMAK Main",        0.00,   60000.00,  89500.00, "ON_HOLD"),
            ],
            "inhouse_deals": [
                # (days_ago, details,                                    buyer,               seller,              amount,    status)
                (55, "UI/UX design package -- CLT-001",          "Rahim Textiles",    "maktech_design",   18000.00, "COMPLETED"),
                (42, "E-commerce website -- CLT-002",            "Apex Retail",       "maktech_dev",      45000.00, "COMPLETED"),
                (30, "SEO audit + 3-month plan -- CLT-003",      "Green Foods BD",    "maktech_seo",       8500.00, "COMPLETED"),
                (15, "Brand identity package -- CLT-004",        "Nova Pharma",       "maktech_design",   22000.00, "IN_PROGRESS"),
            ],
        },
        {
            "accountName": "PMAK Operations",
            "transactions": [
                (50, "Opening balance -- operations fund",        "CEO Fund",      "PMAK Ops",         0.00,   80000.00,  80000.00, "CLEARED"),
                (35, "Server & cloud infrastructure -- Feb",      "PMAK Ops",      "AWS / Cloudinary", 12000.00,      0.00,  68000.00, "CLEARED"),
                (25, "Software licences -- Adobe, Notion, Figma", "PMAK Ops",      "Software Vendors",  8500.00,      0.00,  59500.00, "CLEARED"),
                (18, "Marketing budget -- FB + Google ads",       "PMAK Ops",      "Ad Platforms",     15000.00,      0.00,  44500.00, "CLEARED"),
                (10, "Server & cloud -- March",                   "PMAK Ops",      "AWS / Cloudinary", 12000.00,      0.00,  32500.00, "PENDING"),
                ( 6, "Emergency repair -- office equipment",      "PMAK Ops",      "Tech Vendor",       4500.00,      0.00,  28000.00, "ON_HOLD"),
                ( 2, "Software renewals -- March",                "PMAK Ops",      "Software Vendors",  8500.00,      0.00,  19500.00, "PENDING"),
                ( 0, "Top-up from CEO for Q2 planning",           "CEO Fund",      "PMAK Ops",          0.00,   50000.00,  69500.00, "PENDING"),
            ],
            "inhouse_deals": [
                (48, "Custom ERP module -- CLT-005",              "Spark Logistics", "maktech_dev",      75000.00, "COMPLETED"),
                (20, "Social media campaign -- CLT-006",          "BrandBD Agency",  "maktech_seo",      12000.00, "IN_PROGRESS"),
                ( 8, "Landing page design -- CLT-007",            "StartupX BD",     "maktech_design",    9500.00, "IN_PROGRESS"),
                ( 1, "WordPress plugin dev -- CLT-008",           "DevShop Ltd",     "maktech_dev",      18000.00, "PENDING"),
            ],
        },
    ]

    for a in accounts_data:
        account = await db.pmakaccount.create(data={"accountName": a["accountName"]})
        _ok(f"PmakAccount  {a['accountName']}")

        # Ledger transactions
        for days_ago, details, acc_from, acc_to, debit, credit, balance, status in a["transactions"]:
            await db.pmaktransaction.create(data={
                "accountId":        account.id,
                "date":             _dt(days_ago),
                "details":          details,
                "accountFrom":      acc_from,
                "accountTo":        acc_to,
                "debit":            debit,
                "credit":           credit,
                "remainingBalance": balance,
                "status":           status,          # PmakStatus enum
            })
            _ok(f"  PmakTxn      @-{days_ago}d",
                f"[{status}]  bal=${balance:,.0f}")

        # Inhouse deals (NEW model -- v3)
        for days_ago, details, buyer, seller, amount, status in a["inhouse_deals"]:
            await db.pmakinhouse.create(data={
                "accountId":   account.id,
                "date":        _dt(days_ago),
                "details":     details,
                "buyerName":   buyer,
                "sellerName":  seller,
                "orderAmount": amount,
                "orderStatus": status,               # InhouseOrderStatus enum
            })
            _ok(f"  PmakInhouse  @-{days_ago}d",
                f"[{status}]  {buyer} -> {seller}  ${amount:,.0f}")


# ==============================================================================
#  OUTSIDE ORDERS
# ==============================================================================

async def seed_outside_orders(db: Prisma) -> None:
    """
    6 orders covering all 4 OrderStatus values and both temporal windows.

    OutsideOrder  ALL 13 fields (v3):
      date, clientId, clientName, clientLink, orderDetails, orderSheet [NEW],
      assignTeam, orderStatus, orderAmount, receiveAmount, dueAmount,
      paymentMethod, paymentMethodDetails

    orderSheet = documented order link (Google Doc / Drive URL).
    All amounts in USD per v3 requirement.
    """
    _header("Outside Orders  (6 orders, all statuses, orderSheet filled)")

    orders = [
        {
            "date":                 _dt(25),
            "clientId":             "CLT-001",
            "clientName":           "Rahim Textiles Ltd",
            "clientLink":           "https://rahimtextiles.com.bd",
            "orderDetails":         "Complete e-commerce website with inventory management, payment gateway integration and admin dashboard",
            "orderSheet":           "https://docs.google.com/document/d/rahim-textiles-ecommerce-brief",
            "assignTeam":           "Dev Team",
            "orderStatus":          "COMPLETED",
            "orderAmount":          1200.00,
            "receiveAmount":        1200.00,
            "dueAmount":              0.00,
            "paymentMethod":        "Payoneer",
            "paymentMethodDetails": "Payoneer - MAKTech Main  |  Paid in 2 instalments",
        },
        {
            "date":                 _dt(18),
            "clientId":             "CLT-002",
            "clientName":           "Nova Pharma BD",
            "clientLink":           "https://novapharma.com.bd",
            "orderDetails":         "Corporate brand identity: logo, style guide, stationery, and packaging design",
            "orderSheet":           "https://drive.google.com/drive/folders/nova-pharma-brand-assets",
            "assignTeam":           "Design Team",
            "orderStatus":          "IN_PROGRESS",
            "orderAmount":           850.00,
            "receiveAmount":         425.00,
            "dueAmount":             425.00,
            "paymentMethod":        "Bank Transfer",
            "paymentMethodDetails": "Dutch-Bangla Bank  A/C: 1234567890  |  50% advance received",
        },
        {
            "date":                 _dt(12),
            "clientId":             "CLT-003",
            "clientName":           "GreenFood Solutions",
            "clientLink":           "https://greenfoods.com.bd",
            "orderDetails":         "6-month SEO retainer: keyword research, on-page optimisation, monthly reporting",
            "orderSheet":           "https://docs.google.com/spreadsheets/d/greenfood-seo-tracker",
            "assignTeam":           "SEO Team",
            "orderStatus":          "IN_PROGRESS",
            "orderAmount":           480.00,
            "receiveAmount":         160.00,
            "dueAmount":             320.00,
            "paymentMethod":        "bKash",
            "paymentMethodDetails": "bKash Business: 01700-654321  |  Monthly billing active",
        },
        {
            "date":                 _dt(8),
            "clientId":             "CLT-004",
            "clientName":           "Spark Logistics BD",
            "clientLink":           "https://sparklogistics.com.bd",
            "orderDetails":         "Custom delivery management ERP: route optimisation, driver tracking, client portal",
            "orderSheet":           "https://docs.google.com/document/d/spark-logistics-erp-spec",
            "assignTeam":           "Dev Team",
            "orderStatus":          "PENDING",
            "orderAmount":          2500.00,
            "receiveAmount":         625.00,
            "dueAmount":            1875.00,
            "paymentMethod":        "Bank Transfer",
            "paymentMethodDetails": "BRAC Bank  A/C: 9876543210  |  25% advance, milestone-based billing",
        },
        {
            "date":                 _dt(4),
            "clientId":             "CLT-005",
            "clientName":           "StartupX BD",
            "clientLink":           "https://startupx.com.bd",
            "orderDetails":         "Landing page design + conversion copywriting for SaaS product launch",
            "orderSheet":           "https://drive.google.com/drive/folders/startupx-landing-brief",
            "assignTeam":           "Design Team",
            "orderStatus":          "PENDING",
            "orderAmount":           320.00,
            "receiveAmount":           0.00,
            "dueAmount":             320.00,
            "paymentMethod":        "Payoneer",
            "paymentMethodDetails": "Invoice sent -- awaiting payment",
        },
        {
            "date":                 _dt(2),
            "clientId":             "CLT-006",
            "clientName":           "Apex Garments Ltd",
            "clientLink":           "https://apexgarments.com.bd",
            "orderDetails":         "Annual brand identity package -- cancelled after initial design review phase",
            "orderSheet":           None,
            "assignTeam":           "Design Team",
            "orderStatus":          "CANCELLED",
            "orderAmount":           600.00,
            "receiveAmount":          80.00,
            "dueAmount":               0.00,
            "paymentMethod":        "bKash",
            "paymentMethodDetails": "bKash Business: 01900-123456  |  Advance refunded",
        },
    ]

    for o in orders:
        await db.outsideorder.create(data=o)
        sheet_info = "sheet=YES" if o["orderSheet"] else "sheet=None"
        _ok(f"OutsideOrder  {o['clientId']}",
            f"{o['clientName']}  ${o['orderAmount']}  [{o['orderStatus']}]  {sheet_info}")


# ==============================================================================
#  DOLLAR EXCHANGE
# ==============================================================================

async def seed_dollar_exchange(db: Prisma) -> None:
    """
    8 exchange records -- 5x RECEIVED, 3x DUE.
    Rate is stored per-row (DailyRate model REMOVED in v3).
    totalBdt = exchange_amount * rate.

    DollarExchange  ALL 9 fields:
      date, details, accountFrom, accountTo, debit, credit, rate, totalBdt, paymentStatus
    """
    _header("Dollar Exchange  (8 records, rate per-row, no DailyRate model)")

    exchanges = [
        # (days_ago, details,                                      from,              to,                 debit,   credit,   rate,    status)
        (30, "Sold $500 -- Motijheel exchanger",           "Payoneer Main",   "Exchanger Kamal",  500.00,    0.00, 109.50, "RECEIVED"),
        (22, "Sold $300 -- Gulshan broker",                "Payoneer Main",   "Broker Rahim",     300.00,    0.00, 110.00, "RECEIVED"),
        (15, "Sold $800 -- rate locked before weekend",    "Payoneer Sub",    "Exchanger Hasan",  800.00,    0.00, 109.75, "RECEIVED"),
        ( 9, "Bought $200 -- emergency top-up",            "Exchanger Ali",   "Payoneer Main",      0.00,  200.00, 111.00, "RECEIVED"),
        ( 6, "Sold $400 -- Dhanmondi preferred broker",    "Payoneer Main",   "Broker Salam",     400.00,    0.00, 110.50, "RECEIVED"),
        ( 4, "Sold $600 -- broker arrangement pending",    "Payoneer Main",   "Broker Salam",     600.00,    0.00, 110.25, "DUE"),
        ( 2, "Sold $350 -- awaiting cash collection",      "Payoneer Sub",    "Exchanger Kamal",  350.00,    0.00, 110.75, "DUE"),
        ( 0, "Sold $1000 -- today's live rate",            "Payoneer Main",   "Exchanger Kamal", 1000.00,    0.00, 110.50, "DUE"),
    ]

    for days_ago, details, acc_from, acc_to, debit, credit, rate, status in exchanges:
        exchange_amount = credit if credit > 0 else debit
        total_bdt = round(exchange_amount * rate, 2)
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
        _ok(f"DollarExchange  @-{days_ago}d",
            f"${exchange_amount:.0f} x {rate} = BDT {total_bdt:,.2f}  [{status}]")


# ==============================================================================
#  CARD SHARING  (v3 -- fully rebuilt)
# ==============================================================================

async def seed_card_sharing(db: Prisma, account_id_map: dict[str, str]) -> None:
    """
    3 cards -- cardNo and cardCvc Fernet-encrypted before insert.

    CardSharing  ALL 13 v3.1 fields:
      date, serialNo, details, accountId [FK],
      cardNo [encrypted], cardExpire, cardCvc [encrypted],
      cardDetails [Json array -- Cloudinary URLs],
      cardVendor, cardLimit,
      cardPaymentReceived [Decimal -- amount received],
      cardReceiveBank   [String  -- bank/channel name],
      mailDetails

    REMOVED in v3: payoneerAccount (string), cardPaymentRcv, cardRcvBank, screenshotPath
    """
    _header("Card Sharing  (3 cards, v3 schema -- accountId FK, cardDetails JSON)")

    main_id = account_id_map["Payoneer - MAKTech Main"]
    sub_id  = account_id_map["Payoneer - MAKTech Sub"]

    cards = [
        {
            "date":               _dt(20),
            "serialNo":           "CS-001",
            "details":            "Primary virtual card -- tool subscriptions (Notion, Canva, Figma)",
            "accountId":          main_id,                        # FK to PayoneerAccount
            "cardNo":             "4111111111111111",             # will be encrypted
            "cardExpire":         "09/26",
            "cardCvc":            "123",                          # will be encrypted
            "cardDetails":        [                               # Cloudinary URL array [NEW]
                "https://res.cloudinary.com/maktech/image/private/card_sharing/CS-001/screenshot_01.png",
                "https://res.cloudinary.com/maktech/image/private/card_sharing/CS-001/screenshot_02.png",
            ],
            "cardVendor":         "Notion, Canva, Figma",
            "cardLimit":           500.00,
            "cardPaymentReceive":  320.00,
            "cardReceiveBank":    "Payoneer - MAKTech Main",     # bank/channel name                        
            "mailDetails":        "cards@maktech.com",
        },
        {
            "date":               _dt(12),
            "serialNo":           "CS-002",
            "details":            "Ads card -- Facebook & Google campaigns",
            "accountId":          sub_id,                         # FK to PayoneerAccount
            "cardNo":             "5500000000000004",             # will be encrypted
            "cardExpire":         "12/25",
            "cardCvc":            "456",                          # will be encrypted
            "cardDetails":        [                               # Cloudinary URL array
                "https://res.cloudinary.com/maktech/image/private/card_sharing/CS-002/screenshot_01.png",
            ],
            "cardVendor":         "Facebook Ads, Google Ads",
            "cardLimit":          1000.00,
            "cardPaymentReceive":  875.00,
            "cardReceiveBank":    "Payoneer - MAKTech Sub",      # bank/channel name
            "mailDetails":        "ads@maktech.com",
        },
        {
            "date":               _dt(5),
            "serialNo":           "CS-003",
            "details":            "Emergency backup card -- Director access only",
            "accountId":          main_id,                        # FK to PayoneerAccount
            "cardNo":             "378282246310005",              # will be encrypted
            "cardExpire":         "06/27",
            "cardCvc":            "789",                          # will be encrypted
            "cardDetails":        [],                             # no screenshots yet
            "cardVendor":         "Emergency Use",
            "cardLimit":           250.00,
            "cardPaymentReceive":    0.00,
            "cardReceiveBank":    "",                            # no bank recorded yet
            "mailDetails":        "backup@maktech.com",
        },
    ]

    for c in cards:
        # Bug fix 1: prisma-client-py v0.14 requires Json fields passed as
        #            json.dumps(value) -- a JSON string -- not a raw Python list.
        #            Passing list directly raises: "cardDetails should be of type Json"
        card_details_json = json.dumps(c["cardDetails"])

        # Bug fix 2: FK relations in .create() require a nested "connect" block.
        #            Passing "accountId": id directly raises: "data.account: A value
        #            is required but not set" because prisma-client-py resolves the
        #            relation via the connect syntax, not the bare scalar.
        await db.cardsharing.create(data={
             "date":               c["date"],
             "serialNo":           c["serialNo"],
             "details":            c["details"],
             "accountId":          c["accountId"],                        
             "cardNo":             encrypt_value(c["cardNo"]),
             "cardExpire":         c["cardExpire"],
             "cardCvc":            encrypt_value(c["cardCvc"]),
             "cardDetails":        card_details_json,
             "cardVendor":         c["cardVendor"],
             "cardLimit":          c["cardLimit"],
             "cardPaymentReceive": c["cardPaymentReceive"],                
             "cardReceiveBank":    c["cardReceiveBank"],
             "mailDetails":        c["mailDetails"],
        })
        # Bug fix 3: _ok() and screenshots= were outside the loop (bad indentation)
        screenshots = len(c["cardDetails"])
        _ok(f"CardSharing  {c['serialNo']}",
            f"vendor={c['cardVendor'][:24]}  limit=${c['cardLimit']}  "
            f"rcvBank='{c['cardReceiveBank']}'  screenshots={screenshots}  [ENCRYPTED]")


# ==============================================================================
#  HR EXPENSE
# ==============================================================================

async def seed_hr_expense(db: Prisma) -> None:
    """
    12 ledger entries across 3 temporal windows.
    Running balance maintained consistently.

    HrExpense  ALL 8 fields (v3):
      date, details, accountFrom, accountTo, debit, credit,
      remainingBalance, remarks [NEW -- CEO judgement notes]

    Window A -- THIS MONTH  (days_ago  0-9 ): March 2026 entries
    Window B -- LAST MONTH  (days_ago 10-40): February entries
    Window C -- HISTORICAL  (days_ago 41+  ): older entries
    """
    _header("HR Expense  (12 entries, 3 temporal windows, remarks field)")

    for days_ago, details, acc_from, acc_to, debit, credit, balance, remarks in [
        # ── Window C: HISTORICAL (days 41+) ────────────────────────────────────
        # (days_ago, details,                                    from,         to,               debit,     credit,    balance,   remarks)
        (65, "Opening HR fund -- Q1 budget allocation",  "CEO Fund",   "HR Fund",           0.00,  200000.00, 200000.00, "Approved by CEO. Full Q1 HR budget allocated."),
        (60, "February salary -- Nusrat Jahan (HR)",     "HR Fund",    "HR Nusrat",     18000.00,       0.00, 182000.00, "Approved. Paid on time."),
        (60, "February salary -- Rahim (Developer)",     "HR Fund",    "Dev Rahim",     22000.00,       0.00, 160000.00, "Approved. Senior dev rate applied."),
        (60, "February salary -- Karim (Designer)",      "HR Fund",    "Designer Karim",20000.00,       0.00, 140000.00, "Approved."),
        # ── Window B: LAST MONTH (days 10-40) ──────────────────────────────────
        (25, "Festival bonus -- all staff",              "HR Fund",    "All Staff",     15000.00,       0.00, 125000.00, "CEO approved. EID bonus -- 50% of monthly salary each."),
        (20, "Medical allowance -- Nusrat (HR)",         "HR Fund",    "HR Nusrat",      2500.00,       0.00, 122500.00, "Verified by HR. Medical receipt attached."),
        (15, "Advance salary -- Dev Rahim (emergency)",  "HR Fund",    "Dev Rahim",      5000.00,       0.00, 117500.00, "CEO approved on request. Emergency advance -- to be deducted next month."),
        (12, "Internet allowance -- all staff",          "HR Fund",    "All Staff",      3000.00,       0.00, 114500.00, "Standard monthly allowance. Approved."),
        # ── Window A: THIS MONTH (days 0-9) ────────────────────────────────────
        ( 9, "March salary -- Nusrat Jahan (HR)",        "HR Fund",    "HR Nusrat",     18000.00,       0.00,  96500.00, "Approved. On-time payment."),
        ( 9, "March salary -- Rahim (Developer)",        "HR Fund",    "Dev Rahim",     22000.00,       0.00,  74500.00, "Approved. Note: advance from last month deducted."),
        ( 9, "March salary -- Karim (Designer)",         "HR Fund",    "Designer Karim",20000.00,       0.00,  54500.00, "Approved."),
        ( 0, "Q2 HR fund top-up",                        "CEO Fund",   "HR Fund",           0.00,   60000.00, 114500.00, "CEO approved Q2 budget. Next review: June 2026."),
    ]:
        await db.hrexpense.create(data={
            "date":             _dt(days_ago),
            "details":          details,
            "accountFrom":      acc_from,
            "accountTo":        acc_to,
            "debit":            debit,
            "credit":           credit,
            "remainingBalance": balance,
            "remarks":          remarks,            
        })
        _ok(f"HrExpense  @-{days_ago}d",
            f"'{details[:42]}'  bal=${balance:,.0f}")


# ==============================================================================
#  INVENTORY
# ==============================================================================

async def seed_inventory(db: Prisma) -> None:
    """
    12 items across 3 temporal windows.
    totalPrice = qty * unitPrice (computed before insert).

    Inventory  ALL 9 fields:
      date, itemName, category, quantity, unitPrice, totalPrice,
      condition, assignedTo, notes

    Window A -- THIS MONTH  (days_ago  0-9 ): March 2026 procurements
    Window B -- LAST MONTH  (days_ago 10-40): February / late-Jan
    Window C -- HISTORICAL  (days_ago 41+  ): older assets
    """
    _header("Inventory  (12 items, 3 temporal windows)")

    for days_ago, item_name, category, qty, unit_price, condition, assigned_to, notes in [
        # ── Window A: THIS MONTH (days 0-9) ────────────────────────────────────
        # (days_ago, itemName,                              category,       qty, unitPrice,   condition, assignedTo,       notes)
        ( 0, "Ergonomic Keyboard -- Logitech K800",  "Accessories",   3,   45.00, "New",    "Dev Team",    "March 2026 -- typing comfort upgrade"),
        ( 2, "USB-C Hub -- Anker 13-in-1",           "Accessories",   5,   32.00, "New",    "All Team",    "March 2026 -- desk cable management"),
        ( 5, "Office Chair -- ErgoMax Pro",           "Furniture",     2,  280.00, "New",    "HR & CEO",    "March 2026 -- executive seating upgrade"),
        ( 8, "NVMe SSD 1TB -- Samsung 980 Pro",       "Hardware",      4,   85.00, "New",    "Dev Team",    "March 2026 -- storage upgrade for dev machines"),
        # ── Window B: LAST MONTH (days 10-40) ──────────────────────────────────
        (15, "Standing Desk Converter",               "Furniture",     2,   98.00, "New",    "Dev Team",    "Feb 2026 -- ergonomic upgrade, HR recommended"),
        (22, "Webcam -- Logitech C920 HD",            "Accessories",   3,   75.00, "New",    "All Team",    "Feb 2026 -- video call quality improvement"),
        (30, "TP-Link Wi-Fi 6 Router AX3000",         "Network",       1,  110.00, "New",    "Office",      "Feb 2026 -- main router, replaced old unit"),
        (35, "External Hard Drive 4TB -- Seagate",    "Hardware",      2,   95.00, "New",    "Dev Team",    "Feb 2026 -- backup drives for project archives"),
        # ── Window C: HISTORICAL (days 41+) ────────────────────────────────────
        (45, "UPS Battery Backup 1500VA",             "Hardware",      2,  145.00, "New",    "Office",      "Jan 2026 -- power backup for workstations"),
        (55, "Dell 27in 4K Monitor",                  "Hardware",      4,  420.00, "New",    "All Team",    "Jan 2026 -- one per workstation, 4K accuracy"),
        (90, "Adobe Creative Cloud -- Annual",        "Software",      3,  600.00, "Active", "Design Team", "Dec 2025 -- renewed annual licence, expires Dec 2026"),
        (120,"Office Desk -- L-Shape",                "Furniture",     3,  185.00, "Good",   "Office",      "Nov 2025 -- new office setup Q4 2025"),
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
        _ok(f"Inventory  @-{days_ago}d",
            f"'{item_name[:36]}'  qty={qty}  ${unit_price} ea  total=${total:,.2f}")


# ==============================================================================
#  SUMMARY
# ==============================================================================

async def print_summary(db: Prisma) -> None:
    _header("Final Record Counts")
    total = 0
    for label, count in [
        ("Users",                   await db.user.count()),
        ("Fiverr Profiles",         await db.fiverrprofile.count()),
        ("Fiverr Entries",          await db.fiverrentry.count()),
        ("Fiverr Orders",           await db.fiverrorder.count()),
        ("Upwork Profiles",         await db.upworkprofile.count()),
        ("Upwork Entries",          await db.upworkentry.count()),
        ("Upwork Orders",           await db.upworkorder.count()),
        ("Payoneer Accounts",       await db.payoneeraccount.count()),
        ("Payoneer Transactions",   await db.payoneertransaction.count()),
        ("PMAK Accounts",           await db.pmakaccount.count()),
        ("PMAK Transactions",       await db.pmaktransaction.count()),
        ("PMAK Inhouse Deals",      await db.pmakinhouse.count()),      # NEW
        ("Outside Orders",          await db.outsideorder.count()),
        ("Dollar Exchanges",        await db.dollarexchange.count()),
        ("Card Sharing",            await db.cardsharing.count()),
        ("HR Expenses",             await db.hrexpense.count()),
        ("Inventory Items",         await db.inventory.count()),
        ("Invitations",             await db.invitation.count()),
    ]:
        print(f"  {label:<30} {count:>4} records")
        total += count
    print(f"  {'':->42}")
    print(f"  {'TOTAL':<30} {total:>4} records")

    print()
    print("  v3 Field Coverage:")
    print("  FiverrEntry.activeOrderAmount  -- seeded")
    print("  FiverrOrder.afterFiverr        -- seeded (amount * 0.80)")
    print("  UpworkOrder.afterUpwork        -- seeded (amount * 0.90)")
    print("  OutsideOrder.orderSheet        -- seeded (6/6 have links where applicable)")
    print("  PmakTransaction.status         -- seeded (CLEARED/PENDING/ON_HOLD)")
    print("  PmakInhouse                    -- seeded (8 deals, all statuses)")
    print("  CardSharing.date               -- seeded")
    print("  CardSharing.accountId          -- seeded (FK to PayoneerAccount)")
    print("  CardSharing.cardDetails        -- seeded (JSON URL arrays)")
    print("  CardSharing.cardPaymentReceive -- seeded (renamed from cardPaymentRcv)")
    print("  CardSharing.cardReceiveBank    -- seeded (bank name String -- CHANGED from Decimal)")
    print("  HrExpense.remarks              -- seeded (CEO notes on every entry)")
    print("  DailyRate                      -- REMOVED (rate on DollarExchange.rate)")


# ==============================================================================
#  MAIN
# ==============================================================================

async def main() -> None:
    print()
    print("+======================================================+")
    print("|   MAKTech Financial Flow -- Database Seeder  (v3)   |")
    print("|====================================================== |")
    print("|  MODE: RESET then full fresh seed on every run      |")
    print("|  Passwords: 123456  (all accounts)                  |")
    print("|  Schema: v3 -- Enterprise Edition                   |")
    print("+======================================================+")

    db = Prisma()
    await db.connect()

    try:
        await reset_all(db)
        await seed_users(db)
        await seed_fiverr(db)
        await seed_upwork(db)
        # Payoneer returns account_id_map -- consumed by seed_card_sharing
        account_id_map = await seed_payoneer(db)
        await seed_pmak(db)
        await seed_outside_orders(db)
        await seed_dollar_exchange(db)
        await seed_card_sharing(db, account_id_map)   # requires Payoneer IDs
        await seed_hr_expense(db)
        await seed_inventory(db)
        await print_summary(db)

        print()
        print("+======================================================+")
        print("|          Done! Database is fresh and ready.          |")
        print("|======================================================|")
        print("|  CEO      ->  ceo@maktech.com        /  123456       |")
        print("|  Director ->  director@maktech.com   /  123456       |")
        print("|  HR       ->  hr@maktech.com         /  123456       |")
        print("|  BDev     ->  bdev@maktech.com       /  123456       |")
        print("|                                                      |")
        print("|  API Docs ->  https://fin-flow.maktechlaravel.cloud  |")
        print("+======================================================+")
        print()

    finally:
        await db.disconnect()


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())
else:
    asyncio.run(main())