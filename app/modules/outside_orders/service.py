"""
app/modules/outside_orders/service.py
========================================
v2 — Additions:
  • list_orders()  — new optional filters: client_name (icontains), assign_team (icontains)
  • export_orders() — generates an openpyxl Excel workbook and returns raw bytes
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

from .schema import OutsideOrderCreate, OutsideOrderUpdate


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────

async def create_order(db: Prisma, data: OutsideOrderCreate):
    existing = await db.outsideorder.find_unique(where={"clientId": data.client_id})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Client ID '{data.client_id}' already exists",
        )

    due = float(data.order_amount) - float(data.receive_amount)
    return await db.outsideorder.create(
        data={
            "clientId":            data.client_id,
            "clientName":          data.client_name,
            "clientLink":          data.client_link,
            "orderDetails":        data.order_details,
            "orderSheet":          data.order_sheet,
            "assignTeam":          data.assign_team,
            "status":              data.status.value if hasattr(data.status, "value") else data.status,
            "orderAmount":         data.order_amount,
            "receiveAmount":       data.receive_amount,
            "dueAmount":           due,
            "paymentMethod":       data.payment_method,
            "paymentMethodDetails": data.payment_method_details,
            "date":                data.date,
        }
    )


async def list_orders(
    db: Prisma,
    date_filter: dict,
    status:      Optional[str] = None,
    client_name: Optional[str] = None,
    assign_team: Optional[str] = None,
):
    """
    List outside orders with optional filters.

    Filters (all combinable):
      date_filter  — Prisma-compatible dict from DateRangeFilter.to_prisma_filter()
      status       — exact match on orderStatus enum value (case-insensitive normalised)
      client_name  — case-insensitive substring search on clientName
      assign_team  — case-insensitive substring search on assignTeam
    """
    where: dict = {}

    if date_filter:
        where["date"] = date_filter

    if status:
        where["status"] = status.upper()

    if client_name:
        where["clientName"] = {"contains": client_name, "mode": "insensitive"}

    if assign_team:
        where["assignTeam"] = {"contains": assign_team, "mode": "insensitive"}

    return await db.outsideorder.find_many(where=where, order={"date": "desc"})


async def get_order(db: Prisma, order_id: str):
    order = await db.outsideorder.find_unique(where={"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


async def update_order(db: Prisma, order_id: str, data: OutsideOrderUpdate):
    order = await get_order(db, order_id)

    update_data: dict = {}
    if data.client_name is not None:
        update_data["clientName"] = data.client_name
    if data.client_link is not None:
        update_data["clientLink"] = data.client_link
    if data.order_details is not None:
        update_data["orderDetails"] = data.order_details
    if data.order_sheet is not None:
        update_data["orderSheet"] = data.order_sheet
    if data.assign_team is not None:
        update_data["assignTeam"] = data.assign_team
    if data.status is not None:
        update_data["status"] = data.status.value if hasattr(data.status, "value") else data.status
    if data.payment_method is not None:
        update_data["paymentMethod"] = data.payment_method
    if data.payment_method_details is not None:
        update_data["paymentMethodDetails"] = data.payment_method_details

    order_amount   = float(data.order_amount)   if data.order_amount   is not None else float(order.orderAmount)
    receive_amount = float(data.receive_amount) if data.receive_amount is not None else float(order.receiveAmount)

    if data.order_amount is not None:
        update_data["orderAmount"]   = data.order_amount
    if data.receive_amount is not None:
        update_data["receiveAmount"] = data.receive_amount

    update_data["dueAmount"] = order_amount - receive_amount

    return await db.outsideorder.update(where={"id": order_id}, data=update_data)


async def delete_order(db: Prisma, order_id: str):
    await get_order(db, order_id)
    await db.outsideorder.delete(where={"id": order_id})


# ─────────────────────────────────────────────────────────────────────────────
# Excel export
# ─────────────────────────────────────────────────────────────────────────────

_HEADERS = [
    "Date", "Client ID", "Client Name", "Client Link",
    "Order Details", "Status", "Order Amount (USD)", "Received Amount (USD)",
    "Due Amount (USD)", "Payment Method", "Payment Details", "Assign Team",
]

_HEADER_FILL  = PatternFill("solid", fgColor="1F4E79")
_HEADER_FONT  = Font(bold=True, color="FFFFFF", size=11)
_ALT_ROW_FILL = PatternFill("solid", fgColor="D6E4F0")
_CENTER       = Alignment(horizontal="center", vertical="center", wrap_text=False)
_LEFT         = Alignment(horizontal="left",   vertical="center", wrap_text=True)

_COL_WIDTHS = [12, 16, 22, 28, 40, 12, 20, 20, 18, 18, 28, 18]


def _fmt(v) -> str:
    """Safe string formatter for cell values."""
    if v is None:
        return ""
    if isinstance(v, dt_date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return str(v)


async def export_orders(
    db:          Prisma,
    date_filter: dict,
    status:      Optional[str] = None,
    client_name: Optional[str] = None,
    assign_team: Optional[str] = None,
    label:       str = "outside_orders",
) -> tuple[bytes, str]:
    """
    Build and return (xlsx_bytes, filename) for the filtered orders.

    Parameters mirror list_orders() so the same filters apply to export.
    label is used as the sheet name and filename prefix.
    """
    rows = await list_orders(db, date_filter, status, client_name, assign_team)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Outside Orders"

    # ── Header row ────────────────────────────────────────────────────────────
    ws.row_dimensions[1].height = 22
    for col_idx, (header, width) in enumerate(zip(_HEADERS, _COL_WIDTHS), start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font      = _HEADER_FONT
        cell.fill      = _HEADER_FILL
        cell.alignment = _CENTER
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # ── Data rows ─────────────────────────────────────────────────────────────
    for row_idx, order in enumerate(rows, start=2):
        fill = _ALT_ROW_FILL if row_idx % 2 == 0 else None
        values = [
            _fmt(order.date),
            _fmt(order.clientId),
            _fmt(order.clientName),
            _fmt(order.clientLink),
            _fmt(order.orderDetails),
            _fmt(getattr(order, "orderStatus", None) or getattr(order, "status", "")),
            float(order.orderAmount),
            float(order.receiveAmount),
            float(order.dueAmount),
            _fmt(order.paymentMethod),
            _fmt(order.paymentMethodDetails),
            _fmt(order.assignTeam),
        ]
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = _CENTER if col_idx in (1, 6) else _LEFT
            if fill:
                cell.fill = fill

    # ── Summary row ───────────────────────────────────────────────────────────
    if rows:
        summary_row = len(rows) + 2
        ws.cell(row=summary_row, column=6,  value="TOTAL").font = Font(bold=True)
        ws.cell(row=summary_row, column=7,  value=sum(float(r.orderAmount)   for r in rows)).font = Font(bold=True)
        ws.cell(row=summary_row, column=8,  value=sum(float(r.receiveAmount) for r in rows)).font = Font(bold=True)
        ws.cell(row=summary_row, column=9,  value=sum(float(r.dueAmount)     for r in rows)).font = Font(bold=True)

    ws.freeze_panes = "A2"

    # ── Serialize ─────────────────────────────────────────────────────────────
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{label}.xlsx"
    return buffer.read(), filename