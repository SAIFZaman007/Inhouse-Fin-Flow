"""
app/modules/upwork/service.py
════════════════════════════════════════════════════════════════════════════════
v6 — Enterprise Edition

Changes vs v5
─────────────
update_profile   NEW — PATCH /profiles/{id}
                       Partial rename + isActive toggle. Uniqueness enforced.
update_order     NEW — PATCH /orders/{id}
                       Partial field update; afterUpwork auto-recomputed when
                       amount changes. orderId uniqueness enforced on rename.

Everything else is unchanged from v5.
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import io
import logging
import math
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException
from prisma import Prisma

from app.shared.filters import DateRangeFilter
from app.shared.pagination import PageParams
from .schema import (
    UpworkOrderCreate,
    UpworkOrderUpdate,
    UpworkProfileCreate,
    UpworkProfileUpdate,
    UpworkSnapshotCreate,
)

logger = logging.getLogger(__name__)

_UPWORK_FEE = Decimal("0.10")
_ZERO       = Decimal("0")


# ── Private helpers ───────────────────────────────────────────────────────────

def _d(v: Any) -> Decimal:
    return _ZERO if v is None else Decimal(str(v))


def _after_upwork(amount: Decimal) -> Decimal:
    return (amount * (1 - _UPWORK_FEE)).quantize(Decimal("0.01"))


def _pagination_meta(pagination: Optional[PageParams], total: int) -> dict:
    if pagination is None:
        return {"page": 1, "pageSize": total, "total": total, "totalPages": 1}
    return {
        "page":       pagination.page,
        "pageSize":   pagination.page_size,
        "total":      total,
        "totalPages": math.ceil(total / pagination.page_size) if total > 0 else 1,
    }


async def _resolve_profile_by_name(db: Prisma, profile_name: str):
    """Return active UpworkProfile by case-insensitive name, or raise 404."""
    profile = await db.upworkprofile.find_first(
        where={
            "profileName": {"equals": profile_name, "mode": "insensitive"},
            "isActive":    True,
        }
    )
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Upwork profile '{profile_name}' not found.",
        )
    return profile


async def _get_profile_or_404(db: Prisma, profile_id: str):
    profile = await db.upworkprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Upwork profile not found.")
    return profile


async def _get_order_or_404(db: Prisma, order_id: str):
    order = await db.upworkorder.find_unique(where={"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Upwork order not found.")
    return order


def _snapshot_to_dict(entry: Any, profile_name: str) -> dict:
    aw = _d(entry.availableWithdraw)
    return {
        "id":                        entry.id,
        "profileName":               profile_name,
        "date":                      entry.date.date() if isinstance(entry.date, datetime) else entry.date,
        "availableWithdraw":         float(aw),
        "availableWithdrawAfterFee": float(aw * (1 - _UPWORK_FEE)),
        "pending":                   float(_d(entry.pending)),
        "inReview":                  float(_d(entry.inReview)),
        "workInProgress":            float(_d(entry.workInProgress)),
        "withdrawn":                 float(_d(entry.withdrawn)),
        "connects":                  entry.connects,
        "upworkPlus":                entry.upworkPlus,
        "createdAt":                 entry.createdAt,
    }


def _order_to_dict(order: Any) -> dict:
    return {
        "id":          order.id,
        "profileId":   order.profileId,
        "date":        order.date.date() if isinstance(order.date, datetime) else order.date,
        "clientName":  order.clientName,
        "orderId":     order.orderId,
        "amount":      float(_d(order.amount)),
        "afterUpwork": float(_d(order.afterUpwork)),
        "createdAt":   order.createdAt,
    }


# ── Profile CRUD ──────────────────────────────────────────────────────────────

async def create_profile(db: Prisma, data: UpworkProfileCreate) -> dict:
    existing = await db.upworkprofile.find_unique(
        where={"profileName": data.profileName}
    )
    if existing:
        raise HTTPException(status_code=409, detail="Profile name already exists.")

    profile = await db.upworkprofile.create(
        data={"profileName": data.profileName}
    )

    snapshot_data: Optional[dict] = None
    if data.available_withdraw is not None:
        snap_date = data.snapshot_date or date.today()
        entry = await db.upworkentry.create(
            data={
                "profileId":        profile.id,
                "date":             datetime.combine(snap_date, time.min),
                "availableWithdraw": data.available_withdraw,
                "pending":          data.pending,
                "inReview":         data.in_review,
                "workInProgress":   data.work_in_progress,
                "withdrawn":        data.withdrawn,
                "connects":         data.connects,
                "upworkPlus":       data.upwork_plus,
            }
        )
        snapshot_data = _snapshot_to_dict(entry, profile.profileName)

    return {
        "id":              profile.id,
        "profileName":     profile.profileName,
        "isActive":        profile.isActive,
        "initialSnapshot": snapshot_data,
    }


async def update_profile(
    db: Prisma,
    profile_id: str,
    data: UpworkProfileUpdate,
) -> dict:
    """
    PATCH /profiles/{id} — partial profile update.

    • Rename: profileName uniqueness checked before writing.
    • isActive toggle: supports both soft-delete and restore.
    • Returns the updated lightweight profile dict.
    """
    profile = await _get_profile_or_404(db, profile_id)

    patch: dict = {}

    if data.profileName is not None and data.profileName != profile.profileName:
        conflict = await db.upworkprofile.find_first(
            where={
                "profileName": {"equals": data.profileName, "mode": "insensitive"},
                "id":          {"not": profile_id},
            }
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Profile name '{data.profileName}' is already taken.",
            )
        patch["profileName"] = data.profileName

    if data.isActive is not None:
        patch["isActive"] = data.isActive

    if not patch:
        return {
            "id":          profile.id,
            "profileName": profile.profileName,
            "isActive":    profile.isActive,
        }

    updated = await db.upworkprofile.update(
        where={"id": profile_id},
        data=patch,
    )
    return {
        "id":          updated.id,
        "profileName": updated.profileName,
        "isActive":    updated.isActive,
    }


async def deactivate_profile(db: Prisma, profile_id: str) -> None:
    profile = await db.upworkprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Upwork profile not found.")
    await db.upworkprofile.update(
        where={"id": profile_id}, data={"isActive": False}
    )


# ── Snapshot CRUD ─────────────────────────────────────────────────────────────

async def create_snapshot(db: Prisma, data: UpworkSnapshotCreate) -> dict:
    profile     = await _resolve_profile_by_name(db, data.profile_name)
    upsert_date = datetime.combine(data.date, time.min)
    payload     = {
        "date":             upsert_date,
        "availableWithdraw": data.available_withdraw,
        "pending":          data.pending,
        "inReview":         data.in_review,
        "workInProgress":   data.work_in_progress,
        "withdrawn":        data.withdrawn,
        "connects":         data.connects,
        "upworkPlus":       data.upwork_plus,
    }

    existing = await db.upworkentry.find_first(
        where={"profileId": profile.id, "date": upsert_date}
    )

    if existing:
        entry = await db.upworkentry.update(
            where={"id": existing.id},
            data={k: v for k, v in payload.items() if k != "date"},
        )
    else:
        entry = await db.upworkentry.create(
            data={"profileId": profile.id, **payload}
        )

    aw = _d(entry.availableWithdraw)
    return {
        "id":                        entry.id,
        "profileId":                 entry.profileId,
        "profileName":               profile.profileName,
        "date":                      entry.date.date() if isinstance(entry.date, datetime) else entry.date,
        "availableWithdraw":         aw,
        "availableWithdrawAfterFee": aw * (1 - _UPWORK_FEE),
        "pending":                   _d(entry.pending),
        "inReview":                  _d(entry.inReview),
        "workInProgress":            _d(entry.workInProgress),
        "withdrawn":                 _d(entry.withdrawn),
        "connects":                  entry.connects,
        "upworkPlus":                entry.upworkPlus,
        "createdAt":                 entry.createdAt,
    }


async def get_profile_snapshots(
    db: Prisma,
    profile_id: str,
    date_filter: dict,
    pagination: Optional[PageParams] = None,
) -> dict:
    profile = await _get_profile_or_404(db, profile_id)

    where: dict = {"profileId": profile_id}
    if date_filter:
        where["date"] = date_filter

    total   = await db.upworkentry.count(where=where)
    find_kw = dict(where=where, order={"date": "desc"})
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    entries = await db.upworkentry.find_many(**find_kw)

    return {
        "profileName": profile.profileName,
        "pagination":  _pagination_meta(pagination, total),
        "snapshots":   [_snapshot_to_dict(e, profile.profileName) for e in entries],
    }


# ── Order CRUD ────────────────────────────────────────────────────────────────

async def add_order(db: Prisma, data: UpworkOrderCreate) -> dict:
    profile = await _resolve_profile_by_name(db, data.profile_name)

    conflict = await db.upworkorder.find_unique(where={"orderId": data.order_id})
    if conflict:
        raise HTTPException(status_code=409, detail=f"Order ID '{data.order_id}' already exists.")

    order = await db.upworkorder.create(
        data={
            "profileId":  profile.id,
            "date":       datetime.combine(data.date, time.min),
            "clientName": data.client_name,
            "orderId":    data.order_id,
            "amount":     data.amount,
            "afterUpwork": _after_upwork(data.amount),
        }
    )
    return _order_to_dict(order)


async def update_order(
    db: Prisma,
    order_id: str,
    data: UpworkOrderUpdate,
) -> dict:
    """
    PATCH /orders/{id} — partial order update.

    • date / client_name are free to change.
    • order_id rename: uniqueness is checked before writing.
    • amount change: afterUpwork is automatically re-computed (× 0.90).
    • Returns the updated full order dict.
    """
    order = await _get_order_or_404(db, order_id)

    patch: dict = {}

    if data.date is not None:
        patch["date"] = datetime.combine(data.date, time.min)

    if data.client_name is not None:
        patch["clientName"] = data.client_name

    if data.order_id is not None and data.order_id != order.orderId:
        conflict = await db.upworkorder.find_unique(
            where={"orderId": data.order_id}
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Order ID '{data.order_id}' is already in use.",
            )
        patch["orderId"] = data.order_id

    if data.amount is not None:
        patch["amount"]     = data.amount
        patch["afterUpwork"] = _after_upwork(data.amount)

    if not patch:
        return _order_to_dict(order)

    updated = await db.upworkorder.update(
        where={"id": order_id},
        data=patch,
    )
    return _order_to_dict(updated)


async def get_profile_orders(
    db: Prisma,
    profile_id: str,
    date_filter: dict,
    pagination: Optional[PageParams] = None,
) -> dict:
    profile = await _get_profile_or_404(db, profile_id)

    where: dict = {"profileId": profile_id}
    if date_filter:
        where["date"] = date_filter

    total   = await db.upworkorder.count(where=where)
    find_kw = dict(where=where, order={"date": "desc"})
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    orders = await db.upworkorder.find_many(**find_kw)

    return {
        "profileName": profile.profileName,
        "pagination":  _pagination_meta(pagination, total),
        "orders":      [_order_to_dict(o) for o in orders],
    }


# ── Profile list / detail ─────────────────────────────────────────────────────

async def list_profiles_summary(
    db: Prisma,
    filters: DateRangeFilter,
    name: Optional[str] = None,
    pagination: Optional[PageParams] = None,
) -> dict:
    date_f = filters.to_prisma_filter()

    where: dict = {"isActive": True}
    if name:
        where["profileName"] = {"contains": name, "mode": "insensitive"}

    total_profiles = await db.upworkprofile.count(where=where)

    find_kw: dict = dict(
        where=where,
        include={
            "entries": {
                "where":    {"date": date_f} if date_f else {},
                "order_by": {"date": "desc"},
            },
            "orders": {
                "where":    {"date": date_f} if date_f else {},
                "order_by": {"date": "desc"},
            },
        },
        order={"profileName": "asc"},
    )
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    profiles = await db.upworkprofile.find_many(**find_kw)

    t_aw = t_pend = t_ir = t_wip = t_wd = t_rev = _ZERO
    t_conn = 0

    summaries = []
    for p in profiles:
        latest     = p.entries[0] if p.entries else None
        period_aw  = _d(latest.availableWithdraw) if latest else _ZERO
        period_pend = sum((_d(e.pending)         for e in p.entries), _ZERO)
        period_ir   = sum((_d(e.inReview)         for e in p.entries), _ZERO)
        period_wip  = sum((_d(e.workInProgress)   for e in p.entries), _ZERO)
        period_wd   = sum((_d(e.withdrawn)         for e in p.entries), _ZERO)
        period_conn = sum((e.connects              for e in p.entries), 0)
        rev         = sum((_d(o.afterUpwork)       for o in p.orders),  _ZERO)

        t_aw   += period_aw
        t_pend += period_pend
        t_ir   += period_ir
        t_wip  += period_wip
        t_wd   += period_wd
        t_conn += period_conn
        t_rev  += rev

        summaries.append({
            "id":          p.id,
            "profileName": p.profileName,
            "isActive":    p.isActive,
            "latestSnapshot": _snapshot_to_dict(latest, p.profileName) if latest else None,
            "periodTotals": {
                "availableWithdraw":         float(period_aw),
                "availableWithdrawAfterFee": float(period_aw * (1 - _UPWORK_FEE)),
                "pending":                   float(period_pend),
                "inReview":                  float(period_ir),
                "workInProgress":            float(period_wip),
                "withdrawn":                 float(period_wd),
                "connects":                  period_conn,
            },
            "snapshotCount":   len(p.entries),
            "orderCount":      len(p.orders),
            "revenueInPeriod": float(rev),
            "orders":          [_order_to_dict(o) for o in p.orders],
        })

    return {
        "filter": filters.meta(),
        "totals": {
            "totalAvailableWithdraw":         float(t_aw),
            "totalAvailableWithdrawAfterFee": float(t_aw * (1 - _UPWORK_FEE)),
            "totalPending":                   float(t_pend),
            "totalInReview":                  float(t_ir),
            "totalWorkInProgress":            float(t_wip),
            "totalWithdrawn":                 float(t_wd),
            "totalConnects":                  t_conn,
            "totalRevenueInPeriod":           float(t_rev),
            "activeProfileCount":             total_profiles,
        },
        "pagination": _pagination_meta(pagination, total_profiles),
        "profiles":   summaries,
    }


async def get_profile_detail(
    db: Prisma,
    profile_id: str,
    filters: DateRangeFilter,
    pagination: Optional[PageParams] = None,
) -> dict:
    profile = await _get_profile_or_404(db, profile_id)
    date_f  = filters.to_prisma_filter()

    snap_where: dict = {"profileId": profile_id}
    ord_where:  dict = {"profileId": profile_id}
    if date_f:
        snap_where["date"] = date_f
        ord_where["date"]  = date_f

    snap_total = await db.upworkentry.count(where=snap_where)
    ord_total  = await db.upworkorder.count(where=ord_where)

    snap_kw = dict(where=snap_where, order={"date": "desc"})
    ord_kw  = dict(where=ord_where,  order={"date": "desc"})
    if pagination:
        snap_kw["skip"] = pagination.skip
        snap_kw["take"] = pagination.take
        ord_kw["skip"]  = pagination.skip
        ord_kw["take"]  = pagination.take

    entries = await db.upworkentry.find_many(**snap_kw)
    orders  = await db.upworkorder.find_many(**ord_kw)

    latest = entries[0] if entries else None
    aw     = _d(latest.availableWithdraw) if latest else _ZERO
    rev    = sum((_d(o.afterUpwork) for o in orders), _ZERO)

    return {
        "filter":  filters.meta(),
        "profile": {
            "id":          profile.id,
            "profileName": profile.profileName,
            "isActive":    profile.isActive,
        },
        "periodTotals": {
            "availableWithdraw":         float(aw),
            "availableWithdrawAfterFee": float(aw * (1 - _UPWORK_FEE)),
            "pending":          float(sum((_d(e.pending)        for e in entries), _ZERO)),
            "inReview":         float(sum((_d(e.inReview)        for e in entries), _ZERO)),
            "workInProgress":   float(sum((_d(e.workInProgress)  for e in entries), _ZERO)),
            "withdrawn":        float(sum((_d(e.withdrawn)       for e in entries), _ZERO)),
            "connects":         sum((e.connects                  for e in entries), 0),
            "revenueInPeriod":  float(rev),
            "snapshotCount":    snap_total,
            "orderCount":       ord_total,
        },
        "pagination": _pagination_meta(pagination, max(snap_total, ord_total)),
        "snapshots":  [_snapshot_to_dict(e, profile.profileName) for e in entries],
        "orders":     [_order_to_dict(o) for o in orders],
    }


# ── Single-profile Excel export ───────────────────────────────────────────────

async def export_profile_excel(
    db: Prisma,
    profile_id: str,
    filters: DateRangeFilter,
) -> tuple[bytes, str]:
    """Two-sheet Excel workbook: Snapshots + Orders for one profile."""
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="openpyxl not installed — cannot generate Excel export.",
        )

    detail   = await get_profile_detail(db, profile_id, filters)
    p_name   = detail["profile"]["profileName"]
    start, end = filters.window()

    wb          = openpyxl.Workbook()
    HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
    HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
    ALT_FILL    = PatternFill("solid", fgColor="EBF3FB")

    def _header(ws, cols):
        for c, h in enumerate(cols, 1):
            cell = ws.cell(row=1, column=c, value=h)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 20

    def _autofit(ws):
        for col in ws.columns:
            w = max((len(str(cell.value or "")) for cell in col), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(w + 4, 40)

    # Sheet 1 — Snapshots
    ws1 = wb.active
    ws1.title = "Snapshots"
    _header(ws1, [
        "Date", "Available Withdraw ($)", "After Fee (×0.90) ($)",
        "Pending ($)", "In Review ($)", "Work In Progress ($)",
        "Withdrawn ($)", "Connects", "Upwork Plus",
    ])
    for ri, s in enumerate(detail["snapshots"], 2):
        fill = ALT_FILL if ri % 2 == 0 else None
        for ci, v in enumerate([
            str(s["date"]), s["availableWithdraw"], s["availableWithdrawAfterFee"],
            s["pending"], s["inReview"], s["workInProgress"],
            s["withdrawn"], s["connects"], s["upworkPlus"],
        ], 1):
            cell = ws1.cell(row=ri, column=ci, value=v)
            if fill:
                cell.fill = fill
    _autofit(ws1)

    # Sheet 2 — Orders
    ws2 = wb.create_sheet("Orders")
    _header(ws2, ["Date", "Client Name", "Order ID", "Amount ($)", "After Upwork ($)"])
    for ri, o in enumerate(detail["orders"], 2):
        fill = ALT_FILL if ri % 2 == 0 else None
        for ci, v in enumerate([
            str(o["date"]), o["clientName"], o["orderId"],
            o["amount"], o["afterUpwork"],
        ], 1):
            cell = ws2.cell(row=ri, column=ci, value=v)
            if fill:
                cell.fill = fill
    _autofit(ws2)

    buf      = io.BytesIO()
    wb.save(buf)
    tag      = f"{start}_{end}" if start else "all"
    filename = f"upwork_{p_name.replace(' ', '_')}_{tag}.xlsx"
    return buf.getvalue(), filename