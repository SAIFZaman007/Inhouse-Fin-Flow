"""
app/modules/export/service.py
==============================
Enterprise-grade Excel export engine — MAKTech Financial Flow.

═══════════════════════════════════════════════════════════════════════════════
ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════════

  resolve_date_range()       → ExportQueryParams → (date_from, date_to, label)
  _prisma_date_filter()      → date range → Prisma-safe datetime dict
  _xl()                      → openpyxl Workbook factory — full enterprise styling
  _build_kpi_summary()       → writes KPI Summary tab for dashboard export
  _copy_sheet_into()         → merges a single-sheet wb into a multi-sheet wb
  export_<module>()          → fetch DB → build workbook → (bytes, filename)

═══════════════════════════════════════════════════════════════════════════════
SCHEMA FIELD COVERAGE (v2 — complete audit against schema.prisma)
═══════════════════════════════════════════════════════════════════════════════

  FiverrEntry        ✅ date, profile, availableWithdraw, notCleared,
                        activeOrders, submitted, withdrawn, sellerPlus, promotion
  FiverrOrder        ✅ NEW SHEET — date, profile, buyerName, orderId, amount
  UpworkEntry        ✅ date, profile, availableWithdraw, pending, inReview,
                        workInProgress, withdrawn, connects, upworkPlus
  UpworkOrder        ✅ NEW SHEET — date, profile, clientName, orderId, amount
  PayoneerTransaction✅ date, account, details, accountFrom, accountTo,
                        debit, credit, remainingBalance
  PmakTransaction    ✅ date, account, details, accountFrom, accountTo,
                        debit, credit, remainingBalance, status, notes,
                        buyer, seller  ← FIXED (buyer/seller were missing)
  OutsideOrder       ✅ date, clientId, clientName, clientLink, orderDetails,
                        assignTeam, orderStatus, orderAmount, receiveAmount,
                        dueAmount, paymentMethod, paymentMethodDetails
  DollarExchange     ✅ date, details, accountFrom, accountTo, debit, credit,
                        rate, totalBdt, totalBdtLive, paymentStatus
  CardSharing        ✅ serialNo, details, payoneerAccount, cardExpire,
                        cardVendor, cardLimit, cardPaymentRcv, cardRcvBank,
                        mailDetails  [cardNo + cardCvc intentionally excluded]
  HrExpense          ✅ date, details, accountFrom, accountTo, debit, credit,
                        remainingBalance
  Inventory          ✅ date, itemName, category, quantity, unitPrice,
                        totalPrice, condition, assignedTo, notes

═══════════════════════════════════════════════════════════════════════════════
DASHBOARD EXPORT SHEETS (11 total)
═══════════════════════════════════════════════════════════════════════════════

   1. KPI Summary           — top-line numbers at a glance
   2. Fiverr Entries        — daily snapshots (full fields)
   3. Fiverr Orders         — order log (NEW)
   4. Upwork Entries        — daily snapshots (full fields)
   5. Upwork Orders         — order log (NEW)
   6. Payoneer              — ledger (full fields incl. accountFrom/To)
   7. PMAK                  — ledger (full fields incl. buyer/seller/notes)
   8. Outside Orders        — full order detail
   9. Dollar Exchange       — with live-rate BDT column
  10. HR Expense            — full ledger
  11. Inventory             — full item list incl. notes

═══════════════════════════════════════════════════════════════════════════════
KPI FETCH STRATEGY (v2.1 — correct balance semantics)
═══════════════════════════════════════════════════════════════════════════════

  Ledger modules (Payoneer, PMAK, HR Expense) show CURRENT balances —
  i.e., the latest running balance across ALL-TIME transactions, not just
  the selected period.  The period filter still controls which transactions
  appear in the detail sheets; KPI balances are always authoritative.

  Inventory KPI shows BOTH:
    • "Period additions" — items procured in the selected period
    • "Total asset value" — all-time inventory value (in the note field)

═══════════════════════════════════════════════════════════════════════════════

  FIX 1 — prisma-client-py date serialisation crash:
    ✘ where={"date": {"gte": d_from}}          → TypeError (date not JSON-serialisable)
    ✔ where={"date": {"gte": datetime.combine(d_from, time.min)}}

  FIX 2 — PaymentStatus enum value:
    Schema: enum PaymentStatus { RECEIVED  DUE }
    Filter: where={"paymentStatus": "RECEIVED"}  ✔  (not "RCV")

═══════════════════════════════════════════════════════════════════════════════
STYLING SYSTEM (enterprise-grade)
═══════════════════════════════════════════════════════════════════════════════

  Brand palette:
    Navy header   #1A3C6E  White text, Bold 11pt
    Teal accent   #0E7490  KPI values, Bold 13pt
    Alt row       #EFF6FF  Light blue stripe
    Status green  #DCFCE7  COMPLETED / CLEARED / RECEIVED / ACTIVE
    Status amber  #FEF3C7  IN_PROGRESS / PENDING / ON_HOLD
    Status red    #FEE2E2  DUE / OVERDUE / CANCELLED
    Totals row    #1A3C6E  White bold — mirrors header

  Features: freeze panes, auto column width, number formats (#,##0.00),
            status-conditional fills, SUM formula totals row, tab colours,
            metadata block, grid-lines hidden.
"""

from __future__ import annotations

import io
import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from prisma import Prisma

from app.shared.constants import ExportPeriod
from .schema import ExportQueryParams


# ═══════════════════════════════════════════════════════════════════════════════
#  COLOUR PALETTE — single source of truth
# ═══════════════════════════════════════════════════════════════════════════════

class _C:
    """Hex colour constants (no leading #)."""
    NAVY        = "1A3C6E"   # header / totals bg
    TEAL        = "0E7490"   # KPI accent
    TEAL_LIGHT  = "CFFAFE"   # KPI card bg
    ALT_ROW     = "EFF6FF"   # alternating row
    WHITE       = "FFFFFF"
    BLACK       = "0F172A"
    GREY_BORDER = "CBD5E1"
    META_BG     = "F1F5F9"   # metadata block bg

    # Status fills
    GREEN_BG    = "DCFCE7";  GREEN_TEXT  = "166534"
    AMBER_BG    = "FEF3C7";  AMBER_TEXT  = "92400E"
    RED_BG      = "FEE2E2";  RED_TEXT    = "991B1B"
    BLUE_BG     = "DBEAFE";  BLUE_TEXT   = "1E40AF"

    # Sheet tab colours (one per sheet in dashboard order)
    TABS = [
        "1A3C6E",  # KPI Summary      — navy
        "0E7490",  # Fiverr Entries   — teal
        "065F46",  # Fiverr Orders    — emerald
        "1D4ED8",  # Upwork Entries   — blue
        "2563EB",  # Upwork Orders    — lighter blue
        "7C3AED",  # Payoneer         — violet
        "B45309",  # PMAK             — amber
        "DC2626",  # Outside Orders   — red
        "0369A1",  # Dollar Exchange  — sky
        "047857",  # HR Expense       — green
        "6D28D9",  # Inventory        — purple
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#  STYLE OBJECTS
# ═══════════════════════════════════════════════════════════════════════════════

def _fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)


def _thin_border() -> Border:
    s = Side(style="thin", color=_C.GREY_BORDER)
    return Border(left=s, right=s, top=s, bottom=s)


_HEADER_FILL    = _fill(_C.NAVY)
_TOTALS_FILL    = _fill(_C.NAVY)
_ALT_FILL       = _fill(_C.ALT_ROW)
_META_FILL      = _fill(_C.META_BG)
_KPI_CARD_FILL  = _fill(_C.TEAL_LIGHT)

_HEADER_FONT    = Font(name="Calibri", bold=True, color=_C.WHITE,  size=11)
_TOTALS_FONT    = Font(name="Calibri", bold=True, color=_C.WHITE,  size=10)
_BODY_FONT      = Font(name="Calibri",             color=_C.BLACK,  size=10)
_BOLD_FONT      = Font(name="Calibri", bold=True,  color=_C.BLACK,  size=10)
_META_KEY_FONT  = Font(name="Calibri", bold=True,  color=_C.NAVY,   size=9)
_META_VAL_FONT  = Font(name="Calibri",             color=_C.BLACK,  size=9)
_KPI_LBL_FONT   = Font(name="Calibri", bold=True,  color=_C.NAVY,   size=10)
_KPI_VAL_FONT   = Font(name="Calibri", bold=True,  color=_C.TEAL,   size=13)

_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=False)
_LEFT   = Alignment(horizontal="left",   vertical="center", wrap_text=False)
_RIGHT  = Alignment(horizontal="right",  vertical="center", wrap_text=False)
_WRAP   = Alignment(horizontal="left",   vertical="top",    wrap_text=True)

# Status conditional fill map  →  (bg_hex, text_hex)
_STATUS_STYLES: dict[str, tuple[str, str]] = {
    "COMPLETED":   (_C.GREEN_BG,  _C.GREEN_TEXT),
    "CLEARED":     (_C.GREEN_BG,  _C.GREEN_TEXT),
    "RECEIVED":    (_C.GREEN_BG,  _C.GREEN_TEXT),
    "ACTIVE":      (_C.GREEN_BG,  _C.GREEN_TEXT),
    "IN_PROGRESS": (_C.AMBER_BG,  _C.AMBER_TEXT),
    "PENDING":     (_C.AMBER_BG,  _C.AMBER_TEXT),
    "ON_HOLD":     (_C.AMBER_BG,  _C.AMBER_TEXT),
    "DUE":         (_C.RED_BG,    _C.RED_TEXT),
    "OVERDUE":     (_C.RED_BG,    _C.RED_TEXT),
    "CANCELLED":   (_C.RED_BG,    _C.RED_TEXT),
    "REJECTED":    (_C.RED_BG,    _C.RED_TEXT),
}

# Keys that should receive status-badge styling
_STATUS_COLUMNS = {"orderStatus", "paymentStatus", "status"}

# Keys that should use currency / number formatting
_CURRENCY_COLUMNS = {
    "availableWithdraw", "notCleared", "submitted", "withdrawn",
    "promotion", "pending", "inReview", "workInProgress", "amount",
    "debit", "credit", "remainingBalance", "totalBdt", "totalBdtLive",
    "orderAmount", "receiveAmount", "dueAmount",
    "cardLimit", "cardPaymentRcv",
    "unitPrice", "totalPrice", "rate",
}

_NUMBER_FMT  = "#,##0.00"
_INTEGER_FMT = "#,##0"
_DATE_FMT    = "yyyy-mm-dd"

# Long-text columns that benefit from wrap + constrained width
_WRAP_COLUMNS = {
    "orderDetails", "paymentMethodDetails", "mailDetails",
    "notes", "details", "clientLink",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  DATE RANGE RESOLVER
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_date_range(params: ExportQueryParams) -> tuple[date, date, str]:
    """Return (date_from, date_to, human_label) from export query params."""
    today = date.today()

    if params.date_from and params.date_to:
        label = f"{params.date_from} to {params.date_to}"
        return params.date_from, params.date_to, label

    period = params.period

    if period == ExportPeriod.DAILY:
        ref = params.export_date or today
        return ref, ref, ref.strftime("%d %B %Y")

    if period == ExportPeriod.WEEKLY:
        ref    = params.export_date or today
        monday = ref - timedelta(days=ref.weekday())
        sunday = monday + timedelta(days=6)
        label  = f"Week {monday.strftime('%d %b')} – {sunday.strftime('%d %b %Y')}"
        return monday, sunday, label

    if period == ExportPeriod.MONTHLY:
        y      = params.year  or today.year
        m      = params.month or today.month
        d_from = date(y, m, 1)
        d_to   = date(y, m, calendar.monthrange(y, m)[1])
        return d_from, d_to, date(y, m, 1).strftime("%B %Y")

    if period == ExportPeriod.YEARLY:
        y = params.year or today.year
        return date(y, 1, 1), date(y, 12, 31), str(y)

    raise ValueError(f"Unknown period: {period}")


def _prisma_date_filter(d_from: date, d_to: date) -> dict:
    """
    Convert date → datetime for Prisma where-clauses.

    prisma-client-py serialises where-clause values via json.dumps().
    Its custom encoder handles datetime (ISO-8601) but NOT date objects —
    passing a bare date raises: TypeError: Type date not serializable.
    """
    return {
        "gte": datetime.combine(d_from, time.min),
        "lte": datetime.combine(d_to,   time.max),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  CORE WORKBOOK BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def _xl(
    sheet_title: str,
    columns: list[tuple[str, str]],
    rows: list[dict[str, Any]],
    meta: dict[str, str] | None = None,
    tab_color: str | None = None,
    totals: bool = True,
) -> bytes:
    """
    Build a styled enterprise-grade .xlsx workbook and return raw bytes.

    Args:
        sheet_title : Excel sheet name (max 31 chars).
        columns     : [(header_label, dict_key), …]
        rows        : List of dicts keyed by the column dict_keys.
        meta        : Optional metadata block above the table (label → value).
        tab_color   : Hex colour for the sheet tab (no leading #).
        totals      : Whether to append a SUM totals row for numeric columns.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]
    if tab_color:
        ws.sheet_properties.tabColor = tab_color
    ws.sheet_view.showGridLines = False

    border  = _thin_border()
    row_ptr = 1

    # ── Metadata block ────────────────────────────────────────────────────────
    if meta:
        for key, val in meta.items():
            k_cell = ws.cell(row=row_ptr, column=1, value=key)
            v_cell = ws.cell(row=row_ptr, column=2, value=val)
            for cell, fnt in ((k_cell, _META_KEY_FONT), (v_cell, _META_VAL_FONT)):
                cell.font      = fnt
                cell.fill      = _META_FILL
                cell.alignment = _LEFT
            row_ptr += 1
        row_ptr += 1   # blank separator row

    # ── Column header row ─────────────────────────────────────────────────────
    header_row = row_ptr
    for col_i, (header, _) in enumerate(columns, start=1):
        cell = ws.cell(row=row_ptr, column=col_i, value=header)
        cell.fill      = _HEADER_FILL
        cell.font      = _HEADER_FONT
        cell.alignment = _CENTER
        cell.border    = border
    ws.row_dimensions[row_ptr].height = 24
    ws.freeze_panes = ws.cell(row=row_ptr + 1, column=1)
    row_ptr += 1

    # ── Data rows ─────────────────────────────────────────────────────────────
    data_start = row_ptr
    for row_i, row_data in enumerate(rows):
        alt = (row_i % 2 == 1)
        for col_i, (_, key) in enumerate(columns, start=1):
            raw = row_data.get(key)

            # Normalise value
            if isinstance(raw, Decimal):
                value = float(raw)
            elif isinstance(raw, datetime):
                value = raw.strftime("%Y-%m-%d")
            elif isinstance(raw, date):
                value = raw.strftime("%Y-%m-%d")
            elif raw is None:
                value = ""
            else:
                value = raw

            cell = ws.cell(row=row_ptr, column=col_i, value=value)
            cell.font      = _BODY_FONT
            cell.alignment = _LEFT
            cell.border    = border

            # Alternating row fill (may be overridden by status below)
            if alt:
                cell.fill = _ALT_FILL

            # Status-badge conditional fill
            if key in _STATUS_COLUMNS and isinstance(value, str):
                style_key = value.upper()
                if style_key in _STATUS_STYLES:
                    bg, fg = _STATUS_STYLES[style_key]
                    cell.fill      = _fill(bg)
                    cell.font      = Font(name="Calibri", bold=True, color=fg, size=10)
                    cell.alignment = _CENTER

            # Currency / number formats
            if key in _CURRENCY_COLUMNS and isinstance(value, float):
                cell.number_format = _NUMBER_FMT
                cell.alignment     = _RIGHT

            elif key in {"activeOrders", "connects", "quantity"}:
                cell.number_format = _INTEGER_FMT
                cell.alignment     = _RIGHT

            # Long-text wrap
            elif key in _WRAP_COLUMNS:
                cell.alignment = _WRAP

        row_ptr += 1
    data_end = row_ptr - 1

    # ── Totals row ────────────────────────────────────────────────────────────
    if totals and rows:
        # Identify columns that have actual numeric data in row[0]
        numeric_cols = [
            col_i
            for col_i, (_, key) in enumerate(columns, start=1)
            if key in _CURRENCY_COLUMNS
            and isinstance(rows[0].get(key), (Decimal, int, float))
            and not isinstance(rows[0].get(key), bool)
        ]
        if numeric_cols:
            tot_label = ws.cell(row=row_ptr, column=1, value="TOTAL")
            tot_label.font      = _TOTALS_FONT
            tot_label.fill      = _TOTALS_FILL
            tot_label.alignment = _LEFT
            tot_label.border    = border
            # Fill every cell in the totals row
            for col_i in range(2, len(columns) + 1):
                cell        = ws.cell(row=row_ptr, column=col_i)
                cell.fill   = _TOTALS_FILL
                cell.border = border
            # Write SUM formulae for numeric columns
            for col_i in numeric_cols:
                letter = get_column_letter(col_i)
                fcell  = ws.cell(
                    row=row_ptr, column=col_i,
                    value=f"=SUM({letter}{data_start}:{letter}{data_end})",
                )
                fcell.font          = _TOTALS_FONT
                fcell.fill          = _TOTALS_FILL
                fcell.alignment     = _RIGHT
                fcell.number_format = _NUMBER_FMT
                fcell.border        = border
            ws.row_dimensions[row_ptr].height = 20
            row_ptr += 1

    # ── Auto column width ─────────────────────────────────────────────────────
    for col_i, (header, key) in enumerate(columns, start=1):
        letter  = get_column_letter(col_i)
        max_len = len(str(header))
        for row_data in rows:
            v = row_data.get(key)
            if v is not None:
                max_len = max(max_len, len(str(v)))
        # Constrain wrap-columns to a readable width
        if key in _WRAP_COLUMNS:
            ws.column_dimensions[letter].width = min(max_len + 4, 40)
        else:
            ws.column_dimensions[letter].width = min(max_len + 4, 52)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def _copy_sheet_into(
    source_bytes: bytes,
    target_wb: openpyxl.Workbook,
    sheet_name: str,
    tab_color: str | None = None,
) -> None:
    """
    Copy the active sheet of a single-sheet workbook into target_wb
    as a new named sheet, preserving all cell styles and dimensions.
    """
    src_wb = openpyxl.load_workbook(io.BytesIO(source_bytes))
    src_ws = src_wb.active
    new_ws = target_wb.create_sheet(title=sheet_name[:31])
    if tab_color:
        new_ws.sheet_properties.tabColor = tab_color
    new_ws.sheet_view.showGridLines = False

    for row in src_ws.iter_rows():
        for cell in row:
            nc = new_ws.cell(row=cell.row, column=cell.column, value=cell.value)
            if cell.has_style:
                nc.font          = cell.font.copy()
                nc.fill          = cell.fill.copy()
                nc.alignment     = cell.alignment.copy()
                nc.border        = cell.border.copy()
                nc.number_format = cell.number_format

    for letter, dim in src_ws.column_dimensions.items():
        new_ws.column_dimensions[letter].width = dim.width
    for idx, dim in src_ws.row_dimensions.items():
        new_ws.row_dimensions[idx].height = dim.height
    if src_ws.freeze_panes:
        new_ws.freeze_panes = src_ws.freeze_panes


# ═══════════════════════════════════════════════════════════════════════════════
#  KPI SUMMARY SHEET
# ═══════════════════════════════════════════════════════════════════════════════

def _build_kpi_summary(
    wb: openpyxl.Workbook,
    label: str,
    kpis: list[dict],
    tab_color: str = _C.NAVY,
) -> None:
    """
    Write the KPI Summary sheet as the first tab in the workbook.

    Each KPI is rendered as a card row:
        # | KPI Label | Value | Formula / Note | Status
    """
    ws = wb.create_sheet(title="KPI Summary", index=0)
    ws.sheet_properties.tabColor = tab_color
    ws.sheet_view.showGridLines  = False
    border = _thin_border()

    # Title banner
    ws.merge_cells("A1:E1")
    banner = ws["A1"]
    banner.value     = "MAKTech Financial Flow — Dashboard KPI Summary"
    banner.font      = Font(name="Calibri", bold=True, color=_C.WHITE, size=14)
    banner.fill      = _HEADER_FILL
    banner.alignment = _CENTER
    ws.row_dimensions[1].height = 32

    # Sub-title: period + generated timestamp
    ws.merge_cells("A2:E2")
    sub = ws["A2"]
    sub.value     = f"Period: {label}   ·   Generated: {datetime.now().strftime('%d %b %Y  %H:%M')}"
    sub.font      = Font(name="Calibri", italic=True, color=_C.WHITE, size=10)
    sub.fill      = _fill(_C.TEAL)
    sub.alignment = _CENTER
    ws.row_dimensions[2].height = 20

    # Column headers
    for col_i, h in enumerate(["#", "KPI", "Value (BDT / USD)", "Formula / Note", "Status"], start=1):
        cell = ws.cell(row=3, column=col_i, value=h)
        cell.font      = _HEADER_FONT
        cell.fill      = _fill(_C.TEAL)
        cell.alignment = _CENTER
        cell.border    = border
    ws.row_dimensions[3].height = 20

    # KPI card rows
    for i, kpi in enumerate(kpis, start=1):
        row = 3 + i
        bg  = _fill(_C.ALT_ROW) if (i % 2 == 0) else _fill(_C.WHITE)

        c0 = ws.cell(row=row, column=1, value=i)
        c0.font = Font(name="Calibri", bold=True, color=_C.NAVY, size=10)
        c0.fill = bg; c0.alignment = _CENTER; c0.border = border

        c1 = ws.cell(row=row, column=2, value=kpi["label"])
        c1.font = _KPI_LBL_FONT; c1.fill = bg
        c1.alignment = _LEFT; c1.border = border

        c2 = ws.cell(row=row, column=3, value=kpi["value"])
        c2.font = _KPI_VAL_FONT; c2.fill = _KPI_CARD_FILL
        c2.alignment = _RIGHT; c2.border = border
        c2.number_format = "#,##0.00"

        c3 = ws.cell(row=row, column=4, value=kpi.get("note", ""))
        c3.font = _META_VAL_FONT; c3.fill = bg
        c3.alignment = _LEFT; c3.border = border

        status_val = kpi.get("status", "")
        c4 = ws.cell(row=row, column=5, value=status_val)
        if status_val.upper() in _STATUS_STYLES:
            sbg, sfg = _STATUS_STYLES[status_val.upper()]
            c4.fill = _fill(sbg)
            c4.font = Font(name="Calibri", bold=True, color=sfg, size=10)
        else:
            c4.font = _BODY_FONT; c4.fill = bg
        c4.alignment = _CENTER; c4.border = border

        ws.row_dimensions[row].height = 22

    # Column widths
    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 36
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 56
    ws.column_dimensions["E"].width = 16


# ═══════════════════════════════════════════════════════════════════════════════
#  SHARED ROW BUILDERS — avoid duplicating transformation logic
# ═══════════════════════════════════════════════════════════════════════════════

def _f(v: Any) -> float:
    """Safe Decimal / None → float."""
    return float(v) if v is not None else 0.0


def _fiverr_entry_rows(entries) -> list[dict]:
    return [
        {
            "date":              e.date,
            "profile":           e.profile.profileName if e.profile else "",
            "availableWithdraw": e.availableWithdraw,
            "notCleared":        e.notCleared,
            "activeOrders":      e.activeOrders,
            "submitted":         e.submitted,
            "withdrawn":         e.withdrawn,
            "sellerPlus":        "Yes" if e.sellerPlus else "No",
            "promotion":         e.promotion,
        }
        for e in entries
    ]


_FIVERR_ENTRY_COLS = [
    ("Date",               "date"),
    ("Profile",            "profile"),
    ("Available Withdraw", "availableWithdraw"),
    ("Not Cleared",        "notCleared"),
    ("Active Orders",      "activeOrders"),
    ("Submitted",          "submitted"),
    ("Withdrawn",          "withdrawn"),
    ("Seller Plus",        "sellerPlus"),
    ("Promotion",          "promotion"),
]


def _fiverr_order_rows(orders) -> list[dict]:
    return [
        {
            "date":      o.date,
            "profile":   o.profile.profileName if o.profile else "",
            "buyerName": o.buyerName,
            "orderId":   o.orderId,
            "amount":    o.amount,
        }
        for o in orders
    ]


_FIVERR_ORDER_COLS = [
    ("Date",     "date"),
    ("Profile",  "profile"),
    ("Buyer",    "buyerName"),
    ("Order ID", "orderId"),
    ("Amount ($)", "amount"),
]


def _upwork_entry_rows(entries) -> list[dict]:
    return [
        {
            "date":              e.date,
            "profile":           e.profile.profileName if e.profile else "",
            "availableWithdraw": e.availableWithdraw,
            "pending":           e.pending,
            "inReview":          e.inReview,
            "workInProgress":    e.workInProgress,
            "withdrawn":         e.withdrawn,
            "connects":          e.connects,
            "upworkPlus":        "Yes" if e.upworkPlus else "No",
        }
        for e in entries
    ]


_UPWORK_ENTRY_COLS = [
    ("Date",               "date"),
    ("Profile",            "profile"),
    ("Available Withdraw", "availableWithdraw"),
    ("Pending",            "pending"),
    ("In Review",          "inReview"),
    ("Work In Progress",   "workInProgress"),
    ("Withdrawn",          "withdrawn"),
    ("Connects",           "connects"),
    ("Upwork Plus",        "upworkPlus"),
]


def _upwork_order_rows(orders) -> list[dict]:
    return [
        {
            "date":       o.date,
            "profile":    o.profile.profileName if o.profile else "",
            "clientName": o.clientName,
            "orderId":    o.orderId,
            "amount":     o.amount,
        }
        for o in orders
    ]


_UPWORK_ORDER_COLS = [
    ("Date",       "date"),
    ("Profile",    "profile"),
    ("Client",     "clientName"),
    ("Order ID",   "orderId"),
    ("Amount ($)", "amount"),
]


def _payoneer_rows(txns) -> list[dict]:
    return [
        {
            "date":             t.date,
            "account":          t.account.accountName if t.account else "",
            "details":          t.details,
            "accountFrom":      t.accountFrom  or "",
            "accountTo":        t.accountTo    or "",
            "debit":            t.debit,
            "credit":           t.credit,
            "remainingBalance": t.remainingBalance,
        }
        for t in txns
    ]


_PAYONEER_COLS = [
    ("Date",              "date"),
    ("Account",           "account"),
    ("Details",           "details"),
    ("Account From",      "accountFrom"),
    ("Account To",        "accountTo"),
    ("Debit ($)",         "debit"),
    ("Credit ($)",        "credit"),
    ("Remaining Balance", "remainingBalance"),
]


def _pmak_rows(txns) -> list[dict]:
    """
    Full PmakTransaction row including buyer, seller, notes.
    (buyer and seller were missing in the previous version.)
    """
    return [
        {
            "date":             t.date,
            "account":          t.account.accountName if t.account else "",
            "details":          t.details,
            "accountFrom":      t.accountFrom  or "",
            "accountTo":        t.accountTo    or "",
            "debit":            t.debit,
            "credit":           t.credit,
            "remainingBalance": t.remainingBalance,
            "status":           t.status or "",
            "buyer":            t.buyer  or "",
            "seller":           t.seller or "",
            "notes":            t.notes  or "",
        }
        for t in txns
    ]


_PMAK_COLS = [
    ("Date",              "date"),
    ("Account",           "account"),
    ("Details",           "details"),
    ("Account From",      "accountFrom"),
    ("Account To",        "accountTo"),
    ("Debit (৳)",         "debit"),
    ("Credit (৳)",        "credit"),
    ("Remaining Balance", "remainingBalance"),
    ("Status",            "status"),
    ("Buyer",             "buyer"),
    ("Seller",            "seller"),
    ("Notes",             "notes"),
]


def _outside_order_rows(orders) -> list[dict]:
    return [
        {
            "date":                 o.date,
            "clientId":             o.clientId,
            "clientName":           o.clientName,
            "clientLink":           o.clientLink           or "",
            "orderDetails":         o.orderDetails,
            "assignTeam":           o.assignTeam           or "",
            "orderStatus":          o.orderStatus,
            "orderAmount":          o.orderAmount,
            "receiveAmount":        o.receiveAmount,
            "dueAmount":            o.dueAmount,
            "paymentMethod":        o.paymentMethod        or "",
            "paymentMethodDetails": o.paymentMethodDetails or "",
        }
        for o in orders
    ]


_OUTSIDE_ORDER_COLS = [
    ("Date",             "date"),
    ("Client ID",        "clientId"),
    ("Client Name",      "clientName"),
    ("Client Link",      "clientLink"),
    ("Order Details",    "orderDetails"),
    ("Assigned Team",    "assignTeam"),
    ("Status",           "orderStatus"),
    ("Order Amt (৳)",    "orderAmount"),
    ("Received (৳)",     "receiveAmount"),
    ("Due (৳)",          "dueAmount"),
    ("Payment Method",   "paymentMethod"),
    ("Payment Details",  "paymentMethodDetails"),
]


def _dollar_exchange_rows(records, current_rate: float | None) -> list[dict]:
    rows = []
    for r in records:
        dollar_amt = _f(r.credit) if _f(r.credit) > 0 else _f(r.debit)
        live_bdt   = round(dollar_amt * current_rate, 2) if current_rate else None
        rows.append({
            "date":          r.date,
            "details":       r.details,
            "accountFrom":   r.accountFrom or "",
            "accountTo":     r.accountTo   or "",
            "debit":         r.debit,
            "credit":        r.credit,
            "rate":          r.rate,
            "totalBdt":      r.totalBdt,
            "totalBdtLive":  live_bdt,
            "paymentStatus": r.paymentStatus,
        })
    return rows


def _dollar_exchange_cols(rate_label: str) -> list[tuple[str, str]]:
    return [
        ("Date",                      "date"),
        ("Details",                   "details"),
        ("Account From",              "accountFrom"),
        ("Account To",                "accountTo"),
        ("Debit ($)",                 "debit"),
        ("Credit ($)",                "credit"),
        ("Rate at Entry (৳/$)",       "rate"),
        ("Total BDT (entry rate)",    "totalBdt"),
        (f"Total BDT (@ {rate_label} live)", "totalBdtLive"),
        ("Payment Status",            "paymentStatus"),
    ]


def _hr_expense_rows(expenses) -> list[dict]:
    return [
        {
            "date":             e.date,
            "details":          e.details,
            "accountFrom":      e.accountFrom or "",
            "accountTo":        e.accountTo   or "",
            "debit":            e.debit,
            "credit":           e.credit,
            "remainingBalance": e.remainingBalance,
        }
        for e in expenses
    ]


_HR_EXPENSE_COLS = [
    ("Date",              "date"),
    ("Details",           "details"),
    ("Account From",      "accountFrom"),
    ("Account To",        "accountTo"),
    ("Debit (৳)",         "debit"),
    ("Credit (৳)",        "credit"),
    ("Remaining Balance", "remainingBalance"),
]


def _inventory_rows(items) -> list[dict]:
    return [
        {
            "date":       i.date,
            "itemName":   i.itemName,
            "category":   i.category   or "",
            "quantity":   i.quantity,
            "unitPrice":  i.unitPrice,
            "totalPrice": i.totalPrice,
            "condition":  i.condition  or "",
            "assignedTo": i.assignedTo or "",
            "notes":      i.notes      or "",
        }
        for i in items
    ]


_INVENTORY_COLS = [
    ("Date",            "date"),
    ("Item Name",       "itemName"),
    ("Category",        "category"),
    ("Quantity",        "quantity"),
    ("Unit Price (৳)",  "unitPrice"),
    ("Total Price (৳)", "totalPrice"),
    ("Condition",       "condition"),
    ("Assigned To",     "assignedTo"),
    ("Notes",           "notes"),
]


async def _fetch_daily_rate(db: Prisma) -> tuple[float | None, str, str]:
    """
    Fetch the latest HR-set daily rate.
    Returns (rate_float, rate_date_label, rate_display_label).
    """
    try:
        rec = await db.dailyrate.find_first(order={"date": "desc"})
        if rec:
            rate  = float(rec.rate)
            d_lbl = rec.date.strftime("%d %b %Y") if hasattr(rec.date, "strftime") else str(rec.date)
            return rate, d_lbl, f"৳{rate:,.2f}/$"
    except Exception:
        pass
    return None, "N/A", "N/A"


# ═══════════════════════════════════════════════════════════════════════════════
#  PER-MODULE EXPORT FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def export_fiverr(db: Prisma, params: ExportQueryParams) -> tuple[bytes, str]:
    """
    Two-sheet workbook: Fiverr Entries + Fiverr Orders.
    Both are full schema-coverage with all fields.
    """
    d_from, d_to, label = resolve_date_range(params)
    df = _prisma_date_filter(d_from, d_to)

    entries = await db.fiverrentry.find_many(
        where={"date": df}, include={"profile": True}, order={"date": "asc"},
    )
    orders = await db.fiverrorder.find_many(
        where={"date": df}, include={"profile": True}, order={"date": "asc"},
    )

    meta_e = {"Module": "Fiverr Entries",  "Period": label, "Records": str(len(entries))}
    meta_o = {"Module": "Fiverr Orders",   "Period": label, "Records": str(len(orders))}

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _copy_sheet_into(
        _xl("Fiverr Entries", _FIVERR_ENTRY_COLS, _fiverr_entry_rows(entries), meta_e, _C.TABS[1]),
        wb, "Fiverr Entries", _C.TABS[1],
    )
    _copy_sheet_into(
        _xl("Fiverr Orders", _FIVERR_ORDER_COLS, _fiverr_order_rows(orders), meta_o, _C.TABS[2]),
        wb, "Fiverr Orders", _C.TABS[2],
    )

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf.read(), f"fiverr_{label.replace(' ', '_')}.xlsx"


async def export_upwork(db: Prisma, params: ExportQueryParams) -> tuple[bytes, str]:
    """Two-sheet workbook: Upwork Entries + Upwork Orders."""
    d_from, d_to, label = resolve_date_range(params)
    df = _prisma_date_filter(d_from, d_to)

    entries = await db.upworkentry.find_many(
        where={"date": df}, include={"profile": True}, order={"date": "asc"},
    )
    orders = await db.upworkorder.find_many(
        where={"date": df}, include={"profile": True}, order={"date": "asc"},
    )

    meta_e = {"Module": "Upwork Entries", "Period": label, "Records": str(len(entries))}
    meta_o = {"Module": "Upwork Orders",  "Period": label, "Records": str(len(orders))}

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _copy_sheet_into(
        _xl("Upwork Entries", _UPWORK_ENTRY_COLS, _upwork_entry_rows(entries), meta_e, _C.TABS[3]),
        wb, "Upwork Entries", _C.TABS[3],
    )
    _copy_sheet_into(
        _xl("Upwork Orders", _UPWORK_ORDER_COLS, _upwork_order_rows(orders), meta_o, _C.TABS[4]),
        wb, "Upwork Orders", _C.TABS[4],
    )

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf.read(), f"upwork_{label.replace(' ', '_')}.xlsx"


async def export_payoneer(db: Prisma, params: ExportQueryParams) -> tuple[bytes, str]:
    d_from, d_to, label = resolve_date_range(params)
    df = _prisma_date_filter(d_from, d_to)

    txns = await db.payoneertransaction.find_many(
        where={"date": df}, include={"account": True}, order={"date": "asc"},
    )
    meta = {
        "Module":  "Payoneer Transactions",
        "Period":  label,
        "Records": str(len(txns)),
    }
    return (
        _xl("Payoneer", _PAYONEER_COLS, _payoneer_rows(txns), meta, _C.TABS[5]),
        f"payoneer_{label.replace(' ', '_')}.xlsx",
    )


async def export_pmak(db: Prisma, params: ExportQueryParams) -> tuple[bytes, str]:
    """
    Full PMAK export including buyer, seller, notes.
    Fixes missing fields from previous version.
    """
    d_from, d_to, label = resolve_date_range(params)
    df = _prisma_date_filter(d_from, d_to)

    txns = await db.pmaktransaction.find_many(
        where={"date": df}, include={"account": True}, order={"date": "asc"},
    )
    meta = {
        "Module":  "PMAK Transactions",
        "Period":  label,
        "Records": str(len(txns)),
        "Note":    "Status values: PENDING | CLEARED | ON_HOLD | REJECTED",
    }
    return (
        _xl("PMAK", _PMAK_COLS, _pmak_rows(txns), meta, _C.TABS[6]),
        f"pmak_{label.replace(' ', '_')}.xlsx",
    )


async def export_outside_orders(db: Prisma, params: ExportQueryParams) -> tuple[bytes, str]:
    d_from, d_to, label = resolve_date_range(params)
    df = _prisma_date_filter(d_from, d_to)

    orders = await db.outsideorder.find_many(
        where={"date": df}, order={"date": "asc"},
    )
    meta = {
        "Module":  "Outside Orders",
        "Period":  label,
        "Records": str(len(orders)),
    }
    return (
        _xl("Outside Orders", _OUTSIDE_ORDER_COLS, _outside_order_rows(orders), meta, _C.TABS[7]),
        f"outside_orders_{label.replace(' ', '_')}.xlsx",
    )


async def export_dollar_exchange(db: Prisma, params: ExportQueryParams) -> tuple[bytes, str]:
    """
    Dollar Exchange with live-rate BDT column.
    Includes accountFrom / accountTo (were missing from dashboard inline).
    """
    d_from, d_to, label = resolve_date_range(params)
    df = _prisma_date_filter(d_from, d_to)

    records            = await db.dollarexchange.find_many(where={"date": df}, order={"date": "asc"})
    rate, rate_date, rate_label = await _fetch_daily_rate(db)

    rows    = _dollar_exchange_rows(records, rate)
    columns = _dollar_exchange_cols(rate_label)
    meta = {
        "Module":    "Dollar Exchange",
        "Period":    label,
        "Records":   str(len(records)),
        "Live Rate": f"৳{rate:,.2f} / $1 USD (HR set on {rate_date})" if rate else "No daily rate set",
        "Note":      "Live BDT uses today's HR rate. Entry BDT uses the rate at time of transaction.",
    }
    return (
        _xl("Dollar Exchange", columns, rows, meta, _C.TABS[8]),
        f"dollar_exchange_{label.replace(' ', '_')}.xlsx",
    )


async def export_card_sharing(db: Prisma, params: ExportQueryParams) -> tuple[bytes, str]:
    """Card sharing — cardNo and cardCvc intentionally excluded for security."""
    _, _, label = resolve_date_range(params)

    cards = await db.cardsharing.find_many(order={"serialNo": "asc"})
    rows  = [
        {
            "serialNo":        c.serialNo,
            "details":         c.details         or "",
            "payoneerAccount": c.payoneerAccount,
            "cardExpire":      c.cardExpire,
            "cardVendor":      c.cardVendor,
            "cardLimit":       c.cardLimit,
            "cardPaymentRcv":  c.cardPaymentRcv,
            "cardRcvBank":     c.cardRcvBank      or "",
            "mailDetails":     c.mailDetails      or "",
        }
        for c in cards
    ]
    columns = [
        ("Serial No",        "serialNo"),
        ("Details",          "details"),
        ("Payoneer Account", "payoneerAccount"),
        ("Card Expiry",      "cardExpire"),
        ("Card Vendor",      "cardVendor"),
        ("Card Limit ($)",   "cardLimit"),
        ("Payment RCV ($)",  "cardPaymentRcv"),
        ("Receiving Bank",   "cardRcvBank"),
        ("Mail Details",     "mailDetails"),
    ]
    meta = {
        "Module":   "Card Sharing",
        "Period":   label,
        "Records":  str(len(rows)),
        "SECURITY": "Card numbers and CVCs are intentionally excluded from this export.",
    }
    return (
        _xl("Card Sharing", columns, rows, meta, tab_color="5B21B6"),
        f"card_sharing_{label.replace(' ', '_')}.xlsx",
    )


async def export_hr_expense(db: Prisma, params: ExportQueryParams) -> tuple[bytes, str]:
    d_from, d_to, label = resolve_date_range(params)
    df = _prisma_date_filter(d_from, d_to)

    expenses = await db.hrexpense.find_many(where={"date": df}, order={"date": "asc"})
    meta = {
        "Module":  "HR Expense",
        "Period":  label,
        "Records": str(len(expenses)),
    }
    return (
        _xl("HR Expense", _HR_EXPENSE_COLS, _hr_expense_rows(expenses), meta, _C.TABS[9]),
        f"hr_expense_{label.replace(' ', '_')}.xlsx",
    )


async def export_inventory(db: Prisma, params: ExportQueryParams) -> tuple[bytes, str]:
    d_from, d_to, label = resolve_date_range(params)
    df = _prisma_date_filter(d_from, d_to)

    items = await db.inventory.find_many(where={"date": df}, order={"date": "asc"})
    meta  = {
        "Module":  "Inventory",
        "Period":  label,
        "Records": str(len(items)),
    }
    return (
        _xl("Inventory", _INVENTORY_COLS, _inventory_rows(items), meta, _C.TABS[10]),
        f"inventory_{label.replace(' ', '_')}.xlsx",
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  DASHBOARD EXPORT — 11-sheet multi-module workbook
# ═══════════════════════════════════════════════════════════════════════════════

async def export_dashboard(db: Prisma, params: ExportQueryParams) -> tuple[bytes, str]:
    """
    Full dashboard export — complete schema-field coverage for every module.

    Sheet order:
       1. KPI Summary
       2. Fiverr Entries     ← full fields (submitted, sellerPlus, promotion)
       3. Fiverr Orders      ← NEW
       4. Upwork Entries     ← full fields (workInProgress, connects, upworkPlus)
       5. Upwork Orders      ← NEW
       6. Payoneer           ← full fields (accountFrom, accountTo)
       7. PMAK               ← full fields (buyer, seller, notes)  ← FIXED
       8. Outside Orders     ← full fields (clientId, clientLink, orderDetails …)
       9. Dollar Exchange    ← full fields (accountFrom, accountTo, live BDT)
      10. HR Expense         ← full fields (accountFrom, accountTo)
      11. Inventory          ← full fields (notes)
    """
    d_from, d_to, label = resolve_date_range(params)
    df = _prisma_date_filter(d_from, d_to)

    # ── Fetch all data (sequential — prisma-client-py does not support asyncio.gather) ──
    fiverr_entries  = await db.fiverrentry.find_many(
        where={"date": df}, include={"profile": True}, order={"date": "asc"},
    )
    fiverr_orders   = await db.fiverrorder.find_many(
        where={"date": df}, include={"profile": True}, order={"date": "asc"},
    )
    upwork_entries  = await db.upworkentry.find_many(
        where={"date": df}, include={"profile": True}, order={"date": "asc"},
    )
    upwork_orders   = await db.upworkorder.find_many(
        where={"date": df}, include={"profile": True}, order={"date": "asc"},
    )
    payoneer_txns   = await db.payoneertransaction.find_many(
        where={"date": df}, include={"account": True}, order={"date": "asc"},
    )
    pmak_txns       = await db.pmaktransaction.find_many(
        where={"date": df}, include={"account": True}, order={"date": "asc"},
    )
    outside_orders  = await db.outsideorder.find_many(
        where={"date": df}, order={"date": "asc"},
    )
    dollar_records  = await db.dollarexchange.find_many(
        where={"date": df}, order={"date": "asc"},
    )
    hr_expenses     = await db.hrexpense.find_many(
        where={"date": df}, order={"date": "asc"},
    )
    inventory_items = await db.inventory.find_many(
        where={"date": df}, order={"date": "asc"},
    )
    current_rate, rate_date, rate_label = await _fetch_daily_rate(db)

    # ── All-time fetches for ledger KPIs ──────────────────────────────────────
    # Payoneer, PMAK and HR Expense show CURRENT balances (all-time latest
    # transaction), not period-filtered balances.  The period-filtered txns
    # are still used for the detail sheets — these fetches are KPI-only.
    payoneer_all = await db.payoneertransaction.find_many(
        include={"account": True}, order={"date": "asc"},
    )
    pmak_all = await db.pmaktransaction.find_many(
        include={"account": True}, order={"date": "asc"},
    )
    hr_all = await db.hrexpense.find_many(order={"date": "asc"})

    # All inventory for total asset value KPI (period sheet still uses
    # inventory_items which is date-filtered for the period detail view)
    inventory_all = await db.inventory.find_many(order={"date": "asc"})

    # ── KPI calculations ──────────────────────────────────────────────────────
    fiverr_avail   = sum(_f(e.availableWithdraw) for e in fiverr_entries)
    fiverr_cleared = sum(_f(e.notCleared)        for e in fiverr_entries)
    upwork_avail   = sum(_f(e.availableWithdraw) for e in upwork_entries)
    upwork_pending = sum(_f(e.pending)           for e in upwork_entries)

    # Latest remaining balance per account — uses ALL-TIME transactions so
    # the balance is always the true current balance, regardless of period.
    payoneer_accounts: dict[str, float] = {}
    for t in payoneer_all:          # already sorted asc by fetch order
        if t.account:
            payoneer_accounts[t.account.accountName] = _f(t.remainingBalance)
    payoneer_balance = sum(payoneer_accounts.values())

    pmak_accounts: dict[str, float] = {}
    for t in pmak_all:
        if t.account:
            pmak_accounts[t.account.accountName] = _f(t.remainingBalance)
    pmak_balance = sum(pmak_accounts.values())

    # HR Expense: latest running balance across ALL entries (all-time)
    hr_balance = _f(hr_all[-1].remainingBalance) if hr_all else 0.0

    # Inventory KPI: period items for "new this period", all-time for asset value
    inv_period_count = len(inventory_items)
    inv_period_value = sum(_f(i.totalPrice) for i in inventory_items)
    inv_total_count  = len(inventory_all)
    inv_total_value  = sum(_f(i.totalPrice) for i in inventory_all)

    dollar_total_bdt = sum(_f(r.totalBdt) for r in dollar_records)
    dollar_due_bdt   = sum(_f(r.totalBdt) for r in dollar_records if r.paymentStatus == "DUE")
    dollar_rcv_bdt   = sum(_f(r.totalBdt) for r in dollar_records if r.paymentStatus == "RECEIVED")

    fiverr_order_total  = sum(_f(o.amount) for o in fiverr_orders)
    upwork_order_total  = sum(_f(o.amount) for o in upwork_orders)
    outside_order_total = sum(_f(o.orderAmount)   for o in outside_orders)
    outside_due_total   = sum(_f(o.dueAmount)     for o in outside_orders)

    kpis = [
        {
            "label":  "Fiverr — Available Withdraw",
            "value":  fiverr_avail,
            "note":   f"{len(fiverr_entries)} entries across {len({e.profileId for e in fiverr_entries})} profiles",
            "status": "ACTIVE",
        },
        {
            "label":  "Fiverr — Not Cleared",
            "value":  fiverr_cleared,
            "note":   "Sum of notCleared across all Fiverr entries in period",
            "status": "PENDING",
        },
        {
            "label":  "Fiverr Orders — Total",
            "value":  fiverr_order_total,
            "note":   f"{len(fiverr_orders)} orders in period",
            "status": "ACTIVE",
        },
        {
            "label":  "Upwork — Available Withdraw",
            "value":  upwork_avail,
            "note":   f"{len(upwork_entries)} entries across {len({e.profileId for e in upwork_entries})} profiles",
            "status": "ACTIVE",
        },
        {
            "label":  "Upwork — Pending",
            "value":  upwork_pending,
            "note":   "Sum of pending across all Upwork entries in period",
            "status": "PENDING",
        },
        {
            "label":  "Upwork Orders — Total",
            "value":  upwork_order_total,
            "note":   f"{len(upwork_orders)} orders in period",
            "status": "ACTIVE",
        },
        {
            "label":  "Payoneer Balance (Current)",
            "value":  payoneer_balance,
            "note":   f"Latest all-time balance per account  |  {len(payoneer_txns)} txns in period",
            "status": "ACTIVE",
        },
        {
            "label":  "PMAK Balance (Current)",
            "value":  pmak_balance,
            "note":   f"Latest all-time balance per account  |  {len(pmak_txns)} txns in period",
            "status": "ACTIVE",
        },
        {
            "label":  "Dollar Exchange — Total BDT",
            "value":  dollar_total_bdt,
            "note":   f"RECEIVED ৳{dollar_rcv_bdt:,.2f}  |  DUE ৳{dollar_due_bdt:,.2f}  |  Rate: {rate_label}",
            "status": "RECEIVED" if dollar_due_bdt == 0 else "DUE",
        },
        {
            "label":  "Outside Orders — Total",
            "value":  outside_order_total,
            "note":   f"{len(outside_orders)} orders  |  Due: ৳{outside_due_total:,.2f}",
            "status": "PENDING" if outside_due_total > 0 else "COMPLETED",
        },
        {
            "label":  "HR Expense (Current Balance)",
            "value":  hr_balance,
            "note":   f"Latest all-time ledger balance  |  {len(hr_expenses)} entries in period",
            "status": "ACTIVE",
        },
        {
            "label":  "Inventory — Period Additions",
            "value":  inv_period_value,
            "note":   f"{inv_period_count} new items this period  |  Total assets: ৳{inv_total_value:,.2f} ({inv_total_count} items)",
            "status": "ACTIVE" if inv_period_count > 0 else "PENDING",
        },
    ]

    # ── Build workbook ────────────────────────────────────────────────────────
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # Sheet 1 — KPI Summary
    _build_kpi_summary(wb, label, kpis, _C.TABS[0])

    # Sheet 2 — Fiverr Entries
    _copy_sheet_into(
        _xl("Fiverr Entries", _FIVERR_ENTRY_COLS, _fiverr_entry_rows(fiverr_entries),
            {"Module": "Fiverr Entries", "Period": label}),
        wb, "Fiverr Entries", _C.TABS[1],
    )

    # Sheet 3 — Fiverr Orders  (NEW)
    _copy_sheet_into(
        _xl("Fiverr Orders", _FIVERR_ORDER_COLS, _fiverr_order_rows(fiverr_orders),
            {"Module": "Fiverr Orders", "Period": label}),
        wb, "Fiverr Orders", _C.TABS[2],
    )

    # Sheet 4 — Upwork Entries
    _copy_sheet_into(
        _xl("Upwork Entries", _UPWORK_ENTRY_COLS, _upwork_entry_rows(upwork_entries),
            {"Module": "Upwork Entries", "Period": label}),
        wb, "Upwork Entries", _C.TABS[3],
    )

    # Sheet 5 — Upwork Orders  (NEW)
    _copy_sheet_into(
        _xl("Upwork Orders", _UPWORK_ORDER_COLS, _upwork_order_rows(upwork_orders),
            {"Module": "Upwork Orders", "Period": label}),
        wb, "Upwork Orders", _C.TABS[4],
    )

    # Sheet 6 — Payoneer (full fields)
    _copy_sheet_into(
        _xl("Payoneer", _PAYONEER_COLS, _payoneer_rows(payoneer_txns),
            {"Module": "Payoneer", "Period": label}),
        wb, "Payoneer", _C.TABS[5],
    )

    # Sheet 7 — PMAK (full fields + buyer/seller/notes FIXED)
    _copy_sheet_into(
        _xl("PMAK", _PMAK_COLS, _pmak_rows(pmak_txns),
            {"Module": "PMAK", "Period": label,
             "Note": "Status: PENDING | CLEARED | ON_HOLD | REJECTED"}),
        wb, "PMAK", _C.TABS[6],
    )

    # Sheet 8 — Outside Orders (full fields)
    _copy_sheet_into(
        _xl("Outside Orders", _OUTSIDE_ORDER_COLS, _outside_order_rows(outside_orders),
            {"Module": "Outside Orders", "Period": label}),
        wb, "Outside Orders", _C.TABS[7],
    )

    # Sheet 9 — Dollar Exchange (full fields + live BDT)
    _copy_sheet_into(
        _xl("Dollar Exchange", _dollar_exchange_cols(rate_label),
            _dollar_exchange_rows(dollar_records, current_rate),
            {"Module": "Dollar Exchange", "Period": label,
             "Live Rate": f"৳{current_rate:,.2f}/$1 (set by HR on {rate_date})" if current_rate else "N/A"}),
        wb, "Dollar Exchange", _C.TABS[8],
    )

    # Sheet 10 — HR Expense (full fields)
    _copy_sheet_into(
        _xl("HR Expense", _HR_EXPENSE_COLS, _hr_expense_rows(hr_expenses),
            {"Module": "HR Expense", "Period": label}),
        wb, "HR Expense", _C.TABS[9],
    )

    # Sheet 11 — Inventory (full fields + notes)
    _copy_sheet_into(
        _xl("Inventory", _INVENTORY_COLS, _inventory_rows(inventory_items),
            {"Module": "Inventory", "Period": label}),
        wb, "Inventory", _C.TABS[10],
    )

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe_label = label.replace(" ", "_").replace("–", "-")
    return buf.read(), f"dashboard_{safe_label}.xlsx"