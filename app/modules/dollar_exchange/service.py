"""
app/modules/dollar_exchange/service.py
========================================
v2 — Additions:
  • list_exchanges() — new optional filter: account_from (icontains)
  • export_exchanges() — openpyxl Excel export with per-account & date filtering

SCHEMA FACTS (schema.prisma — ground truth):
  Field name   : paymentStatus            ← camelCase, matches schema exactly
  Enum type    : PaymentStatus            ← defined in schema.prisma
  Enum values  : RECEIVED | DUE           ← use these exact strings everywhere

PRISMA-CLIENT-PY RULES:
  create/update data dict  → "paymentStatus": "RECEIVED"  (exact schema field + enum value)
  where/filter dict        → "paymentStatus": "RECEIVED"
  Python attribute access  → r.paymentStatus

NOTE ON .aggregate():
  prisma-client-py does NOT expose a model-level .aggregate() method.
  All aggregation is done via db.query_raw() with raw PostgreSQL SQL.
"""
import io
from datetime import date as dt_date
from decimal import Decimal
from typing import Optional

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from fastapi import HTTPException
from prisma import Prisma

from .schema import DollarExchangeCreate, DollarExchangeUpdate


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────

async def create_exchange(db: Prisma, data: DollarExchangeCreate):
    return await db.dollarexchange.create(
        data={
            "date":          data.date,
            "details":       data.details,
            "accountFrom":   data.accountFrom,
            "accountTo":     data.accountTo,
            "debit":         data.debit,
            "credit":        data.credit,
            "rate":          data.rate,
            "totalBdt":      data.total_bdt,
            "paymentStatus": data.payment_status.value,
        }
    )


async def list_exchanges(
    db:             Prisma,
    date_filter:    dict,
    payment_status: Optional[str] = None,
    account_from:   Optional[str] = None,
):
    """
    List dollar exchange records with optional filters.

    Filters (all combinable):
      date_filter    — Prisma-compatible dict from DateRangeFilter.to_prisma_filter()
      payment_status — "RECEIVED" | "DUE" (also accepts legacy "RCV" alias)
      account_from   — case-insensitive substring search on accountFrom
    """
    where: dict = {}

    if date_filter:
        where["date"] = date_filter

    if payment_status:
        status = (
            "RECEIVED"
            if payment_status.upper() in ("RECEIVED", "RCV")
            else payment_status.upper()
        )
        where["paymentStatus"] = status

    if account_from:
        where["accountFrom"] = {"contains": account_from, "mode": "insensitive"}

    return await db.dollarexchange.find_many(where=where, order={"date": "desc"})


async def get_exchange(db: Prisma, exchange_id: str):
    record = await db.dollarexchange.find_unique(where={"id": exchange_id})
    if not record:
        raise HTTPException(status_code=404, detail="Exchange record not found")
    return record


async def update_exchange(db: Prisma, exchange_id: str, data: DollarExchangeUpdate):
    existing = await get_exchange(db, exchange_id)

    update_data: dict = {}

    if data.payment_status is not None:
        update_data["paymentStatus"] = data.payment_status.value

    if data.details is not None:
        update_data["details"] = data.details

    if data.accountFrom is not None:
        update_data["accountFrom"] = data.accountFrom

    if data.accountTo is not None:
        update_data["accountTo"] = data.accountTo

    if data.rate is not None:
        new_rate = data.rate
        exchange_amount = (
            existing.credit
            if (existing.credit and existing.credit > 0)
            else existing.debit or Decimal("0")
        )
        update_data["rate"]     = new_rate
        update_data["totalBdt"] = exchange_amount * new_rate

    if not update_data:
        return existing

    return await db.dollarexchange.update(
        where={"id": exchange_id},
        data=update_data,
    )


async def delete_exchange(db: Prisma, exchange_id: str) -> None:
    await get_exchange(db, exchange_id)
    await db.dollarexchange.delete(where={"id": exchange_id})


async def get_total_bdt(db: Prisma) -> dict:
    """
    Return total BDT split by payment status (query_raw — no .aggregate() in prisma-client-py).
    """
    rows = await db.query_raw(
        """
        SELECT
            COALESCE(SUM("totalBdt"), 0)                                                  AS total,
            COALESCE(SUM(CASE WHEN "paymentStatus" = 'RECEIVED' THEN "totalBdt" END), 0) AS received,
            COALESCE(SUM(CASE WHEN "paymentStatus" = 'DUE'      THEN "totalBdt" END), 0) AS due
        FROM dollar_exchanges
        """
    )
    r = rows[0] if rows else {}
    return {
        "total":    float(r.get("total",    0) or 0),
        "received": float(r.get("received", 0) or 0),
        "due":      float(r.get("due",      0) or 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Excel export
# ─────────────────────────────────────────────────────────────────────────────

_HEADERS = [
    "Date", "Details", "Account From", "Account To",
    "Debit (USD)", "Credit (USD)", "Rate", "Total BDT", "Payment Status",
]

_HEADER_FILL  = PatternFill("solid", fgColor="1F4E79")
_HEADER_FONT  = Font(bold=True, color="FFFFFF", size=11)
_ALT_ROW_FILL = PatternFill("solid", fgColor="D6E4F0")
_DUE_FILL     = PatternFill("solid", fgColor="FCE4D6")   # light red for DUE rows
_CENTER       = Alignment(horizontal="center", vertical="center")
_LEFT         = Alignment(horizontal="left",   vertical="center", wrap_text=True)

_COL_WIDTHS = [12, 36, 22, 22, 14, 14, 10, 18, 16]


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, dt_date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return str(v)


async def export_exchanges(
    db:             Prisma,
    date_filter:    dict,
    payment_status: Optional[str] = None,
    account_from:   Optional[str] = None,
    label:          str = "dollar_exchange",
) -> tuple[bytes, str]:
    """
    Build and return (xlsx_bytes, filename) for the filtered exchange records.
    DUE rows are highlighted in light red for quick identification.
    """
    rows = await list_exchanges(db, date_filter, payment_status, account_from)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Dollar Exchange"

    # ── Header ────────────────────────────────────────────────────────────────
    ws.row_dimensions[1].height = 22
    for col_idx, (header, width) in enumerate(zip(_HEADERS, _COL_WIDTHS), start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font      = _HEADER_FONT
        cell.fill      = _HEADER_FILL
        cell.alignment = _CENTER
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # ── Data rows ─────────────────────────────────────────────────────────────
    for row_idx, exc in enumerate(rows, start=2):
        is_due   = str(getattr(exc, "paymentStatus", "")).upper() == "DUE"
        row_fill = _DUE_FILL if is_due else (_ALT_ROW_FILL if row_idx % 2 == 0 else None)

        values = [
            _fmt(exc.date),
            _fmt(exc.details),
            _fmt(exc.accountFrom),
            _fmt(exc.accountTo),
            float(exc.debit),
            float(exc.credit),
            float(exc.rate),
            float(exc.totalBdt),
            str(exc.paymentStatus),
        ]
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = _CENTER if col_idx in (1, 9) else _LEFT
            if row_fill:
                cell.fill = row_fill

    # ── Summary ───────────────────────────────────────────────────────────────
    if rows:
        s = len(rows) + 2
        ws.cell(row=s, column=7,  value="TOTAL").font = Font(bold=True)
        ws.cell(row=s, column=5,  value=sum(float(r.debit)    for r in rows)).font = Font(bold=True)
        ws.cell(row=s, column=6,  value=sum(float(r.credit)   for r in rows)).font = Font(bold=True)
        ws.cell(row=s, column=8,  value=sum(float(r.totalBdt) for r in rows)).font = Font(bold=True)

    ws.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{label}.xlsx"
    return buffer.read(), filename