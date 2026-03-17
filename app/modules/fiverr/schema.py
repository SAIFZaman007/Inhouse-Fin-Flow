"""
app/modules/fiverr/schema.py
════════════════════════════════════════════════════════════════════════════════
v6 — Enterprise Edition

Changes vs v5
─────────────
FiverrProfileUpdate   NEW — PATCH /profiles/{id}  (all fields optional)
FiverrOrderUpdate     NEW — PATCH /orders/{id}     (all fields optional;
                            afterFiverr re-computed server-side if amount changes)

Everything else is unchanged from v5.
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Fee constant (mirrors service.py — keep in sync) ─────────────────────────
_FIVERR_FEE = Decimal("0.20")


# ─────────────────────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────────────────────

class FiverrProfileCreate(BaseModel):
    """
    Create a new Fiverr profile.

    If ``available_withdraw`` is supplied, an initial snapshot is recorded
    for ``snapshot_date`` (defaults to today), eliminating the need for a
    separate POST /snapshots call.
    """
    profileName: str = Field(..., min_length=1, max_length=100)

    # Optional initial-snapshot fields ───────────────────────────────────────
    snapshot_date:       Optional[date]    = Field(default=None, description="Defaults to today.")
    available_withdraw:  Optional[Decimal] = Field(default=None, ge=0, description="Seeds an initial snapshot.")
    not_cleared:         Decimal           = Field(default=Decimal("0"), ge=0)
    active_orders:       int               = Field(default=0, ge=0)
    active_order_amount: Decimal           = Field(default=Decimal("0"), ge=0)
    submitted:           Decimal           = Field(default=Decimal("0"), ge=0)
    withdrawn:           Decimal           = Field(default=Decimal("0"), ge=0)
    seller_plus:         bool              = False
    promotion:           Decimal           = Field(default=Decimal("0"), ge=0)


class FiverrProfileUpdate(BaseModel):
    """
    PATCH /profiles/{id} — partial update for a Fiverr profile.

    Only supplied fields are written; omitted fields are left unchanged.
    Sending ``profileName`` renames the profile (uniqueness enforced server-side).
    Sending ``isActive = true`` re-activates a previously soft-deleted profile.
    """
    profileName: Optional[str]  = Field(default=None, min_length=1, max_length=100)
    isActive:    Optional[bool] = Field(
        default=None,
        description="Set false to soft-delete; true to restore a deactivated profile.",
    )


class FiverrProfileResponse(BaseModel):
    """Lightweight profile row (list / create responses)."""
    id:          str
    profileName: str
    isActive:    bool

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot
# ─────────────────────────────────────────────────────────────────────────────

class FiverrSnapshotCreate(BaseModel):
    """
    Daily financial snapshot — upserts on (profileName, date).

    ``profile_name`` replaced ``profile_id`` in v5.
    The service resolves the name to a profile record server-side, so HR
    staff never need to handle internal UUIDs.
    """
    profile_name:        str     = Field(
        ..., min_length=1, max_length=100,
        description="Exact Fiverr profile name (case-insensitive match).",
    )
    date:                date
    available_withdraw:  Decimal = Field(..., ge=0)
    not_cleared:         Decimal = Field(default=Decimal("0"), ge=0)
    active_orders:       int     = Field(default=0, ge=0)
    active_order_amount: Decimal = Field(default=Decimal("0"), ge=0)
    submitted:           Decimal = Field(default=Decimal("0"), ge=0)
    withdrawn:           Decimal = Field(default=Decimal("0"), ge=0)
    seller_plus:         bool    = False
    promotion:           Decimal = Field(default=Decimal("0"), ge=0)


class FiverrSnapshotResponse(BaseModel):
    """Full snapshot row returned by POST /snapshots and GET .../snapshots."""
    id:                        str
    profileId:                 str
    profileName:               str       # ← v5: human-readable label
    date:                      date
    availableWithdraw:         Decimal
    availableWithdrawAfterFee: Decimal   # computed: × 0.80
    notCleared:                Decimal
    activeOrders:              int
    activeOrderAmount:         Decimal
    submitted:                 Decimal
    withdrawn:                 Decimal
    sellerPlus:                bool
    promotion:                 Decimal
    createdAt:                 datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Order
# ─────────────────────────────────────────────────────────────────────────────

class FiverrOrderCreate(BaseModel):
    """
    Log a new Fiverr order.

    ``profile_name`` replaced ``profile_id`` in v5.
    ``afterFiverr`` (amount × 0.80) is always computed server-side.
    """
    profile_name: str     = Field(
        ..., min_length=1, max_length=100,
        description="Exact Fiverr profile name (case-insensitive match).",
    )
    date:         date
    buyer_name:   str     = Field(..., min_length=1)
    order_id:     str     = Field(..., min_length=1)
    amount:       Decimal = Field(..., gt=0)


class FiverrOrderUpdate(BaseModel):
    """
    PATCH /orders/{id} — partial update for a logged Fiverr order.

    Only supplied fields are written; omitted fields are left unchanged.
    If ``amount`` is updated, ``afterFiverr`` is automatically re-computed
    server-side (amount × 0.80) — clients must never send ``afterFiverr``.
    ``order_id`` uniqueness is enforced server-side on rename.
    """
    date:       date
    buyer_name: Optional[str]     = Field(default=None, min_length=1)
    order_id:   Optional[str]     = Field(default=None, min_length=1)
    amount:     Optional[Decimal] = Field(default=None, gt=0)


class FiverrOrderResponse(BaseModel):
    """Full order row."""
    id:          str
    profileId:   str
    date:        date
    buyerName:   str
    orderId:     str
    amount:      Decimal
    afterFiverr: Decimal
    createdAt:   datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Embedded sub-types (profile list / detail responses)
# ─────────────────────────────────────────────────────────────────────────────

class FiverrSnapshotInProfile(BaseModel):
    """Snapshot row embedded within profile list / detail responses."""
    id:                        str
    profileName:               str    # ← v5
    date:                      date
    availableWithdraw:         float
    availableWithdrawAfterFee: float  # view-only, not stored
    notCleared:                float
    activeOrders:              int
    activeOrderAmount:         float
    submitted:                 float
    withdrawn:                 float
    sellerPlus:                bool
    promotion:                 float
    createdAt:                 datetime


class FiverrOrderInProfile(BaseModel):
    """Order row embedded within profile list / detail responses."""
    id:          str
    date:        date
    buyerName:   str
    orderId:     str
    amount:      float
    afterFiverr: float
    createdAt:   datetime


# ─────────────────────────────────────────────────────────────────────────────
# List envelope  GET /profiles
# ─────────────────────────────────────────────────────────────────────────────

class FiverrTotals(BaseModel):
    """Cross-profile aggregate for the selected period."""
    totalAvailableWithdraw:         float
    totalAvailableWithdrawAfterFee: float   # × 0.80
    totalNotCleared:                float
    totalActiveOrders:              int
    totalActiveOrderAmount:         float
    totalSubmitted:                 float
    totalWithdrawn:                 float
    totalPromotion:                 float
    totalRevenueInPeriod:           float   # Σ afterFiverr
    activeProfileCount:             int


class FiverrProfileSummary(BaseModel):
    """Per-profile row within the paginated list response."""
    id:              str
    profileName:     str
    isActive:        bool
    latestSnapshot:  Optional[FiverrSnapshotInProfile]
    periodTotals:    Dict[str, Any]
    snapshotCount:   int
    orderCount:      int
    revenueInPeriod: float
    orders:          List[FiverrOrderInProfile]


class FiverrListResponse(BaseModel):
    """Top-level envelope for GET /profiles."""
    filter:     Dict[str, Any]
    totals:     FiverrTotals
    pagination: Dict[str, Any]
    profiles:   List[FiverrProfileSummary]


# ─────────────────────────────────────────────────────────────────────────────
# Single-profile detail  GET /profiles/{id}
# ─────────────────────────────────────────────────────────────────────────────

class FiverrProfileDetailTotals(BaseModel):
    availableWithdraw:         float
    availableWithdrawAfterFee: float
    notCleared:                float
    activeOrders:              int
    activeOrderAmount:         float
    submitted:                 float
    withdrawn:                 float
    promotion:                 float
    revenueInPeriod:           float
    snapshotCount:             int
    orderCount:                int


class FiverrProfileDetailResponse(BaseModel):
    """Full drill-down for GET /profiles/{id}."""
    filter:       Dict[str, Any]
    profile:      FiverrProfileResponse
    periodTotals: FiverrProfileDetailTotals
    pagination:   Dict[str, Any]
    snapshots:    List[FiverrSnapshotInProfile]
    orders:       List[FiverrOrderInProfile]