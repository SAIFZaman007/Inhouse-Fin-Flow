"""
MAKTech Financial Flow — Comprehensive Seed Script
====================================================
Seeds ALL models defined in schema.prisma with rich, realistic demo data.

Models covered:
  ✅ User                  (CEO + Director + HR + BDEV)
  ✅ FiverrProfile         (4 profiles)
  ✅ FiverrEntry           (8 daily snapshots per profile)
  ✅ FiverrOrder           (5 buyer orders per profile)
  ✅ UpworkProfile         (3 profiles)
  ✅ UpworkEntry           (8 daily snapshots per profile)
  ✅ UpworkOrder           (5 client orders per profile)
  ✅ PayoneerAccount       (3 accounts)
  ✅ PayoneerTransaction   (10 ledger entries per account)
  ✅ PmakAccount           (3 accounts)
  ✅ PmakTransaction       (10 ledger entries per account)
  ✅ OutsideOrder          (10 client orders, all statuses)
  ✅ DollarExchange        (12 exchange records, mixed statuses)
  ✅ CardSharing           (5 cards, cardNo + cardCvc Fernet-encrypted)
  ✅ HrExpense             (14 ledger entries — two months)
  ✅ Inventory             (14 items across all categories)
  ✅ PermissionRule        (11 canonical modules, correct per-role defaults)
  ✅ TermsCondition        (1 versioned T&C record)

BEHAVIOUR:
  ▶ Every run = full RESET then fresh seed (no stale data ever)
  ▶ All passwords: 123456

Run with:
  poetry run python scripts/seed.py       (Windows / from project root)
  poetry run python -m scripts.seed       (module style)
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

# ── Path fix: works whether run as script or as module ────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prisma import Json, Prisma
from app.core.security import encrypt_value, hash_password


# ══════════════════════════════════════════════════════════════════════════════
#  CORE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _dt(days_ago: int = 0) -> datetime:
    """
    Return a timezone-aware datetime (UTC midnight) N days ago.
    Prisma Python requires datetime.datetime — NOT datetime.date.
    UTC midnight keeps @db.Date fields consistent across timezones.
    """
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return base - timedelta(days=days_ago)


def _pw(plain: str = "123456") -> str:
    """bcrypt-hash a password for storage."""
    return hash_password(str(plain))


# ── Pretty console output ─────────────────────────────────────────────────────

def _header(title: str) -> None:
    bar = "─" * 58
    print(f"\n┌{bar}┐")
    print(f"│  {title:<56}│")
    print(f"└{bar}┘")


def _ok(label: str, detail: str = "") -> None:
    suffix = f"  {detail}" if detail else ""
    print(f"  ✅  {label}{suffix}")


def _del(label: str, count: int) -> None:
    print(f"  🗑   {label:<32} {count} records deleted")


# ══════════════════════════════════════════════════════════════════════════════
#  RESET — always runs first
# ══════════════════════════════════════════════════════════════════════════════

async def reset_all(db: Prisma) -> None:
    """
    Wipe every table in strict dependency order (children before parents).
    Runs automatically at the start of every seed execution.
    """
    _header("🗑  RESET — Clearing All Tables")

    # Children before parents — strict FK-safe dependency order.
    # CardSharing references PayoneerAccount (FK added in migration
    # 20260326051848_role_matrix_integrated), so CardSharing MUST be
    # deleted before PayoneerAccount. Previously it came after, which
    # had no effect on localhost (no FK enforced) but raises
    # ForeignKeyViolationError on production where the FK now exists.
    steps = [
        ("TermsCondition",      db.termscondition),
        ("PermissionRule",      db.permissionrule),
        ("Invitation",          db.invitation),
        ("FiverrOrder",         db.fiverrorder),
        ("FiverrEntry",         db.fiverrentry),
        ("FiverrProfile",       db.fiverrprofile),
        ("UpworkOrder",         db.upworkorder),
        ("UpworkEntry",         db.upworkentry),
        ("UpworkProfile",       db.upworkprofile),
        ("CardSharing",         db.cardsharing),         # ← BEFORE PayoneerAccount (FK child)
        ("PayoneerTransaction", db.payoneertransaction), # ← BEFORE PayoneerAccount (FK child)
        ("PayoneerAccount",     db.payoneeraccount),     # ← parent, now safe to delete
        ("PmakTransaction",     db.pmaktransaction),
        ("PmakAccount",         db.pmakaccount),
        ("OutsideOrder",        db.outsideorder),
        ("DollarExchange",      db.dollarexchange),
        ("HrExpense",           db.hrexpense),
        ("Inventory",           db.inventory),
        ("User",                db.user),
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
            "passwordHash": _pw(),
            "isActive":     True,
        },
        {
            "name":         "Mahfuz Rahman (Director)",
            "email":        "director@maktech.com",
            "role":         "DIRECTOR",
            "passwordHash": _pw(),
            "isActive":     True,
        },
        {
            "name":         "Nusrat Jahan (HR)",
            "email":        "hr@maktech.com",
            "role":         "HR",
            "passwordHash": _pw(),
            "isActive":     True,
        },
        {
            "name":         "Tanvir Ahmed (BDEV)",
            "email":        "bdev@maktech.com",
            "role":         "BDEV",
            "passwordHash": _pw(),
            "isActive":     True,
        },
    ]

    for u in users:
        await db.user.create(data=u)
        _ok(f"{u['role']:<10}", f"email={u['email']}  password=123456")


# ══════════════════════════════════════════════════════════════════════════════
#  FIVERR
# ══════════════════════════════════════════════════════════════════════════════

async def seed_fiverr(db: Prisma) -> None:
    """
    4 profiles x 8 daily entries x 5 orders = 52 child records.

    Schema fields:
      FiverrProfile : profileName, isActive
      FiverrEntry   : profileId, date, availableWithdraw, notCleared,
                      activeOrders, submitted, withdrawn, sellerPlus, promotion
      FiverrOrder   : profileId, date, buyerName, orderId, amount
    """
    _header("🟢 Fiverr  (4 profiles)")

    profiles = [
        {
            "profileName": "maktech_design",
            "entries": [
                # (days_ago, avail,    notCleared, activeOrders, submitted, withdrawn,  sellerPlus, promotion)
                ( 0, 1250.00,  320.00, 5, 180.00, 400.00, True,   75.00),
                ( 1, 1180.00,  295.00, 4, 160.00, 350.00, True,   60.00),
                ( 2, 1100.00,  250.00, 6, 200.00, 300.00, True,   80.00),
                ( 3,  980.00,  210.00, 3, 140.00, 250.00, True,   55.00),
                ( 7,  850.00,  180.00, 2, 120.00, 200.00, False,   0.00),
                (14,  790.00,  150.00, 2, 110.00, 180.00, False,   0.00),
                (21,  710.00,  120.00, 1,  90.00, 160.00, False,   0.00),
                (30,  640.00,   95.00, 1,  75.00, 140.00, False,   0.00),
            ],
            "orders": [
                # (buyerName,        orderId,         amount, days_ago)
                ("BuyerAlpha",       "FO-2024-0001",  120.00,  1),
                ("BuyerBeta",        "FO-2024-0002",   85.00,  2),
                ("BuyerGamma",       "FO-2024-0003",  200.00,  0),
                ("BuyerDelta",       "FO-2024-0004",   55.00,  5),
                ("BuyerEpsilon",     "FO-2024-0005",  310.00,  9),
            ],
        },
        {
            "profileName": "maktech_dev",
            "entries": [
                ( 0, 2400.00,  580.00, 8, 320.00, 750.00, True,  120.00),
                ( 1, 2200.00,  510.00, 7, 290.00, 680.00, True,  100.00),
                ( 2, 2050.00,  460.00, 6, 260.00, 600.00, True,   90.00),
                ( 3, 1900.00,  400.00, 5, 230.00, 530.00, True,   80.00),
                ( 7, 1650.00,  330.00, 4, 200.00, 450.00, False,   0.00),
                (14, 1520.00,  290.00, 3, 175.00, 400.00, False,   0.00),
                (21, 1380.00,  250.00, 3, 150.00, 360.00, False,   0.00),
                (30, 1200.00,  200.00, 2, 120.00, 300.00, False,   0.00),
            ],
            "orders": [
                ("DevClient_A",      "FO-2024-0010",  350.00,  0),
                ("DevClient_B",      "FO-2024-0011",  180.00,  1),
                ("DevClient_C",      "FO-2024-0012",  420.00,  2),
                ("DevClient_D",      "FO-2024-0013",  275.00,  6),
                ("DevClient_E",      "FO-2024-0014",  510.00, 11),
            ],
        },
        {
            "profileName": "maktech_seo",
            "entries": [
                ( 0,  780.00,  190.00, 3, 110.00, 230.00, False,  30.00),
                ( 1,  720.00,  170.00, 3,  95.00, 200.00, False,  25.00),
                ( 2,  660.00,  145.00, 2,  80.00, 175.00, False,  20.00),
                ( 3,  590.00,  120.00, 2,  70.00, 150.00, False,  15.00),
                ( 7,  510.00,   95.00, 1,  60.00, 120.00, False,   0.00),
                (14,  470.00,   80.00, 1,  50.00, 100.00, False,   0.00),
                (21,  420.00,   65.00, 1,  45.00,  90.00, False,   0.00),
                (30,  380.00,   50.00, 1,  40.00,  80.00, False,   0.00),
            ],
            "orders": [
                ("SEO_ClientX",      "FO-2024-0020",   95.00,  0),
                ("SEO_ClientY",      "FO-2024-0021",  140.00,  3),
                ("SEO_ClientZ",      "FO-2024-0022",   65.00,  1),
                ("SEO_ClientW",      "FO-2024-0023",  110.00,  8),
                ("SEO_ClientV",      "FO-2024-0024",   80.00, 14),
            ],
        },
        {
            "profileName": "maktech_content",
            "entries": [
                ( 0,  960.00,  210.00, 4, 145.00, 280.00, True,   45.00),
                ( 1,  890.00,  185.00, 3, 130.00, 250.00, True,   38.00),
                ( 2,  820.00,  160.00, 3, 115.00, 220.00, True,   30.00),
                ( 3,  750.00,  138.00, 2, 100.00, 190.00, True,   25.00),
                ( 7,  660.00,  110.00, 2,  85.00, 160.00, False,   0.00),
                (14,  600.00,   90.00, 1,  70.00, 140.00, False,   0.00),
                (21,  540.00,   75.00, 1,  60.00, 120.00, False,   0.00),
                (30,  490.00,   60.00, 1,  50.00, 100.00, False,   0.00),
            ],
            "orders": [
                ("ContentCo_A",      "FO-2024-0030",  160.00,  0),
                ("ContentCo_B",      "FO-2024-0031",   90.00,  2),
                ("ContentCo_C",      "FO-2024-0032",  220.00,  4),
                ("ContentCo_D",      "FO-2024-0033",  130.00,  7),
                ("ContentCo_E",      "FO-2024-0034",   75.00, 12),
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
                    "date":              _dt(days_ago),
                    "availableWithdraw": avail,
                    "notCleared":        not_cleared,
                    "activeOrders":      active_orders,
                    "submitted":         submitted,
                    "withdrawn":         withdrawn,
                    "sellerPlus":        seller_plus,
                    "promotion":         promotion,
                }
            )
        _ok(f"  └─ {len(p['entries'])} entries", f"latest avail=${p['entries'][0][1]:,.2f}")

        for buyer_name, order_id, amount, days_ago_o in p["orders"]:
            await db.fiverrorder.create(
                data={
                    "profileId":   profile.id,
                    "date":        _dt(days_ago_o),
                    "buyerName":   buyer_name,
                    "orderId":     order_id,
                    "amount":      amount,
                    "afterFiverr": round(amount * 0.80, 2),
                }
            )
        _ok(f"  └─ {len(p['orders'])} orders")


# ══════════════════════════════════════════════════════════════════════════════
#  UPWORK
# ══════════════════════════════════════════════════════════════════════════════

async def seed_upwork(db: Prisma) -> None:
    """
    3 profiles x 8 daily entries x 5 orders = 39 child records.

    Schema fields:
      UpworkProfile : profileName, isActive
      UpworkEntry   : profileId, date, availableWithdraw, pending, inReview,
                      workInProgress, withdrawn, connects, upworkPlus
      UpworkOrder   : profileId, date, clientName, orderId, amount
    """
    _header("🔵 Upwork  (3 profiles)")

    profiles = [
        {
            "profileName": "maktech_upwork_main",
            "entries": [
                # (days_ago, avail,    pending,  inReview,  wip,     withdrawn, connects, upworkPlus)
                ( 0, 3200.00,  480.00,  650.00, 1200.00,  900.00,  80, True),
                ( 1, 2950.00,  420.00,  580.00, 1100.00,  800.00,  75, True),
                ( 2, 2700.00,  370.00,  510.00,  980.00,  720.00,  70, True),
                ( 3, 2450.00,  310.00,  440.00,  860.00,  640.00,  65, True),
                ( 7, 2100.00,  250.00,  360.00,  720.00,  560.00,  58, True),
                (14, 1900.00,  210.00,  310.00,  650.00,  500.00,  52, True),
                (21, 1720.00,  180.00,  270.00,  580.00,  440.00,  47, True),
                (30, 1550.00,  150.00,  230.00,  500.00,  380.00,  42, True),
            ],
            "orders": [
                # (clientName,           orderId,          amount, days_ago)
                ("TechStartup Ltd",      "UW-2024-0001",   500.00,  0),
                ("Creative Agency BD",   "UW-2024-0002",   320.00,  2),
                ("Global Corp PLC",      "UW-2024-0003",   750.00,  1),
                ("InnovateTech GmbH",    "UW-2024-0004",   610.00,  5),
                ("DataDriven Inc",       "UW-2024-0005",   430.00,  9),
            ],
        },
        {
            "profileName": "maktech_upwork_sub",
            "entries": [
                ( 0, 1100.00,  220.00,  310.00,  450.00,  380.00,  40, False),
                ( 1,  980.00,  190.00,  270.00,  400.00,  340.00,  38, False),
                ( 2,  880.00,  160.00,  230.00,  360.00,  300.00,  35, False),
                ( 3,  780.00,  130.00,  190.00,  310.00,  260.00,  32, False),
                ( 7,  650.00,  100.00,  150.00,  250.00,  200.00,  28, False),
                (14,  580.00,   85.00,  125.00,  210.00,  175.00,  24, False),
                (21,  510.00,   70.00,  105.00,  180.00,  150.00,  20, False),
                (30,  440.00,   55.00,   85.00,  150.00,  120.00,  16, False),
            ],
            "orders": [
                ("SmallBiz Owner",       "UW-2024-0010",   180.00,  0),
                ("Freelance Buyer",      "UW-2024-0011",    95.00,  1),
                ("E-commerce Store",     "UW-2024-0012",   260.00,  3),
                ("LocalBrand BD",        "UW-2024-0013",   145.00,  7),
                ("Boutique Agency",      "UW-2024-0014",   210.00, 12),
            ],
        },
        {
            "profileName": "maktech_upwork_dev2",
            "entries": [
                ( 0, 1750.00,  340.00,  420.00,  680.00,  520.00,  55, True),
                ( 1, 1620.00,  300.00,  380.00,  620.00,  470.00,  52, True),
                ( 2, 1490.00,  265.00,  340.00,  560.00,  420.00,  48, True),
                ( 3, 1360.00,  230.00,  300.00,  500.00,  370.00,  44, True),
                ( 7, 1180.00,  190.00,  250.00,  420.00,  310.00,  39, True),
                (14, 1060.00,  160.00,  210.00,  370.00,  270.00,  35, True),
                (21,  950.00,  135.00,  178.00,  320.00,  235.00,  31, True),
                (30,  840.00,  110.00,  148.00,  270.00,  200.00,  27, True),
            ],
            "orders": [
                ("SaaS Venture Co",      "UW-2024-0020",   620.00,  0),
                ("HealthTech BV",        "UW-2024-0021",   390.00,  2),
                ("EduPlatform Ltd",      "UW-2024-0022",   510.00,  4),
                ("RetailChain PLC",      "UW-2024-0023",   280.00,  8),
                ("FinTech Startup",      "UW-2024-0024",   740.00, 13),
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
                    "profileId":         profile.id,
                    "date":              _dt(days_ago),
                    "availableWithdraw": avail,
                    "pending":           pending,
                    "inReview":          in_review,
                    "workInProgress":    wip,
                    "withdrawn":         withdrawn,
                    "connects":          connects,
                    "upworkPlus":        upwork_plus,
                }
            )
        _ok(f"  └─ {len(p['entries'])} entries", f"latest avail=${p['entries'][0][1]:,.2f}")

        for client_name, order_id, amount, days_ago_o in p["orders"]:
            await db.upworkorder.create(
                data={
                    "profileId":   profile.id,
                    "date":        _dt(days_ago_o),
                    "clientName":  client_name,
                    "orderId":     order_id,
                    "amount":      amount,
                    "afterUpwork": round(amount * 0.90, 2),
                }
            )
        _ok(f"  └─ {len(p['orders'])} orders")


# ══════════════════════════════════════════════════════════════════════════════
#  PAYONEER
# ══════════════════════════════════════════════════════════════════════════════

async def seed_payoneer(db: Prisma) -> None:
    """
    3 accounts x 10 ledger transactions = 30 records.

    Schema fields:
      PayoneerAccount     : accountName, isActive
      PayoneerTransaction : accountId, date, details, accountFrom, accountTo,
                            debit, credit, remainingBalance
    """
    _header("💳 Payoneer  (3 accounts)")

    accounts = [
        {
            "accountName": "Payoneer - MAKTech Main",
            "transactions": [
                # (days_ago, details,                                        from,              to,               debit,    credit,   balance)
                (60, "Initial deposit from Fiverr withdrawal",       "Fiverr",          "Payoneer Main",      0.00,  1500.00, 1500.00),
                (55, "Service fee deduction — monthly",              "Payoneer Main",   "Payoneer Fee",      12.50,     0.00, 1487.50),
                (45, "Received from Upwork withdrawal",              "Upwork",          "Payoneer Main",      0.00,   900.00, 2387.50),
                (38, "Transfer to PMAK BDT account",                 "Payoneer Main",   "PMAK Main",        800.00,     0.00, 1587.50),
                (30, "Fiverr monthly withdrawal — March",            "Fiverr",          "Payoneer Main",      0.00,  1200.00, 2787.50),
                (22, "Exchange to BDT via Motijheel agent",          "Payoneer Main",   "Exchanger Kamal",  500.00,     0.00, 2287.50),
                (15, "Received from Upwork project milestone",       "Upwork",          "Payoneer Main",      0.00,   650.00, 2937.50),
                ( 9, "Transfer to PMAK — April operations",         "Payoneer Main",   "PMAK Main",        900.00,     0.00, 2037.50),
                ( 4, "Fiverr bi-weekly withdrawal",                  "Fiverr",          "Payoneer Main",      0.00,   800.00, 2837.50),
                ( 0, "Service fee — April",                          "Payoneer Main",   "Payoneer Fee",      12.50,     0.00, 2825.00),
            ],
        },
        {
            "accountName": "Payoneer - MAKTech Sub",
            "transactions": [
                (58, "Initial load from card sharing program",       "Card Vendor",     "Payoneer Sub",       0.00,   400.00,  400.00),
                (50, "Subscription payment — Adobe CC",              "Payoneer Sub",    "Adobe Inc",         54.99,     0.00,  345.01),
                (42, "Client payment received — overseas",           "Client Overseas", "Payoneer Sub",       0.00,   250.00,  595.01),
                (35, "Tool license renewal — Semrush",               "Payoneer Sub",    "Semrush",           89.00,     0.00,  506.01),
                (28, "Top-up from Fiverr profile",                   "Fiverr",          "Payoneer Sub",       0.00,   300.00,  806.01),
                (20, "International transfer fee",                    "Payoneer Sub",    "Fee",                5.50,     0.00,  800.51),
                (14, "Ad spend top-up — Facebook & Google",          "Payoneer Sub",    "Ad Platforms",     150.00,     0.00,  650.51),
                ( 8, "Incoming client retainer — UK agency",         "UK Agency",       "Payoneer Sub",       0.00,   500.00, 1150.51),
                ( 3, "Withdrawal to PMAK Petty Cash",                "Payoneer Sub",    "PMAK Petty",       200.00,     0.00,  950.51),
                ( 0, "Monthly balance snapshot",                     "Payoneer Sub",    "Record",             0.00,     0.00,  950.51),
            ],
        },
        {
            "accountName": "Payoneer - MAKTech Reserve",
            "transactions": [
                (90, "Reserve fund allocation from Main",            "Payoneer Main",   "Reserve",            0.00,  2000.00, 2000.00),
                (80, "Emergency tool renewal — server hosting",      "Reserve",         "DigitalOcean",     120.00,     0.00, 1880.00),
                (70, "Quarterly tax provision transfer",             "Reserve",         "Tax Account",      500.00,     0.00, 1380.00),
                (60, "Top-up from main operations",                  "Payoneer Main",   "Reserve",            0.00,  1000.00, 2380.00),
                (50, "Domain & SSL renewals — annual",               "Reserve",         "Namecheap",         85.00,     0.00, 2295.00),
                (40, "Emergency salary advance — covered",           "Reserve",         "Staff Advance",    300.00,     0.00, 1995.00),
                (30, "Replenishment from Main",                      "Payoneer Main",   "Reserve",            0.00,   500.00, 2495.00),
                (20, "Server upgrade costs",                         "Reserve",         "DigitalOcean",     240.00,     0.00, 2255.00),
                (10, "Office equipment fund contribution",           "Reserve",         "Equipment Fund",   400.00,     0.00, 1855.00),
                ( 0, "Top-up — end of month rebalance",              "Payoneer Main",   "Reserve",            0.00,   600.00, 2455.00),
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
                    "date":             _dt(days_ago),
                    "details":          details,
                    "accountFrom":      acc_from,
                    "accountTo":        acc_to,
                    "debit":            debit,
                    "credit":           credit,
                    "remainingBalance": balance,
                }
            )
        _ok(f"  └─ {len(acc['transactions'])} transactions",
            f"closing balance=${acc['transactions'][-1][6]:,.2f}")


# ══════════════════════════════════════════════════════════════════════════════
#  PMAK
# ══════════════════════════════════════════════════════════════════════════════

async def seed_pmak(db: Prisma) -> None:
    """
    3 accounts x 10 ledger transactions = 30 records.

    Schema fields:
      PmakAccount     : accountName, isActive
      PmakTransaction : accountId, date, details, accountFrom, accountTo,
                        debit, credit, remainingBalance
    """
    _header("🏦 PMAK  (3 accounts)")

    accounts = [
        {
            "accountName": "PMAK - Main BDT Account",
            "transactions": [
                # (days_ago, details,                                       from,              to,              debit,     credit,     balance)
                (60, "Opening balance — fund from Payoneer exchange",  "Payoneer Main",  "PMAK Main",         0.00,  88000.00,  88000.00),
                (55, "Office rent — March",                            "PMAK Main",      "Landlord",      25000.00,      0.00,  63000.00),
                (50, "Salary disbursement — March",                    "PMAK Main",      "Staff",         30000.00,      0.00,  33000.00),
                (45, "New fund — dollar exchange Motijheel",           "Exchanger",      "PMAK Main",         0.00,  55000.00,  88000.00),
                (38, "Internet & utilities — March",                   "PMAK Main",      "DESCO / ISP",    4500.00,      0.00,  83500.00),
                (30, "Equipment purchase — monitors",                  "PMAK Main",      "Vendor",        12000.00,      0.00,  71500.00),
                (22, "Top-up from Payoneer withdrawal",                "Payoneer Sub",   "PMAK Main",         0.00,  40000.00, 111500.00),
                (15, "Office rent — April",                            "PMAK Main",      "Landlord",      25000.00,      0.00,  86500.00),
                ( 7, "Salary disbursement — April",                    "PMAK Main",      "Staff",         32000.00,      0.00,  54500.00),
                ( 0, "Fund from Payoneer Main — April top-up",         "Payoneer Main",  "PMAK Main",         0.00,  60000.00, 114500.00),
            ],
        },
        {
            "accountName": "PMAK - Petty Cash",
            "transactions": [
                (60, "Initial allocation from Main",                   "PMAK Main",      "Petty Cash",        0.00,  10000.00,  10000.00),
                (55, "Office supplies — stationery & printer ink",     "Petty Cash",     "Shop",           2500.00,      0.00,   7500.00),
                (48, "Transport & team meals",                         "Petty Cash",     "Staff",          1800.00,      0.00,   5700.00),
                (40, "Replenishment from Main",                        "PMAK Main",      "Petty Cash",        0.00,   8000.00,  13700.00),
                (32, "Miscellaneous expenses — maintenance",           "Petty Cash",     "Various",        3200.00,      0.00,  10500.00),
                (24, "Client visit hospitality",                       "Petty Cash",     "Hospitality",    1500.00,      0.00,   9000.00),
                (16, "Replenishment from Main",                        "PMAK Main",      "Petty Cash",        0.00,   5000.00,  14000.00),
                ( 9, "Courier & postage costs",                        "Petty Cash",     "Courier",         850.00,      0.00,  13150.00),
                ( 4, "Emergency repairs — office AC unit",             "Petty Cash",     "Technician",     2800.00,      0.00,  10350.00),
                ( 0, "Replenishment — month-end",                      "PMAK Main",      "Petty Cash",        0.00,   5000.00,  15350.00),
            ],
        },
        {
            "accountName": "PMAK - Project Escrow",
            "transactions": [
                (45, "Client advance — Rahman Enterprise project",     "Rahman Ent",     "Escrow",            0.00,  30000.00,  30000.00),
                (40, "Milestone 1 released to dev team",               "Escrow",         "Dev Team",      10000.00,      0.00,  20000.00),
                (35, "Client advance — BDTech project",               "BDTech",         "Escrow",            0.00,  25000.00,  45000.00),
                (28, "Milestone 2 released — Rahman Enterprise",       "Escrow",         "Dev Team",      10000.00,      0.00,  35000.00),
                (20, "Client advance — Hasan Agency",                 "Hasan Agency",   "Escrow",            0.00,  15000.00,  50000.00),
                (14, "Milestone 1 released — BDTech",                 "Escrow",         "Dev Team",       8000.00,      0.00,  42000.00),
                ( 9, "Final payment — Rahman Enterprise delivered",    "Escrow",         "PMAK Main",     25000.00,      0.00,  17000.00),
                ( 5, "New client advance — Taslim Brothers",          "Taslim Bros",    "Escrow",            0.00,  20000.00,  37000.00),
                ( 2, "Milestone 2 released — Hasan Agency",           "Escrow",         "Dev Team",       7500.00,      0.00,  29500.00),
                ( 0, "Month-end escrow reconciliation",                "Escrow",         "Record",            0.00,      0.00,  29500.00),
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
                    "date":             _dt(days_ago),
                    "details":          details,
                    "accountFrom":      acc_from,
                    "accountTo":        acc_to,
                    "debit":            debit,
                    "credit":           credit,
                    "remainingBalance": balance,
                }
            )
        _ok(f"  └─ {len(acc['transactions'])} transactions",
            f"closing balance=৳{acc['transactions'][-1][6]:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
#  OUTSIDE ORDERS
# ══════════════════════════════════════════════════════════════════════════════

async def seed_outside_orders(db: Prisma) -> None:
    """
    10 orders — all OrderStatus values represented, realistic BD clients.

    Schema fields:
      OutsideOrder: date, clientId, clientName, clientLink, orderDetails,
                    orderSheet, assignTeam, orderStatus, orderAmount,
                    receiveAmount, dueAmount, paymentMethod, paymentMethodDetails
    """
    _header("📦 Outside Orders  (10 orders)")

    orders = [
        {
            "date":                 _dt(60),
            "clientId":             "CLT-001",
            "clientName":           "Rahman Enterprise",
            "clientLink":           "https://facebook.com/rahmanenterprise",
            "orderDetails":         "Full website redesign with SEO optimization and 6-month support",
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
            "date":                 _dt(45),
            "clientId":             "CLT-002",
            "clientName":           "Karim Solutions Ltd",
            "clientLink":           "https://linkedin.com/company/karim-solutions",
            "orderDetails":         "Social media management — 3 platforms, 30 posts/month for 3 months",
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
            "date":                 _dt(30),
            "clientId":             "CLT-003",
            "clientName":           "Hasan Digital Agency",
            "clientLink":           "mailto:hasan@digitalagency.com",
            "orderDetails":         "WordPress e-commerce site with payment gateway integration",
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
            "date":                 _dt(55),
            "clientId":             "CLT-004",
            "clientName":           "Taslim Brothers Import",
            "clientLink":           "+8801911-234567",
            "orderDetails":         "Product photography — 200 SKUs, edited and delivered in 5 days",
            "orderSheet":           None,
            "assignTeam":           "Design Team",
            "orderStatus":          "COMPLETED",
            "orderAmount":          18000.00,
            "receiveAmount":        18000.00,
            "dueAmount":            0.00,
            "paymentMethod":        "Cash",
            "paymentMethodDetails": "Cash payment at office",
        },
        {
            "date":                 _dt(20),
            "clientId":             "CLT-005",
            "clientName":           "BDTech Startup Hub",
            "clientLink":           "https://bdtechhub.com",
            "orderDetails":         "Mobile app UI/UX design — 40 screens, Figma deliverable",
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
            "date":                 _dt(15),
            "clientId":             "CLT-006",
            "clientName":           "Al-Amin Garments Ltd",
            "clientLink":           "https://alamingarments.com",
            "orderDetails":         "Brand identity package — logo, stationery, packaging design",
            "orderSheet":           None,
            "assignTeam":           "Design Team",
            "orderStatus":          "COMPLETED",
            "orderAmount":          35000.00,
            "receiveAmount":        35000.00,
            "dueAmount":            0.00,
            "paymentMethod":        "Bank Transfer",
            "paymentMethodDetails": "Islami Bank  A/C: 2345678901",
        },
        {
            "date":                 _dt(10),
            "clientId":             "CLT-007",
            "clientName":           "Dhaka Food & Beverage Co",
            "clientLink":           "+8801755-112233",
            "orderDetails":         "Menu & catalogue design, print-ready files, 500 copies",
            "orderSheet":           None,
            "assignTeam":           "Design Team",
            "orderStatus":          "IN_PROGRESS",
            "orderAmount":          22000.00,
            "receiveAmount":        11000.00,
            "dueAmount":            11000.00,
            "paymentMethod":        "bKash",
            "paymentMethodDetails": "bKash Merchant: 01622-998877",
        },
        {
            "date":                 _dt(5),
            "clientId":             "CLT-008",
            "clientName":           "Greenfield Real Estate",
            "clientLink":           "https://greenfieldbd.com",
            "orderDetails":         "Corporate website + CRM integration, 6-month AMC",
            "orderSheet":           None,
            "assignTeam":           "Dev Team",
            "orderStatus":          "PENDING",
            "orderAmount":          120000.00,
            "receiveAmount":        30000.00,
            "dueAmount":            90000.00,
            "paymentMethod":        "Bank Transfer",
            "paymentMethodDetails": "Southeast Bank  A/C: 5678901234",
        },
        {
            "date":                 _dt(3),
            "clientId":             "CLT-009",
            "clientName":           "Pioneer Pharmaceuticals",
            "clientLink":           "https://pioneerpharma.com",
            "orderDetails":         "Annual report design + digital PDF — 80 pages",
            "orderSheet":           None,
            "assignTeam":           "Design Team",
            "orderStatus":          "PENDING",
            "orderAmount":          40000.00,
            "receiveAmount":        20000.00,
            "dueAmount":            20000.00,
            "paymentMethod":        "Nagad",
            "paymentMethodDetails": "Nagad: 01833-445566",
        },
        {
            "date":                 _dt(0),
            "clientId":             "CLT-010",
            "clientName":           "Chittagong Port Authority",
            "clientLink":           "mailto:procurement@cpa.gov.bd",
            "orderDetails":         "Staff training portal — LMS development, 200 users",
            "orderSheet":           None,
            "assignTeam":           "Dev Team",
            "orderStatus":          "CANCELLED",
            "orderAmount":          200000.00,
            "receiveAmount":        0.00,
            "dueAmount":            0.00,
            "paymentMethod":        "Bank Transfer",
            "paymentMethodDetails": "Sonali Bank  A/C: 0011223344",
        },
    ]

    for o in orders:
        await db.outsideorder.create(data=o)
        _ok(
            f"OutsideOrder  {o['clientId']}",
            f"{o['clientName'][:28]:<28}  ৳{o['orderAmount']:>10,.0f}  [{o['orderStatus']}]",
        )


# ══════════════════════════════════════════════════════════════════════════════
#  DOLLAR EXCHANGE
# ══════════════════════════════════════════════════════════════════════════════

async def seed_dollar_exchange(db: Prisma) -> None:
    """
    12 exchange records — mix of RECEIVED / DUE, buys and sells.
    totalBdt = exchange_amount x rate (computed before insert).

    Schema fields:
      DollarExchange: date, details, accountFrom, accountTo,
                      debit, credit, rate, totalBdt, paymentStatus
    """
    _header("💱 Dollar Exchange  (12 records)")

    exchanges = [
        # (days_ago, details,                                         from,              to,                debit,    credit,   rate,    status)
        (60, "Sold $500 to agent — Motijheel March",           "Payoneer Main",   "Exchanger Kamal",   500.00,    0.00,  109.50, "RECEIVED"),
        (55, "Sold $300 to broker — Gulshan",                  "Payoneer Main",   "Broker Rahim",      300.00,    0.00,  110.00, "RECEIVED"),
        (48, "Sold $800 — rate locked pre-weekend",            "Payoneer Sub",    "Exchanger Hasan",   800.00,    0.00,  109.75, "RECEIVED"),
        (42, "Bought $200 — emergency import rate",            "Exchanger Ali",   "Payoneer Main",       0.00,  200.00,  111.00, "RECEIVED"),
        (35, "Sold $600 to preferred broker",                  "Payoneer Main",   "Broker Salam",      600.00,    0.00,  110.25, "RECEIVED"),
        (28, "Sold $1000 — bulk rate negotiated",              "Payoneer Main",   "Exchanger Kamal",  1000.00,    0.00,  110.50, "RECEIVED"),
        (21, "Bought $400 for PMAK staff disbursement",        "Exchanger Hasan", "Payoneer Main",       0.00,  400.00,  110.80, "RECEIVED"),
        (14, "Sold $750 — mid-month clearance",                "Payoneer Sub",    "Broker Rahim",      750.00,    0.00,  110.40, "RECEIVED"),
        ( 9, "Sold $450 to new agent — test transaction",      "Payoneer Main",   "New Agent Jalal",   450.00,    0.00,  110.10, "DUE"),
        ( 5, "Sold $900 — weekend rate premium",               "Payoneer Main",   "Exchanger Kamal",   900.00,    0.00,  111.25, "DUE"),
        ( 2, "Sold $650 — urgent clearance",                   "Payoneer Sub",    "Broker Salam",      650.00,    0.00,  110.90, "DUE"),
        ( 0, "Sold $1200 — today's best rate",                 "Payoneer Main",   "Exchanger Kamal",  1200.00,    0.00,  111.50, "DUE"),
    ]

    for ex in exchanges:
        days_ago, details, acc_from, acc_to, debit, credit, rate, status = ex
        exchange_amount = credit if credit > 0 else debit
        total_bdt = round(exchange_amount * rate, 2)

        await db.dollarexchange.create(
            data={
                "date":          _dt(days_ago),
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
            f"${exchange_amount:>6.0f} x {rate} = ৳{total_bdt:>10,.2f}  [{status}]",
        )


# ══════════════════════════════════════════════════════════════════════════════
#  CARD SHARING
# ══════════════════════════════════════════════════════════════════════════════

async def seed_card_sharing(db: Prisma) -> None:
    """
    5 cards. cardNo and cardCvc are Fernet-encrypted before DB insert.

    Schema fields (v5):
      CardSharing: serialNo, date, details, account (connect by name),
                   cardNo (encrypted), cardExpire, cardCvc (encrypted),
                   cardDetails (Json[]), cardVendor, cardLimit,
                   cardPaymentReceive, cardReceiveBank, mailDetails
    """
    _header("🃏 Card Sharing  (5 cards, cardNo & CVC encrypted)")

    # (serialNo, days_ago, details, accountName, cardNo, cardExpire, cardCvc,
    #  cardVendor, cardLimit, cardPaymentReceive, cardReceiveBank, mailDetails)
    cards = [
        (
            "CS-001",  5,
            "Primary virtual card — SaaS tool subscriptions",
            "Payoneer - MAKTech Main",
            "4111111111111111", "09/26", "123",
            "Notion, Canva, Figma",
            500.00, 320.00, "Payoneer Main Balance", "cards@maktech.com",
        ),
        (
            "CS-002", 10,
            "Secondary card — Facebook & Google Ads spend",
            "Payoneer - MAKTech Sub",
            "5500000000000004", "12/25", "456",
            "Facebook Ads, Google Ads",
            1000.00, 875.00, "Payoneer Sub Balance", "ads@maktech.com",
        ),
        (
            "CS-003", 15,
            "Emergency backup card — Director access only",
            "Payoneer - MAKTech Main",
            "378282246310005", "06/27", "789",
            "Emergency Use",
            250.00, 0.00, "", "backup@maktech.com",
        ),
        (
            "CS-004", 20,
            "Dev tools & infrastructure card",
            "Payoneer - MAKTech Reserve",
            "4000056655665556", "03/27", "321",
            "DigitalOcean, GitHub, JetBrains",
            800.00, 610.00, "Payoneer Reserve Balance", "devops@maktech.com",
        ),
        (
            "CS-005", 25,
            "AI & productivity tools — CEO direct use",
            "Payoneer - MAKTech Main",
            "5425233430109903", "11/26", "654",
            "OpenAI, Anthropic, Grammarly",
            300.00, 185.00, "Payoneer Main Balance", "ceo@maktech.com",
        ),
    ]

    for (
        serial_no, days_ago, details, account_name,
        card_no, card_expire, card_cvc,
        card_vendor, card_limit, card_payment_receive, card_receive_bank,
        mail_details,
    ) in cards:
        account = await db.payoneeraccount.find_first(
            where={"accountName": {"equals": account_name, "mode": "insensitive"}}
        )
        if not account:
            raise RuntimeError(
                f"Payoneer account '{account_name}' not found — "
                "ensure seed_payoneer() ran before seed_card_sharing()."
            )

        await db.cardsharing.create(
            data={
                "serialNo":           serial_no,
                "date":               _dt(days_ago),
                "details":            details,
                "account":            {"connect": {"id": account.id}},
                "cardNo":             encrypt_value(card_no),
                "cardExpire":         card_expire,
                "cardCvc":            encrypt_value(card_cvc),
                "cardDetails":        Json([]),
                "cardVendor":         card_vendor,
                "cardLimit":          card_limit,
                "cardPaymentReceive": card_payment_receive,
                "cardReceiveBank":    card_receive_bank,
                "mailDetails":        mail_details,
            }
        )
        _ok(
            f"CardSharing  {serial_no}",
            f"vendor={card_vendor[:28]:<28}  limit=${card_limit:>7,.0f}  [ENCRYPTED]",
        )


# ══════════════════════════════════════════════════════════════════════════════
#  HR EXPENSE
# ══════════════════════════════════════════════════════════════════════════════

async def seed_hr_expense(db: Prisma) -> None:
    """
    14 ledger entries covering two full payroll months.

    Schema fields:
      HrExpense: date, details, accountFrom, accountTo,
                 debit, credit, remainingBalance
    """
    _header("💰 HR Expense  (14 entries — 2 months)")

    expenses = [
        # (days_ago, details,                                              from,            to,                  debit,    credit,    balance)
        # ── March payroll ──────────────────────────────────────────────────────────────────────────────────────
        (60, "March salary — Nusrat Jahan (HR Manager)",            "PMAK Main",  "Nusrat Jahan",        18000.00,     0.00,  82000.00),
        (60, "March salary — Rahim Uddin (Lead Dev)",               "PMAK Main",  "Rahim Uddin",         22000.00,     0.00,  60000.00),
        (60, "March salary — Karim Hossain (Sr. Designer)",         "PMAK Main",  "Karim Hossain",       20000.00,     0.00,  40000.00),
        (60, "March salary — Sumaiya Akter (Jr. Dev)",              "PMAK Main",  "Sumaiya Akter",       14000.00,     0.00,  26000.00),
        (55, "Eid festival bonus — all staff (4 persons)",          "PMAK Main",  "All Staff",           20000.00,     0.00,   6000.00),
        (50, "Medical allowance reimbursement — Nusrat",            "PMAK Main",  "Nusrat Jahan",         2500.00,     0.00,   3500.00),
        (45, "Fund allocation — April salaries",                    "Payoneer Main", "PMAK Main",             0.00, 80000.00,  83500.00),
        # ── April payroll ──────────────────────────────────────────────────────────────────────────────────────
        (30, "April salary — Nusrat Jahan (HR Manager)",            "PMAK Main",  "Nusrat Jahan",        18000.00,     0.00,  65500.00),
        (30, "April salary — Rahim Uddin (Lead Dev)",               "PMAK Main",  "Rahim Uddin",         22000.00,     0.00,  43500.00),
        (30, "April salary — Karim Hossain (Sr. Designer)",         "PMAK Main",  "Karim Hossain",       20000.00,     0.00,  23500.00),
        (30, "April salary — Sumaiya Akter (Jr. Dev)",              "PMAK Main",  "Sumaiya Akter",       14000.00,     0.00,   9500.00),
        (22, "Performance bonus — Rahim (project delivery)",        "PMAK Main",  "Rahim Uddin",          5000.00,     0.00,   4500.00),
        ( 7, "Performance bonus — Karim (client praise)",           "PMAK Main",  "Karim Hossain",        3000.00,     0.00,   1500.00),
        ( 0, "Fund allocation — May salaries",                      "Payoneer Main", "PMAK Main",             0.00, 80000.00,  81500.00),
    ]

    for exp in expenses:
        days_ago, details, acc_from, acc_to, debit, credit, balance = exp
        await db.hrexpense.create(
            data={
                "date":             _dt(days_ago),
                "details":          details,
                "accountFrom":      acc_from,
                "accountTo":        acc_to,
                "debit":            debit,
                "credit":           credit,
                "remainingBalance": balance,
            }
        )
        _ok(f"HrExpense", f"'{details[:44]}'  balance=৳{balance:>10,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
#  INVENTORY
# ══════════════════════════════════════════════════════════════════════════════

async def seed_inventory(db: Prisma) -> None:
    """
    14 items across Hardware, Software, Accessories, Furniture, Network.
    totalPrice = quantity x unitPrice (computed, then stored).

    Schema fields:
      Inventory: date, itemName, category, quantity, unitPrice,
                 totalPrice, condition, assignedTo, notes
    """
    _header("📋 Inventory  (14 items)")

    items = [
        # (days_ago, itemName,                                      category,      qty, unitPrice,   condition,  assignedTo,       notes)
        (120, "Apple MacBook Pro 14\" M3 Pro",                "Hardware",      2,  195000.00, "New",      "Dev Team",       "Primary dev machines — March 2024"),
        (120, "Apple MacBook Air M2",                          "Hardware",      2,   95000.00, "New",      "Design Team",    "Design workstations — March 2024"),
        (110, "Dell 27\" 4K Monitor P2723QE",                 "Hardware",      4,   42000.00, "New",      "All Team",       "One per workstation"),
        (110, "Logitech MX Master 3 Mouse",                   "Accessories",   5,    8500.00, "New",      "All Team",       "Wireless ergonomic — all desks"),
        (110, "Keychron K2 Mechanical Keyboard",              "Accessories",   4,    7200.00, "New",      "Dev Team",       "Tenkeyless, RGB backlit"),
        (100, "Adobe Creative Cloud — Annual License",        "Software",      3,   28000.00, "Active",   "Design Team",    "Renewed Jan 2024 — expires Jan 2025"),
        (100, "JetBrains All Products Pack — Annual",         "Software",      2,   22000.00, "Active",   "Dev Team",       "IDE suite — renewed Feb 2024"),
        ( 90, "Office Desk L-Shape 160cm",                    "Furniture",     4,   18500.00, "New",      "Office",         "New office fit-out — Feb 2024"),
        ( 90, "Ergonomic Office Chair — HAG Capisco",         "Furniture",     4,   24000.00, "New",      "All Team",       "Back support — premium seating"),
        ( 75, "TP-Link Wi-Fi 6 Router AX3000",                "Network",       1,   12000.00, "New",      "Office",         "Main office router — replaces old Asus"),
        ( 75, "TP-Link 8-Port Gigabit Switch TL-SG108",      "Network",       2,    3500.00, "New",      "Office",         "Wired network expansion"),
        ( 60, "UPS Battery Backup APC 1500VA",                "Hardware",      2,   14500.00, "New",      "Office",         "Critical workstation power backup"),
        ( 45, "Logitech C920 HD Webcam",                      "Accessories",   3,    6800.00, "New",      "All Team",       "Client calls & remote meetings"),
        ( 20, "Samsung T7 Portable SSD 1TB",                  "Accessories",   4,    9500.00, "New",      "Dev & Design",   "Fast backup drives per engineer"),
    ]

    for item in items:
        days_ago, item_name, category, qty, unit_price, condition, assigned_to, notes = item
        total = round(qty * unit_price, 2)
        await db.inventory.create(
            data={
                "date":        _dt(days_ago),
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
        _ok(f"Inventory", f"'{item_name[:38]}'  qty={qty}  total=৳{total:>10,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
#  PERMISSION RULES  (Role Matrix)
# ══════════════════════════════════════════════════════════════════════════════

async def seed_permission_rules(db: Prisma) -> None:
    """
    Seed all 11 canonical modules with correct per-role visibility defaults.

    Default matrix:
      CEO & DIRECTOR  VISIBLE  for all 11 modules
      HR              VISIBLE  for operational modules (fiverr, upwork, pmak,
                               pmak_inhouse, outside_orders, dollar_exchange,
                               hr_expense, inventory)
      BDEV            VISIBLE  for pmak & pmak_inhouse only

    Schema fields:
      PermissionRule: moduleName, ceoAccess, directorAccess,
                      hrAccess, bdevAccess, displayOrder
    """
    _header("🔐 Permission Rules  (Role Matrix — 11 modules)")

    # (moduleName,          displayOrder, ceoAccess,  directorAccess, hrAccess,   bdevAccess)
    rules = [
        ("dashboard",          0,         "VISIBLE",  "VISIBLE",      "HIDDEN",   "HIDDEN"),
        ("fiverr",             1,         "VISIBLE",  "VISIBLE",      "VISIBLE",  "HIDDEN"),
        ("upwork",             2,         "VISIBLE",  "VISIBLE",      "VISIBLE",  "HIDDEN"),
        ("payoneer",           3,         "VISIBLE",  "VISIBLE",      "HIDDEN",   "HIDDEN"),
        ("pmak",               4,         "VISIBLE",  "VISIBLE",      "VISIBLE",  "VISIBLE"),
        ("pmak_inhouse",       5,         "VISIBLE",  "VISIBLE",      "VISIBLE",  "VISIBLE"),
        ("outside_orders",     6,         "VISIBLE",  "VISIBLE",      "VISIBLE",  "HIDDEN"),
        ("card_sharing",       7,         "VISIBLE",  "VISIBLE",      "HIDDEN",   "HIDDEN"),
        ("dollar_exchange",    8,         "VISIBLE",  "VISIBLE",      "VISIBLE",  "HIDDEN"),
        ("hr_expense",         9,         "VISIBLE",  "VISIBLE",      "VISIBLE",  "HIDDEN"),
        ("inventory",         10,         "VISIBLE",  "VISIBLE",      "VISIBLE",  "HIDDEN"),
    ]

    for module_name, display_order, ceo, director, hr, bdev in rules:
        await db.permissionrule.create(
            data={
                "moduleName":     module_name,
                "ceoAccess":      ceo,
                "directorAccess": director,
                "hrAccess":       hr,
                "bdevAccess":     bdev,
                "displayOrder":   display_order,
            }
        )
        _ok(
            f"PermissionRule  {module_name:<18}",
            f"CEO={ceo:<7}  DIR={director:<7}  HR={hr:<7}  BDEV={bdev}",
        )


# ══════════════════════════════════════════════════════════════════════════════
#  TERMS & CONDITIONS
# ══════════════════════════════════════════════════════════════════════════════

async def seed_terms(db: Prisma) -> None:
    """
    One initial Terms & Conditions record at version 1.

    Schema fields:
      TermsCondition: content, version
    """
    _header("📄 Terms & Conditions  (v1)")

    content = (
        "MAKTech Financial Flow — Platform Terms & Conditions\n\n"
        "1. AUTHORISED USE\n"
        "   Access to this platform is restricted to authorised MAKTech employees "
        "only. Credentials must not be shared. All actions are logged and audited.\n\n"
        "2. DATA CONFIDENTIALITY\n"
        "   All financial data, client information, and internal records viewed "
        "within this system are strictly confidential. Disclosure to third parties "
        "without written consent from the CEO is prohibited.\n\n"
        "3. ROLE-BASED ACCESS\n"
        "   Users may only access modules permitted by their assigned role. "
        "Attempting to circumvent role restrictions will result in immediate "
        "account suspension and disciplinary action.\n\n"
        "4. ACCURATE RECORD KEEPING\n"
        "   All financial entries must be accurate and entered in a timely manner. "
        "Deliberate falsification of records is a terminable offence.\n\n"
        "5. PASSWORD SECURITY\n"
        "   Users must change their temporary password upon first login and "
        "maintain a strong, unique password. Passwords must not be written down "
        "or stored in plain text.\n\n"
        "6. INCIDENT REPORTING\n"
        "   Any suspected unauthorised access, data breach, or system anomaly "
        "must be reported to the CEO immediately.\n\n"
        "By logging in, you confirm you have read, understood, and agree to "
        "comply with these terms in full.\n\n"
        "Last updated: April 2024 — Version 1.0"
    )

    await db.termscondition.create(data={"content": content, "version": 1})
    _ok("TermsCondition  v1", "initial platform T&C created")


# ══════════════════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

async def print_summary(db: Prisma) -> None:
    _header("📊 Final Record Counts")

    rows = [
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
        ("Card Sharing",           await db.cardsharing.count()),
        ("HR Expenses",            await db.hrexpense.count()),
        ("Inventory Items",        await db.inventory.count()),
        ("Permission Rules",       await db.permissionrule.count()),
        ("Terms Conditions",       await db.termscondition.count()),
        ("Invitations",            await db.invitation.count()),
    ]

    total = 0
    for label, count in rows:
        print(f"  · {label:<26} {count:>4} records")
        total += count
    print(f"  {'─' * 38}")
    print(f"  {'TOTAL':<26} {total:>4} records")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║     MAKTech Financial Flow — Database Seeder         ║")
    print("╠══════════════════════════════════════════════════════╣")
    print("║  MODE : RESET then fresh seed on every run           ║")
    print("║  PWD  : 123456  (all accounts)                       ║")
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
        await seed_card_sharing(db)
        await seed_hr_expense(db)
        await seed_inventory(db)
        await seed_permission_rules(db)
        await seed_terms(db)

        await print_summary(db)

        print()
        print("╔══════════════════════════════════════════════════════╗")
        print("║      Done! Database is fresh and ready.              ║")
        print("╠══════════════════════════════════════════════════════╣")
        print("║  CEO      →  ceo@maktech.com        /  123456        ║")
        print("║  Director →  director@maktech.com   /  123456        ║")
        print("║  HR       →  hr@maktech.com         /  123456        ║")
        print("║  BDEV     →  bdev@maktech.com       /  123456        ║")
        print("║                                                      ║")
        print("║  API Docs →  http://localhost:8000/docs              ║")
        print("╚══════════════════════════════════════════════════════╝")
        print()

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())