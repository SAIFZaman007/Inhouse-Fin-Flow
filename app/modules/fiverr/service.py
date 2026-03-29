"""
app/modules/fiverr/service.py
════════════════════════════════════════════════════════════════════════════════
v2 — Enterprise Edition

Changes vs v1
─────────────
revenueInPeriod   FORMULA FIX — now computed as:
                      availableWithdraw + notCleared - withdrawn
                    matching the spec.  ``withdrawn`` is subtracted so that
                    deducted amounts are correctly removed from both
                    ``revenueInPeriod`` and the effective available balance.
                    The helper ``_revenue_from_snapshot`` encapsulates this
                    formula and is applied consistently in _entry_to_dict,
                    list_profiles_summary, get_profile_detail, create_snapshot,
                    and add_order.

withdrawn         DEDUCTION — whenever an amount is withdrawn it is subtracted
                    from ``revenueInPeriod`` via the formula above, so the net
                    platform balance always reflects funds still on the platform.

Everything else is unchanged from v1 (additive accumulation, sync on order,
20% Fiverr fee, sellerPlus OR semantics).
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
    FiverrOrderCreate,
    FiverrOrderUpdate,
    FiverrProfileCreate,
    FiverrProfileUpdate,
    FiverrSnapshotCreate,
)

logger = logging.getLogger(__name__)

_FIVERR_FEE  = Decimal("0.20")
_AFTER_RATE  = Decimal("1") - _FIVERR_FEE   # 0.80
_ZERO        = Decimal("0")

_SNAPSHOT_FIELDS = frozenset({
    "available_withdraw",
    "not_cleared",
    "active_orders",
    "active_order_amount",
    "submitted",
    "withdrawn",
    "seller_plus",
    "promotion",
})


# ── Private helpers ───────────────────────────────────────────────────────────

def _d(v: Any) -> Decimal:
    return _ZERO if v is None else Decimal(str(v))


def _after_fee(amount: Any) -> Decimal:
    return (_d(amount) * _AFTER_RATE).quantize(Decimal("0.01"))


def _revenue_from_snapshot(entry: Any) -> Decimal:
    """
    Compute revenueInPeriod from a snapshot row.

    Formula (spec):
        revenueInPeriod = availableWithdraw + notCleared - withdrawn

    ``withdrawn`` is subtracted so that deducted amounts are correctly removed
    from both revenueInPeriod and the effective available balance.
    Returns Decimal("0") for a None entry.
    """
    if entry is None:
        return _ZERO
    return (
        _d(entry.availableWithdraw)
        + _d(entry.notCleared)
        - _d(entry.withdrawn)
    )


def _entry_to_dict(entry: Any, profile_name: str) -> dict:
    """
    Serialise a FiverrEntry ORM object to a plain dict.

    ``revenueInPeriod`` = availableWithdraw + notCleared - withdrawn
    """
    aw  = _d(entry.availableWithdraw)
    rev = _revenue_from_snapshot(entry)
    return {
        "id":                entry.id,
        "profileId":         entry.profileId,
        "profileName":       profile_name,
        "date":              entry.date.date() if isinstance(entry.date, datetime) else entry.date,
        "availableWithdraw": float(aw),
        "notCleared":        float(_d(entry.notCleared)),
        "activeOrders":      entry.activeOrders,
        "activeOrderAmount": float(_d(entry.activeOrderAmount)),
        "submitted":         float(_d(entry.submitted)),
        "withdrawn":         float(_d(entry.withdrawn)),
        "revenueInPeriod":   float(rev),    # aw + notCleared - withdrawn
        "sellerPlus":        entry.sellerPlus,
        "promotion":         float(_d(entry.promotion)),
        "createdAt":         entry.createdAt,
    }


def _order_to_dict(order: Any) -> dict:
    return {
        "id":          order.id,
        "profileId":   order.profileId,
        "date":        order.date.date() if isinstance(order.date, datetime) else order.date,
        "buyerName":   order.buyerName,
        "orderId":     order.orderId,
        "amount":      float(_d(order.amount)),
        "afterFiverr": float(_d(order.afterFiverr)),
        "createdAt":   order.createdAt,
    }


def _pagination_meta(pagination: Optional[PageParams], total: int) -> dict:
    if pagination is None:
        return {"page": 1, "pageSize": total, "total": total, "totalPages": 1}
    return {
        "page":       pagination.page,
        "pageSize":   pagination.page_size,
        "total":      total,
        "totalPages": math.ceil(total / pagination.page_size) if total > 0 else 1,
    }


async def _get_profile_or_404(db: Prisma, profile_id: str):
    profile = await db.fiverrprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Fiverr profile not found.")
    return profile


async def _resolve_profile_by_name(db: Prisma, profile_name: str):
    profile = await db.fiverrprofile.find_first(
        where={
            "profileName": {"equals": profile_name, "mode": "insensitive"},
            "isActive":    True,
        }
    )
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Fiverr profile '{profile_name}' not found.",
        )
    return profile


# ── Snapshot sync helper ──────────────────────────────────────────────────────

async def _sync_snapshot_on_order(
    db: Prisma,
    profile_id: str,
    snap_dt: datetime,
    order_amount: Decimal,
) -> None:
    """
    Additively increment ``activeOrders`` (+1) and ``activeOrderAmount``
    (+order_amount) on the snapshot for ``(profile_id, snap_dt)``.

    If no snapshot row exists yet for that date it is created with:
      • availableWithdraw = 0, activeOrders = 1, activeOrderAmount = order_amount
      • all other numeric fields at zero / defaults
    """
    existing = await db.fiverrentry.find_unique(
        where={"profileId_date": {"profileId": profile_id, "date": snap_dt}}
    )

    if existing is None:
        await db.fiverrentry.create(
            data={
                "profileId":         profile_id,
                "date":              snap_dt,
                "availableWithdraw": _ZERO,
                "notCleared":        _ZERO,
                "activeOrders":      1,
                "activeOrderAmount": order_amount,
                "submitted":         _ZERO,
                "withdrawn":         _ZERO,
                "sellerPlus":        False,
                "promotion":         _ZERO,
            }
        )
    else:
        await db.fiverrentry.update(
            where={"profileId_date": {"profileId": profile_id, "date": snap_dt}},
            data={
                "activeOrders":      existing.activeOrders + 1,
                "activeOrderAmount": _d(existing.activeOrderAmount) + order_amount,
            },
        )


# ── Profile CRUD ──────────────────────────────────────────────────────────────

async def create_profile(db: Prisma, data: FiverrProfileCreate) -> dict:
    existing = await db.fiverrprofile.find_unique(
        where={"profileName": data.profileName}
    )
    if existing:
        raise HTTPException(status_code=409, detail="Profile name already exists.")

    profile = await db.fiverrprofile.create(
        data={"profileName": data.profileName}
    )

    snapshot: Optional[dict] = None
    if data.available_withdraw is not None:
        snap_date = data.snapshot_date or date.today()
        snap_dt   = datetime.combine(snap_date, time.min)
        entry = await db.fiverrentry.upsert(
            where={"profileId_date": {"profileId": profile.id, "date": snap_dt}},
            data={
                "create": {
                    "profileId":         profile.id,
                    "date":              snap_dt,
                    "availableWithdraw": data.available_withdraw,
                    "notCleared":        data.not_cleared        or _ZERO,
                    "activeOrders":      data.active_orders      or 0,
                    "activeOrderAmount": data.active_order_amount or _ZERO,
                    "submitted":         data.submitted           or _ZERO,
                    "withdrawn":         data.withdrawn           or _ZERO,
                    "sellerPlus":        data.seller_plus,
                    "promotion":         data.promotion           or _ZERO,
                },
                "update": {
                    "availableWithdraw": data.available_withdraw,
                    "notCleared":        data.not_cleared        or _ZERO,
                    "activeOrders":      data.active_orders      or 0,
                    "activeOrderAmount": data.active_order_amount or _ZERO,
                    "submitted":         data.submitted           or _ZERO,
                    "withdrawn":         data.withdrawn           or _ZERO,
                    "sellerPlus":        data.seller_plus,
                    "promotion":         data.promotion           or _ZERO,
                },
            },
        )
        snapshot = _entry_to_dict(entry, profile.profileName)

    return {
        "id":              profile.id,
        "profileName":     profile.profileName,
        "isActive":        profile.isActive,
        "initialSnapshot": snapshot,
    }


async def update_profile(
    db: Prisma,
    profile_id: str,
    data: FiverrProfileUpdate,
) -> dict:
    profile = await _get_profile_or_404(db, profile_id)

    profile_patch: dict = {}

    if data.profileName is not None and data.profileName != profile.profileName:
        conflict = await db.fiverrprofile.find_first(
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
        profile_patch["profileName"] = data.profileName

    if data.isActive is not None:
        profile_patch["isActive"] = data.isActive

    if profile_patch:
        profile = await db.fiverrprofile.update(
            where={"id": profile_id},
            data=profile_patch,
        )

    sent            = data.model_fields_set
    snapshot_fields = sent & _SNAPSHOT_FIELDS
    upserted_snapshot: Optional[dict] = None

    if snapshot_fields:
        snap_date = data.snapshot_date or date.today()
        snap_dt   = datetime.combine(snap_date, time.min)

        existing_entry = await db.fiverrentry.find_unique(
            where={"profileId_date": {"profileId": profile_id, "date": snap_dt}}
        )

        def _pick(field: str, existing_attr: str, default: Any) -> Any:
            if field in sent:
                return getattr(data, field)
            if existing_entry is not None:
                return getattr(existing_entry, existing_attr)
            return default

        aw                  = _pick("available_withdraw",  "availableWithdraw",  _ZERO)
        not_cleared         = _pick("not_cleared",         "notCleared",         _ZERO)
        active_orders       = _pick("active_orders",       "activeOrders",       0)
        active_order_amount = _pick("active_order_amount", "activeOrderAmount",  _ZERO)
        submitted           = _pick("submitted",           "submitted",          _ZERO)
        withdrawn           = _pick("withdrawn",           "withdrawn",          _ZERO)
        seller_plus         = _pick("seller_plus",         "sellerPlus",         False)
        promotion           = _pick("promotion",           "promotion",          _ZERO)

        entry_data = {
            "availableWithdraw":  aw,
            "notCleared":         not_cleared,
            "activeOrders":       active_orders,
            "activeOrderAmount":  active_order_amount,
            "submitted":          submitted,
            "withdrawn":          withdrawn,
            "sellerPlus":         seller_plus,
            "promotion":          promotion,
        }

        entry = await db.fiverrentry.upsert(
            where={"profileId_date": {"profileId": profile_id, "date": snap_dt}},
            data={
                "create": {"profileId": profile_id, "date": snap_dt, **entry_data},
                "update": entry_data,
            },
        )
        upserted_snapshot = _entry_to_dict(entry, profile.profileName)

    return {
        "id":               profile.id,
        "profileName":      profile.profileName,
        "isActive":         profile.isActive,
        "snapshotUpserted": upserted_snapshot,
    }


async def deactivate_profile(db: Prisma, profile_id: str) -> None:
    profile = await db.fiverrprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Fiverr profile not found.")
    await db.fiverrprofile.update(
        where={"id": profile_id}, data={"isActive": False}
    )


# ── Snapshot CRUD ─────────────────────────────────────────────────────────────

async def create_snapshot(db: Prisma, data: FiverrSnapshotCreate) -> dict:
    """
    POST /snapshots — additive daily snapshot (v2).

    • First submission  → INSERT with incoming values.
    • Repeat submission → ADD incoming numeric values to stored values.
                          sellerPlus uses OR semantics (sticky True).

    revenueInPeriod = availableWithdraw + notCleared - withdrawn
    ``withdrawn`` deducted so the net balance is always correct.
    """
    profile = await _resolve_profile_by_name(db, data.profile_name)
    snap_dt = datetime.combine(data.date, time.min)

    existing = await db.fiverrentry.find_unique(
        where={"profileId_date": {"profileId": profile.id, "date": snap_dt}}
    )

    if existing is None:
        entry = await db.fiverrentry.create(
            data={
                "profileId":         profile.id,
                "date":              snap_dt,
                "availableWithdraw": data.available_withdraw,
                "notCleared":        data.not_cleared,
                "activeOrders":      data.active_orders,
                "activeOrderAmount": data.active_order_amount,
                "submitted":         data.submitted,
                "withdrawn":         data.withdrawn,
                "sellerPlus":        data.seller_plus,
                "promotion":         data.promotion,
            }
        )
    else:
        new_aw    = _d(existing.availableWithdraw)  + _d(data.available_withdraw)
        new_nc    = _d(existing.notCleared)          + _d(data.not_cleared)
        new_ao    = existing.activeOrders            + data.active_orders
        new_aoa   = _d(existing.activeOrderAmount)   + _d(data.active_order_amount)
        new_sub   = _d(existing.submitted)           + _d(data.submitted)
        new_wdr   = _d(existing.withdrawn)           + _d(data.withdrawn)
        new_plus  = existing.sellerPlus              or data.seller_plus
        new_promo = _d(existing.promotion)           + _d(data.promotion)

        entry = await db.fiverrentry.update(
            where={"profileId_date": {"profileId": profile.id, "date": snap_dt}},
            data={
                "availableWithdraw": new_aw,
                "notCleared":        new_nc,
                "activeOrders":      new_ao,
                "activeOrderAmount": new_aoa,
                "submitted":         new_sub,
                "withdrawn":         new_wdr,
                "sellerPlus":        new_plus,
                "promotion":         new_promo,
            },
        )

    all_orders         = await db.fiverrorder.find_many(where={"profileId": profile.id})
    total_revenue      = sum((_d(o.afterFiverr) for o in all_orders), _ZERO)
    total_order_amount = sum((_d(o.amount)       for o in all_orders), _ZERO)

    rev           = _revenue_from_snapshot(entry)
    updated_aw    = _d(entry.availableWithdraw)
    snapshot_dict = _entry_to_dict(entry, profile.profileName)

    return {
        **snapshot_dict,
        "syncedTotals": {
            "revenueAllTime":     float(total_revenue),
            "orderAmountAllTime": float(total_order_amount),
            "latestSnapshot": {
                "availableWithdraw":  float(updated_aw),
                "notCleared":         float(_d(entry.notCleared)),
                "activeOrders":       entry.activeOrders,
                "activeOrderAmount":  float(_d(entry.activeOrderAmount)),
                "submitted":          float(_d(entry.submitted)),
                "withdrawn":          float(_d(entry.withdrawn)),
                "revenueInPeriod":    float(rev),    # aw + notCleared - withdrawn
                "promotion":          float(_d(entry.promotion)),
            },
        },
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

    total   = await db.fiverrentry.count(where=where)
    find_kw = dict(where=where, order={"date": "desc"})
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    entries = await db.fiverrentry.find_many(**find_kw)
    return {
        "profileId":   profile_id,
        "profileName": profile.profileName,
        "pagination":  _pagination_meta(pagination, total),
        "snapshots":   [_entry_to_dict(e, profile.profileName) for e in entries],
    }


# ── Order CRUD ────────────────────────────────────────────────────────────────

async def add_order(db: Prisma, data: FiverrOrderCreate) -> dict:
    """
    POST /orders — log a new Fiverr order and sync the daily snapshot (v2).

    1. Resolve active profile by name (case-insensitive).
    2. Guard duplicate orderId (409).
    3. Persist FiverrOrder; afterFiverr = amount × 0.80 (server-computed).
    4. Sync snapshot: activeOrders += 1, activeOrderAmount += amount.
    5. Return order + snapshotSync + syncedTotals.
    """
    profile = await _resolve_profile_by_name(db, data.profile_name)

    existing = await db.fiverrorder.find_unique(where={"orderId": data.order_id})
    if existing:
        raise HTTPException(status_code=409, detail="Order ID already exists.")

    snap_dt      = datetime.combine(data.date, time.min)
    order_amount = _d(data.amount)

    order = await db.fiverrorder.create(
        data={
            "profileId":   profile.id,
            "date":        snap_dt,
            "buyerName":   data.buyer_name,
            "orderId":     data.order_id,
            "amount":      order_amount,
            "afterFiverr": _after_fee(order_amount),
        }
    )

    await _sync_snapshot_on_order(db, profile.id, snap_dt, order_amount)

    updated_entry = await db.fiverrentry.find_unique(
        where={"profileId_date": {"profileId": profile.id, "date": snap_dt}}
    )

    all_orders         = await db.fiverrorder.find_many(where={"profileId": profile.id})
    total_revenue      = sum((_d(o.afterFiverr) for o in all_orders), _ZERO)
    total_order_amount = sum((_d(o.amount)       for o in all_orders), _ZERO)

    rev = _revenue_from_snapshot(updated_entry) if updated_entry else _ZERO

    return {
        **_order_to_dict(order),
        "snapshotSync": {
            "date":              str(data.date),
            "activeOrders":      updated_entry.activeOrders                   if updated_entry else 1,
            "activeOrderAmount": float(_d(updated_entry.activeOrderAmount))   if updated_entry else float(order_amount),
            "revenueInPeriod":   float(rev),
            "latestSnapshot": {
                "availableWithdraw":  float(_d(updated_entry.availableWithdraw))  if updated_entry else 0.0,
                "notCleared":         float(_d(updated_entry.notCleared))          if updated_entry else 0.0,
                "activeOrders":       updated_entry.activeOrders                   if updated_entry else 1,
                "activeOrderAmount":  float(_d(updated_entry.activeOrderAmount))   if updated_entry else float(order_amount),
                "submitted":          float(_d(updated_entry.submitted))            if updated_entry else 0.0,
                "withdrawn":          float(_d(updated_entry.withdrawn))            if updated_entry else 0.0,
                "revenueInPeriod":    float(rev),
                "promotion":          float(_d(updated_entry.promotion))            if updated_entry else 0.0,
            } if updated_entry else None,
        },
        "syncedTotals": {
            "revenueAllTime":     float(total_revenue),
            "orderAmountAllTime": float(total_order_amount),
        },
    }


async def update_order(db: Prisma, order_id: str, data: FiverrOrderUpdate) -> dict:
    order = await db.fiverrorder.find_unique(where={"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Fiverr order not found.")

    patch: dict = {}
    sent = data.model_fields_set

    if "date" in sent and data.date is not None:
        patch["date"] = datetime.combine(data.date, time.min)

    if data.buyer_name is not None:
        patch["buyerName"] = data.buyer_name

    if data.order_id is not None and data.order_id != order.orderId:
        conflict = await db.fiverrorder.find_unique(where={"orderId": data.order_id})
        if conflict:
            raise HTTPException(status_code=409, detail=f"Order ID '{data.order_id}' is already taken.")
        patch["orderId"] = data.order_id

    if data.amount is not None:
        patch["amount"]      = data.amount
        patch["afterFiverr"] = _after_fee(data.amount)

    if not patch:
        return _order_to_dict(order)

    updated = await db.fiverrorder.update(where={"id": order_id}, data=patch)
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

    total   = await db.fiverrorder.count(where=where)
    find_kw = dict(where=where, order={"date": "desc"})
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    orders = await db.fiverrorder.find_many(**find_kw)
    return {
        "profileId":   profile_id,
        "profileName": profile.profileName,
        "pagination":  _pagination_meta(pagination, total),
        "orders":      [_order_to_dict(o) for o in orders],
    }


# ── List / detail ─────────────────────────────────────────────────────────────

async def list_profiles_summary(
    db: Prisma,
    filters: DateRangeFilter,
    name: Optional[str] = None,
    pagination: Optional[PageParams] = None,
) -> dict:
    """
    GET /profiles — combined totals + paginated per-profile breakdown (v2).

    revenueInPeriod = availableWithdraw + notCleared - withdrawn
    ``withdrawn`` subtracted so deducted funds reduce the net balance.
    """
    date_f       = filters.to_prisma_filter()
    date_f_where = {"date": date_f} if date_f else {}

    where: dict = {"isActive": True}
    if name:
        where["profileName"] = {"contains": name, "mode": "insensitive"}

    total_profiles = await db.fiverrprofile.count(where=where)

    find_kw: dict = dict(
        where=where,
        include={
            "entries": {"where": date_f_where, "order_by": {"date": "desc"}},
            "orders":  {"where": date_f_where, "order_by": {"date": "desc"}},
        },
    )
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    profiles = await db.fiverrprofile.find_many(**find_kw)

    t_avail = t_nc = t_aoa = t_sub = t_wdr = t_promo = _ZERO
    t_ao    = 0
    t_revenue = t_order_rev = t_order_amount = _ZERO

    summaries = []
    for p in profiles:
        latest = p.entries[0] if p.entries else None
        aw     = _d(latest.availableWithdraw) if latest else _ZERO
        wdrawn = _d(latest.withdrawn)          if latest else _ZERO

        t_avail  += aw
        t_nc     += _d(latest.notCleared)       if latest else _ZERO
        t_ao     += latest.activeOrders          if latest else 0
        t_aoa    += _d(latest.activeOrderAmount) if latest else _ZERO
        t_sub    += _d(latest.submitted)         if latest else _ZERO
        t_wdr    += wdrawn
        t_promo  += _d(latest.promotion)         if latest else _ZERO

        period_revenue      = _revenue_from_snapshot(latest)
        period_order_rev    = sum((_d(o.afterFiverr) for o in p.orders), _ZERO)
        period_order_amount = sum((_d(o.amount)       for o in p.orders), _ZERO)

        t_revenue      += period_revenue
        t_order_rev    += period_order_rev
        t_order_amount += period_order_amount

        period_totals = {
            "availableWithdraw":    float(aw),
            "notCleared":           float(_d(latest.notCleared)       if latest else _ZERO),
            "activeOrders":         latest.activeOrders                if latest else 0,
            "activeOrderAmount":    float(_d(latest.activeOrderAmount) if latest else _ZERO),
            "submitted":            float(_d(latest.submitted)         if latest else _ZERO),
            "withdrawn":            float(wdrawn),
            "promotion":            float(_d(latest.promotion)         if latest else _ZERO),
            "revenueInPeriod":      float(period_revenue),          # aw + notCleared - withdrawn
            "orderRevenueInPeriod": float(period_order_rev),        # Σ afterFiverr
            "totalOrderAmount":     float(period_order_amount),     # Σ order.amount
        }

        summaries.append({
            "id":              p.id,
            "profileName":     p.profileName,
            "isActive":        p.isActive,
            "latestSnapshot":  _entry_to_dict(latest, p.profileName) if latest else None,
            "periodTotals":    period_totals,
            "snapshotCount":   len(p.entries),
            "orderCount":      len(p.orders),
            "revenueInPeriod": float(period_revenue),
            "orders":          [_order_to_dict(o) for o in p.orders],
        })

    return {
        "filter": filters.meta(),
        "totals": {
            "totalAvailableWithdraw":  float(t_avail),
            "totalNotCleared":         float(t_nc),
            "totalActiveOrders":       t_ao,
            "totalActiveOrderAmount":  float(t_aoa),
            "totalSubmitted":          float(t_sub),
            "totalWithdrawn":          float(t_wdr),
            "totalPromotion":          float(t_promo),
            "totalRevenueInPeriod":    float(t_revenue),    # Σ (aw + notCleared - withdrawn)
            "totalOrderRevenue":       float(t_order_rev),  # Σ afterFiverr
            "totalOrderAmount":        float(t_order_amount),
            "activeProfileCount":      total_profiles,
        },
        "pagination": _pagination_meta(pagination, total_profiles),
        "profiles":   summaries,
    }


async def get_profile_detail(
    db: Prisma,
    profile_id: str,
    filters: DateRangeFilter,
    pagination: Optional[PageParams] = None,
    name: Optional[str] = None,
) -> dict:
    """
    GET /profiles/{id} — full detail view for a single Fiverr profile (v2).

    revenueInPeriod = availableWithdraw + notCleared - withdrawn
    """
    profile = await _get_profile_or_404(db, profile_id)

    if name and name.lower() not in profile.profileName.lower():
        raise HTTPException(
            status_code=404,
            detail=f"Fiverr profile not found matching name '{name}'.",
        )

    date_f = filters.to_prisma_filter()

    snap_where:  dict = {"profileId": profile_id}
    order_where: dict = {"profileId": profile_id}
    if date_f:
        snap_where["date"]  = date_f
        order_where["date"] = date_f

    snap_total  = await db.fiverrentry.count(where=snap_where)
    order_total = await db.fiverrorder.count(where=order_where)

    snap_kw: dict  = dict(where=snap_where,  order={"date": "desc"})
    order_kw: dict = dict(where=order_where, order={"date": "desc"})
    if pagination:
        snap_kw["skip"]  = order_kw["skip"] = pagination.skip
        snap_kw["take"]  = order_kw["take"] = pagination.take

    entries = await db.fiverrentry.find_many(**snap_kw)
    orders  = await db.fiverrorder.find_many(**order_kw)

    latest       = entries[0] if entries else None
    aw           = _d(latest.availableWithdraw) if latest else _ZERO
    revenue      = _revenue_from_snapshot(latest)
    order_rev    = sum((_d(o.afterFiverr) for o in orders), _ZERO)
    order_amount = sum((_d(o.amount)       for o in orders), _ZERO)

    return {
        "filter": filters.meta(),
        "profile": {
            "id":          profile.id,
            "profileName": profile.profileName,
            "isActive":    profile.isActive,
        },
        "periodTotals": {
            "availableWithdraw":    float(aw),
            "notCleared":           float(_d(latest.notCleared)       if latest else _ZERO),
            "activeOrders":         latest.activeOrders                if latest else 0,
            "activeOrderAmount":    float(_d(latest.activeOrderAmount) if latest else _ZERO),
            "submitted":            float(_d(latest.submitted)         if latest else _ZERO),
            "withdrawn":            float(_d(latest.withdrawn)         if latest else _ZERO),
            "promotion":            float(_d(latest.promotion)         if latest else _ZERO),
            "revenueInPeriod":      float(revenue),     # aw + notCleared - withdrawn
            "orderRevenueInPeriod": float(order_rev),   # Σ afterFiverr
            "totalOrderAmount":     float(order_amount),
            "snapshotCount":        snap_total,
            "orderCount":           order_total,
        },
        "pagination": _pagination_meta(pagination, max(snap_total, order_total)),
        "snapshots":  [_entry_to_dict(e, profile.profileName) for e in entries],
        "orders":     [_order_to_dict(o) for o in orders],
    }


# ── Excel export ──────────────────────────────────────────────────────────────

async def export_profile_excel(
    db: Prisma,
    profile_id: str,
    filters: DateRangeFilter,
) -> tuple[bytes, str]:
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
    pname    = detail["profile"]["profileName"]
    start, end = filters.window()

    wb          = openpyxl.Workbook()
    HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
    HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
    ALT_FILL    = PatternFill("solid", fgColor="EBF3FB")

    def _header(ws, cols):
        for c, h in enumerate(cols, 1):
            cell = ws.cell(row=1, column=c, value=h)
            cell.font      = HEADER_FONT
            cell.fill      = HEADER_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 20

    def _autofit(ws):
        for col in ws.columns:
            w = max((len(str(cell.value or "")) for cell in col), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(w + 4, 40)

    ws1 = wb.active
    ws1.title = "Snapshots"
    _header(ws1, [
        "Date", "Available Withdraw ($)", "Not Cleared ($)",
        "Active Orders", "Active Order Amount ($)",
        "Submitted ($)", "Withdrawn ($)", "Revenue in Period ($)",
        "Seller Plus", "Promotion ($)",
    ])
    for ri, s in enumerate(detail["snapshots"], 2):
        fill = ALT_FILL if ri % 2 == 0 else None
        for ci, v in enumerate([
            str(s["date"]),
            s["availableWithdraw"], s["notCleared"],
            s["activeOrders"], s["activeOrderAmount"],
            s["submitted"], s["withdrawn"], s["revenueInPeriod"],
            s["sellerPlus"], s["promotion"],
        ], 1):
            cell = ws1.cell(row=ri, column=ci, value=v)
            if fill:
                cell.fill = fill
    _autofit(ws1)

    ws2 = wb.create_sheet("Orders")
    _header(ws2, ["Date", "Buyer", "Order ID", "Amount ($)", "After Fiverr ($)"])
    for ri, o in enumerate(detail["orders"], 2):
        fill = ALT_FILL if ri % 2 == 0 else None
        for ci, v in enumerate([
            str(o["date"]), o["buyerName"], o["orderId"],
            o["amount"], o["afterFiverr"],
        ], 1):
            cell = ws2.cell(row=ri, column=ci, value=v)
            if fill:
                cell.fill = fill
    _autofit(ws2)

    buf      = io.BytesIO()
    wb.save(buf)
    tag      = f"{start}_{end}" if start else "all"
    filename = f"fiverr_{pname.replace(' ', '_')}_{tag}.xlsx"
    return buf.getvalue(), filename