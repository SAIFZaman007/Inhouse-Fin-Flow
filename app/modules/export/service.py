"""
app/modules/export/service.py
==============================
Excel export service — generates multi-sheet .xlsx for daily/monthly/yearly periods.

BUG FIX:
  Line ~32 had: db.fiversnapshot   ← AttributeError at runtime (missing 'r')
  Fixed to:     db.fiverrsnapshot  ← correct Prisma model accessor
"""
from datetime import date, timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from prisma import Prisma

# ── Styles ────────────────────────────────────────────────────────────────────
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
TITLE_FONT  = Font(bold=True, size=13, color="1F3864")
ALT_FILL    = PatternFill("solid", fgColor="EEF2FF")
BORDER = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)
CENTER = Alignment(horizontal="center", vertical="center")
LEFT   = Alignment(horizontal="left",   vertical="center")


def _get_date_range(period: str, target_date: date) -> tuple[date, date]:
    if period == "daily":
        return target_date, target_date
    if period == "monthly":
        start = target_date.replace(day=1)
        end = (start.replace(month=start.month % 12 + 1, day=1) - timedelta(days=1)) \
              if start.month < 12 else start.replace(day=31)
        return start, end
    # yearly
    return target_date.replace(month=1, day=1), target_date.replace(month=12, day=31)


def _write_sheet(
    ws,
    title: str,
    headers: list[str],
    rows: list[list],
    col_widths: list[int] | None = None,
) -> None:
    """Write a fully-formatted sheet: title row → header row → data rows."""
    # Title
    ws.append([title])
    title_cell = ws.cell(row=1, column=1)
    title_cell.font      = TITLE_FONT
    title_cell.alignment = LEFT
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws.row_dimensions[1].height = 28

    # Headers
    ws.append(headers)
    for cell in ws[2]:
        cell.fill      = HEADER_FILL
        cell.font      = HEADER_FONT
        cell.alignment = CENTER
        cell.border    = BORDER
    ws.row_dimensions[2].height = 22

    # Data
    for row_idx, row in enumerate(rows, start=3):
        ws.append(row)
        fill = ALT_FILL if row_idx % 2 == 0 else None
        for cell in ws[row_idx]:
            cell.border    = BORDER
            cell.alignment = LEFT
            if fill:
                cell.fill = fill

    # Column widths
    widths = col_widths or [18] * len(headers)
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width


async def build_export(db: Prisma, period: str, target_date: date) -> bytes:
    start, end = _get_date_range(period, target_date)
    date_filter = {"gte": start, "lte": end}
    period_label = f"{period.title()}: {start} → {end}"

    wb = Workbook()
    wb.remove(wb.active)  # remove default empty sheet

    # ── 1. Fiverr Snapshots ──────────────────────────────────────────────────
    # FIX: was db.fiversnapshot (missing 'r') — caused AttributeError at runtime
    fiverr_snapshots = await db.fiverrsnapshot.find_many(
        where={"date": date_filter},
        include={"profile": True},
        order={"date": "asc"},
    )
    _write_sheet(
        wb.create_sheet("Fiverr Snapshots"),
        f"Fiverr Snapshots — {period_label}",
        ["Date", "Profile", "Available ($)", "Not Cleared ($)", "Active Orders",
         "Submitted", "Withdrawn ($)", "Seller Plus", "Promotion"],
        [
            [str(s.date), s.profile.name,
             float(s.availableWithdraw), float(s.notCleared),
             s.activeOrders, s.submitted, float(s.withdrawn),
             "Yes" if s.sellerPlus else "No",
             "Yes" if s.promotion else "No"]
            for s in fiverr_snapshots
        ],
        [12, 22, 16, 16, 14, 12, 15, 12, 12],
    )

    # ── 2. Fiverr Orders ─────────────────────────────────────────────────────
    fiverr_orders = await db.fiverrorder.find_many(
        where={"date": date_filter},
        include={"profile": True},
        order={"date": "asc"},
    )
    _write_sheet(
        wb.create_sheet("Fiverr Orders"),
        f"Fiverr Orders — {period_label}",
        ["Date", "Profile", "Client Name", "Order ID", "Amount ($)"],
        [[str(o.date), o.profile.name, o.clientName, o.orderId, float(o.amount)]
         for o in fiverr_orders],
        [12, 22, 26, 24, 14],
    )

    # ── 3. Upwork Snapshots ──────────────────────────────────────────────────
    upwork_snapshots = await db.upworksnapshot.find_many(
        where={"date": date_filter},
        include={"profile": True},
        order={"date": "asc"},
    )
    _write_sheet(
        wb.create_sheet("Upwork Snapshots"),
        f"Upwork Snapshots — {period_label}",
        ["Date", "Profile", "Available ($)", "Pending ($)", "In Review ($)",
         "WIP ($)", "Withdrawn ($)", "Connect", "Plus"],
        [
            [str(s.date), s.profile.name,
             float(s.availableWithdraw), float(s.pending),
             float(s.inReview), float(s.workInProgress), float(s.withdrawn),
             s.connect, "Yes" if s.upworkPlus else "No"]
            for s in upwork_snapshots
        ],
        [12, 22, 16, 14, 14, 14, 15, 10, 8],
    )

    # ── 4. Upwork Orders ─────────────────────────────────────────────────────
    upwork_orders = await db.upworkorder.find_many(
        where={"date": date_filter},
        include={"profile": True},
        order={"date": "asc"},
    )
    _write_sheet(
        wb.create_sheet("Upwork Orders"),
        f"Upwork Orders — {period_label}",
        ["Date", "Profile", "Client Name", "Order ID", "Amount ($)"],
        [[str(o.date), o.profile.name, o.clientName, o.orderId, float(o.amount)]
         for o in upwork_orders],
        [12, 22, 26, 24, 14],
    )

    # ── 5. Payoneer Transactions ─────────────────────────────────────────────
    payoneer_txs = await db.payoneertransaction.find_many(
        where={"date": date_filter},
        include={"account": True},
        order={"date": "asc"},
    )
    _write_sheet(
        wb.create_sheet("Payoneer"),
        f"Payoneer Transactions — {period_label}",
        ["Date", "Account", "Details", "From", "To", "Debit ($)", "Credit ($)", "Balance ($)"],
        [
            [str(t.date), t.account.name, t.details,
             t.fromParty or "", t.toParty or "",
             float(t.debit), float(t.credit), float(t.remainingBalance)]
            for t in payoneer_txs
        ],
        [12, 22, 30, 18, 18, 12, 12, 14],
    )

    # ── 6. PMAK Transactions ─────────────────────────────────────────────────
    pmak_txs = await db.pmaktransaction.find_many(
        where={"date": date_filter},
        include={"account": True},
        order={"date": "asc"},
    )
    _write_sheet(
        wb.create_sheet("PMAK"),
        f"PMAK Transactions — {period_label}",
        ["Date", "Account", "Details", "From", "To", "Debit ($)", "Credit ($)", "Balance ($)"],
        [
            [str(t.date), t.account.name, t.details,
             t.fromParty or "", t.toParty or "",
             float(t.debit), float(t.credit), float(t.remainingBalance)]
            for t in pmak_txs
        ],
        [12, 22, 30, 18, 18, 12, 12, 14],
    )

    # ── 7. Outside Orders ────────────────────────────────────────────────────
    outside_orders = await db.outsideorder.find_many(
        where={"date": date_filter},
        order={"date": "asc"},
    )
    _write_sheet(
        wb.create_sheet("Outside Orders"),
        f"Outside Orders — {period_label}",
        ["Date", "Client ID", "Client Name", "Status",
         "Order Amount ($)", "Received ($)", "Due ($)", "Payment Method"],
        [
            [str(o.date), o.clientId, o.clientName, o.status,
             float(o.orderAmount), float(o.receiveAmount), float(o.dueAmount),
             o.paymentMethod or ""]
            for o in outside_orders
        ],
        [12, 16, 24, 14, 16, 14, 12, 20],
    )

    # ── 8. Dollar Exchange ───────────────────────────────────────────────────
    exchanges = await db.dollarexchange.find_many(
        where={"date": date_filter},
        order={"date": "asc"},
    )
    _write_sheet(
        wb.create_sheet("Dollar Exchange"),
        f"Dollar Exchange — {period_label}",
        ["Date", "Details", "From", "To",
         "Debit ($)", "Credit ($)", "Rate (BDT)", "Total BDT", "Status"],
        [
            [str(e.date), e.details, e.fromParty or "", e.toParty or "",
             float(e.debit), float(e.credit), float(e.rate),
             float(e.totalBdt), e.paymentStatus]
            for e in exchanges
        ],
        [12, 28, 18, 18, 12, 12, 12, 16, 12],
    )

    # ── 9. HR Expense ────────────────────────────────────────────────────────
    hr_expenses = await db.hrexpense.find_many(
        where={"date": date_filter},
        order={"date": "asc"},
    )
    _write_sheet(
        wb.create_sheet("HR Expense"),
        f"HR Expense — {period_label}",
        ["Date", "Details", "From", "To", "Debit ($)", "Credit ($)", "Balance ($)"],
        [
            [str(e.date), e.details, e.fromParty or "", e.toParty or "",
             float(e.debit), float(e.credit), float(e.remainingBalance)]
            for e in hr_expenses
        ],
        [12, 30, 18, 18, 12, 12, 14],
    )

    # ── 10. Inventory ────────────────────────────────────────────────────────
    inventory_items = await db.inventory.find_many(
        where={"date": date_filter},
        order={"date": "asc"},
    )
    _write_sheet(
        wb.create_sheet("Inventory"),
        f"Inventory — {period_label}",
        ["Date", "Item Name", "Category", "Quantity",
         "Unit Price ($)", "Total Price ($)", "Vendor", "Notes"],
        [
            [str(i.date), i.itemName, i.category or "", i.quantity,
             float(i.unitPrice), float(i.totalPrice),
             i.vendor or "", i.notes or ""]
            for i in inventory_items
        ],
        [12, 26, 16, 10, 14, 16, 20, 26],
    )

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output.read()