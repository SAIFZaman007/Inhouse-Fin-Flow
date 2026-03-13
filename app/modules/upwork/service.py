"""
app/modules/upwork/service.py
════════════════════════════════════════════════════════════════════════════════
v5 — Enterprise Edition

Changes vs v4
─────────────
_resolve_profile_by_name  NEW — case-insensitive profile lookup by name.
_snapshot_to_dict         Now accepts optional ``profile_name`` kwarg and
                          includes it as ``profileName`` in every dict.
create_snapshot           Resolves profile via ``data.profile_name`` (not id).
add_order                 Resolves profile via ``data.profile_name`` (not id).
get_profile_snapshots     Passes profile name; supports PageParams.
get_profile_detail        Passes profile name; supports PageParams.
list_profiles_summary     Passes profile name; supports PageParams.

Fee constant
────────────
_UPWORK_FEE = 0.10  (10 % service fee — single source of truth)
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import io
import logging
import math
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from fastapi import HTTPException
from prisma import Prisma

from app.shared.filters import DateRangeFilter, to_dt_start, to_dt_end
from app.shared.pagination import PageParams
from .schema import (
    UpworkOrderCreate,
    UpworkProfileCreate,
    UpworkSnapshotCreate,
)

logger = logging.getLogger(__name__)

# ── Fee constants ─────────────────────────────────────────────────────────────
_UPWORK_FEE        = Decimal("0.10")
_UPWORK_NET_FACTOR = Decimal("1") - _UPWORK_FEE   # 0.90
_ZERO              = Decimal("0")


# ── Private helpers ───────────────────────────────────────────────────────────

def _compute_after_upwork(amount: Decimal) -> Decimal:
    """Net amount after Upwork's 10 % service fee, rounded to 2 dp."""
    return (amount * _UPWORK_NET_FACTOR).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _d(v: Any) -> Decimal:
    """Safely coerce Prisma Decimal / None → Python Decimal."""
    return _ZERO if v is None else Decimal(str(v))


def _snapshot_to_dict(entry: Any, *, profile_name: Optional[str] = None) -> dict:
    """
    Convert an UpworkEntry ORM object → serialisable dict.

    ``profile_name`` is injected by every caller that holds the profile object,
    so each snapshot row carries ``profileName`` — no second lookup needed.
    """
    avail = _d(entry.availableWithdraw)
    row: dict = {
        "id":                        entry.id,
        "profileId":                 entry.profileId,
        "date":                      entry.date.date() if isinstance(entry.date, datetime) else entry.date,
        "availableWithdraw":         float(avail),
        "availableWithdrawAfterFee": float(avail * _UPWORK_NET_FACTOR),
        "pending":                   float(_d(entry.pending)),
        "inReview":                  float(_d(entry.inReview)),
        "workInProgress":            float(_d(entry.workInProgress)),
        "withdrawn":                 float(_d(entry.withdrawn)),
        "connects":                  entry.connects,
        "upworkPlus":                entry.upworkPlus,
        "createdAt":                 entry.createdAt,
    }
    if profile_name is not None:
        row["profileName"] = profile_name
    return row


def _order_to_dict(order: Any) -> dict:
    return {
        "id":          order.id,
        "date":        order.date.date() if isinstance(order.date, datetime) else order.date,
        "clientName":  order.clientName,
        "orderId":     order.orderId,
        "amount":      float(_d(order.amount)),
        "afterUpwork": float(_d(order.afterUpwork)),
        "createdAt":   order.createdAt,
    }


def _date_filter_for_entry(d: date) -> dict:
    """Single-day gte/lte — avoids bare datetime.date serialisation bug."""
    return {"gte": to_dt_start(d), "lte": to_dt_end(d)}


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
    """
    Return the active UpworkProfile whose name matches ``profile_name``
    (case-insensitive).  Raises HTTP 404 if not found.
    """
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


# ── Profile CRUD ──────────────────────────────────────────────────────────────

async def create_profile(db: Prisma, data: UpworkProfileCreate) -> dict:
    """Create an Upwork profile, optionally seeding an initial snapshot."""
    existing = await db.upworkprofile.find_unique(where={"profileName": data.profileName})
    if existing:
        raise HTTPException(status_code=409, detail="Profile name already exists.")

    profile = await db.upworkprofile.create(data={"profileName": data.profileName})

    snapshot_dict: Optional[dict] = None
    if data.available_withdraw is not None:
        snap_date = data.snapshot_date or date.today()
        entry = await db.upworkentry.create(
            data={
                "profileId":         profile.id,
                "date":              datetime.combine(snap_date, time.min),
                "availableWithdraw": data.available_withdraw,
                "pending":           data.pending,
                "inReview":          data.in_review,
                "workInProgress":    data.work_in_progress,
                "withdrawn":         data.withdrawn,
                "connects":          data.connects,
                "upworkPlus":        data.upwork_plus,
            }
        )
        snapshot_dict = _snapshot_to_dict(entry, profile_name=profile.profileName)

    return {
        "id":              profile.id,
        "profileName":     profile.profileName,
        "isActive":        profile.isActive,
        "initialSnapshot": snapshot_dict,
    }


async def deactivate_profile(db: Prisma, profile_id: str) -> None:
    profile = await db.upworkprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Upwork profile not found.")
    await db.upworkprofile.update(where={"id": profile_id}, data={"isActive": False})


# ── List with combined totals  GET /profiles ──────────────────────────────────

async def list_profiles_summary(
    db: Prisma,
    filters: DateRangeFilter,
    name: Optional[str] = None,
    pagination: Optional[PageParams] = None,
) -> dict:
    """Combined cross-profile totals + paginated per-profile breakdown."""
    date_f = filters.to_prisma_filter()

    profile_where: dict = {"isActive": True}
    if name:
        profile_where["profileName"] = {"contains": name, "mode": "insensitive"}

    total_profiles = await db.upworkprofile.count(where=profile_where)

    find_kwargs: dict = dict(
        where=profile_where,
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
        find_kwargs["skip"] = pagination.skip
        find_kwargs["take"] = pagination.take

    profiles = await db.upworkprofile.find_many(**find_kwargs)

    # ── Aggregate accumulators ────────────────────────────────────────────────
    t_avail     = _ZERO
    t_after_fee = _ZERO
    t_pending   = _ZERO
    t_review    = _ZERO
    t_wip       = _ZERO
    t_withdrawn = _ZERO
    t_connects  = 0
    t_revenue   = _ZERO

    summaries = []
    for p in profiles:
        latest   = p.entries[0] if p.entries else None
        avail    = _d(latest.availableWithdraw) if latest else _ZERO
        pending  = _d(latest.pending)           if latest else _ZERO
        review   = _d(latest.inReview)          if latest else _ZERO
        wip      = _d(latest.workInProgress)    if latest else _ZERO
        withdrawn = _d(latest.withdrawn)        if latest else _ZERO
        connects = latest.connects              if latest else 0
        revenue  = sum((_d(o.afterUpwork) for o in p.orders), _ZERO)

        t_avail     += avail
        t_after_fee += avail * _UPWORK_NET_FACTOR
        t_pending   += pending
        t_review    += review
        t_wip       += wip
        t_withdrawn += withdrawn
        t_connects  += connects
        t_revenue   += revenue

        summaries.append({
            "id":             p.id,
            "profileName":    p.profileName,
            "isActive":       p.isActive,
            "latestSnapshot": _snapshot_to_dict(latest, profile_name=p.profileName) if latest else None,
            "periodTotals": {
                "availableWithdraw":         float(avail),
                "availableWithdrawAfterFee": float(avail * _UPWORK_NET_FACTOR),
                "pending":                   float(pending),
                "inReview":                  float(review),
                "workInProgress":            float(wip),
                "withdrawn":                 float(withdrawn),
                "connects":                  connects,
                "revenueInPeriod":           float(revenue),
            },
            "snapshotCount":   len(p.entries),
            "orderCount":      len(p.orders),
            "revenueInPeriod": float(revenue),
            "orders":          [_order_to_dict(o) for o in p.orders],
        })

    return {
        "filter": filters.meta(),
        "totals": {
            "totalAvailableWithdraw":         float(t_avail),
            "totalAvailableWithdrawAfterFee": float(t_after_fee),
            "totalPending":                   float(t_pending),
            "totalInReview":                  float(t_review),
            "totalWorkInProgress":            float(t_wip),
            "totalWithdrawn":                 float(t_withdrawn),
            "totalConnects":                  t_connects,
            "totalRevenueInPeriod":           float(t_revenue),
            "activeProfileCount":             total_profiles,
        },
        "pagination": _pagination_meta(pagination, total_profiles),
        "profiles":   summaries,
    }


# ── Single-profile detail  GET /profiles/{id} ─────────────────────────────────

async def get_profile_detail(
    db: Prisma,
    profile_id: str,
    filters: DateRangeFilter,
    pagination: Optional[PageParams] = None,
) -> dict:
    """Full drill-down for one profile — paginated snapshots + orders."""
    profile = await db.upworkprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Upwork profile not found.")

    date_f      = filters.to_prisma_filter()
    snap_where  = {"profileId": profile_id, **( {"date": date_f} if date_f else {} )}
    order_where = {"profileId": profile_id, **( {"date": date_f} if date_f else {} )}

    total_snaps  = await db.upworkentry.count(where=snap_where)
    total_orders = await db.upworkorder.count(where=order_where)

    snap_kw:  dict = dict(where=snap_where,  order={"date": "desc"})
    order_kw: dict = dict(where=order_where, order={"date": "desc"})
    if pagination:
        snap_kw["skip"]  = pagination.skip
        snap_kw["take"]  = pagination.take
        order_kw["skip"] = pagination.skip
        order_kw["take"] = pagination.take

    entries = await db.upworkentry.find_many(**snap_kw)
    orders  = await db.upworkorder.find_many(**order_kw)

    head = await db.upworkentry.find_first(where=snap_where, order={"date": "desc"}) \
           if total_snaps > 0 else None

    avail   = _d(head.availableWithdraw) if head else _ZERO
    revenue = sum((_d(o.afterUpwork) for o in orders), _ZERO)

    return {
        "filter":  filters.meta(),
        "profile": {"id": profile.id, "profileName": profile.profileName, "isActive": profile.isActive},
        "periodTotals": {
            "availableWithdraw":         float(avail),
            "availableWithdrawAfterFee": float(avail * _UPWORK_NET_FACTOR),
            "pending":                   float(_d(head.pending)        if head else _ZERO),
            "inReview":                  float(_d(head.inReview)       if head else _ZERO),
            "workInProgress":            float(_d(head.workInProgress) if head else _ZERO),
            "withdrawn":                 float(_d(head.withdrawn)      if head else _ZERO),
            "connects":                  head.connects                  if head else 0,
            "revenueInPeriod":           float(revenue),
            "snapshotCount":             total_snaps,
            "orderCount":                total_orders,
        },
        "pagination": {
            **_pagination_meta(pagination, total_snaps),
            "totalOrders":     total_orders,
            "totalOrderPages": math.ceil(total_orders / (pagination.page_size if pagination else total_orders or 1))
                               if total_orders > 0 else 1,
        },
        "snapshots": [_snapshot_to_dict(e, profile_name=profile.profileName) for e in entries],
        "orders":    [_order_to_dict(o) for o in orders],
    }


# ── Snapshot CRUD ─────────────────────────────────────────────────────────────

async def create_snapshot(db: Prisma, data: UpworkSnapshotCreate) -> dict:
    """
    Upsert a daily snapshot.
    Resolves profile by ``data.profile_name`` — HR never handles UUIDs.
    """
    profile    = await _resolve_profile_by_name(db, data.profile_name)
    entry_data = {
        "availableWithdraw": data.available_withdraw,
        "pending":           data.pending,
        "inReview":          data.in_review,
        "workInProgress":    data.work_in_progress,
        "withdrawn":         data.withdrawn,
        "connects":          data.connects,
        "upworkPlus":        data.upwork_plus,
    }

    existing = await db.upworkentry.find_first(
        where={"profileId": profile.id, "date": _date_filter_for_entry(data.date)}
    )
    if existing:
        entry = await db.upworkentry.update(where={"id": existing.id}, data=entry_data)
    else:
        entry = await db.upworkentry.create(
            data={"profileId": profile.id, "date": datetime.combine(data.date, time.min), **entry_data}
        )
    return _snapshot_to_dict(entry, profile_name=profile.profileName)


async def get_profile_snapshots(
    db: Prisma,
    profile_id: str,
    date_filter: dict,
    pagination: Optional[PageParams] = None,
) -> dict:
    """Paginated snapshots for one profile — every row includes ``profileName``."""
    profile = await db.upworkprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Upwork profile not found.")

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
        "pagination": _pagination_meta(pagination, total),
        "items":      [_snapshot_to_dict(e, profile_name=profile.profileName) for e in entries],
    }


# ── Order CRUD ────────────────────────────────────────────────────────────────

async def add_order(db: Prisma, data: UpworkOrderCreate) -> dict:
    """
    Log a new order.
    Resolves profile by ``data.profile_name``.
    ``afterUpwork`` is computed here — never from the client.
    """
    profile  = await _resolve_profile_by_name(db, data.profile_name)
    existing = await db.upworkorder.find_unique(where={"orderId": data.order_id})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Order ID '{data.order_id}' already recorded.",
        )
    order = await db.upworkorder.create(
        data={
            "profileId":   profile.id,
            "date":        datetime.combine(data.date, time.min),
            "clientName":  data.client_name,
            "orderId":     data.order_id,
            "amount":      data.amount,
            "afterUpwork": _compute_after_upwork(data.amount),
        }
    )
    return _order_to_dict(order)


async def get_profile_orders(
    db: Prisma,
    profile_id: str,
    date_filter: dict,
    pagination: Optional[PageParams] = None,
) -> dict:
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
        "pagination": _pagination_meta(pagination, total),
        "items":      [_order_to_dict(o) for o in orders],
    }


# ── Profile-level Excel export ────────────────────────────────────────────────

async def export_profile_excel(
    db: Prisma,
    profile_id: str,
    filters: DateRangeFilter,
) -> tuple[bytes, str]:
    """Two-sheet Excel: Sheet 1 = Snapshots, Sheet 2 = Orders."""
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="openpyxl not installed — cannot generate Excel export.",
        )

    detail       = await get_profile_detail(db, profile_id, filters)
    profile_name = detail["profile"]["profileName"]
    start, end   = filters.window()

    wb          = openpyxl.Workbook()
    HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
    HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
    ALT_FILL    = PatternFill("solid", fgColor="EBF3FB")

    def _header(ws, cols: list[str]) -> None:
        for c, h in enumerate(cols, 1):
            cell = ws.cell(row=1, column=c, value=h)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 20

    def _autofit(ws) -> None:
        for col in ws.columns:
            w = max((len(str(cell.value or "")) for cell in col), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(w + 4, 40)

    # Sheet 1 — Snapshots
    ws1 = wb.active
    ws1.title = "Snapshots"
    _header(ws1, [
        "Date", "Available Withdraw ($)", "After Fee ($)",
        "Pending ($)", "In Review ($)", "Work In Progress ($)",
        "Withdrawn ($)", "Connects", "Upwork Plus",
    ])
    for ri, s in enumerate(detail["snapshots"], 2):
        fill = ALT_FILL if ri % 2 == 0 else None
        for ci, v in enumerate([
            str(s["date"]), s["availableWithdraw"], s["availableWithdrawAfterFee"],
            s["pending"], s["inReview"], s["workInProgress"],
            s["withdrawn"], s["connects"],
            "Yes" if s["upworkPlus"] else "No",
        ], 1):
            cell = ws1.cell(row=ri, column=ci, value=v)
            if fill:
                cell.fill = fill
    _autofit(ws1)

    # Sheet 2 — Orders
    ws2 = wb.create_sheet("Orders")
    _header(ws2, ["Date", "Client Name", "Order ID", "Amount ($)", "After Fee ($)"])
    for ri, o in enumerate(detail["orders"], 2):
        fill = ALT_FILL if ri % 2 == 0 else None
        for ci, v in enumerate([
            str(o["date"]), o["clientName"], o["orderId"], o["amount"], o["afterUpwork"],
        ], 1):
            cell = ws2.cell(row=ri, column=ci, value=v)
            if fill:
                cell.fill = fill
    _autofit(ws2)

    buf      = io.BytesIO()
    wb.save(buf)
    tag      = f"{start}_{end}" if start else "all"
    filename = f"upwork_{profile_name.replace(' ', '_')}_{tag}.xlsx"
    return buf.getvalue(), filename