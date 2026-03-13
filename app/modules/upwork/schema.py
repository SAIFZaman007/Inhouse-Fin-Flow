"""
app/modules/upwork/schema.py
════════════════════════════════════════════════════════════════════════════════
v5 — Enterprise Edition

Changes vs v4
─────────────
UpworkSnapshotCreate
  • ``profile_id``  →  ``profile_name``  (str, case-insensitive server lookup)

UpworkOrderCreate
  • ``profile_id``  →  ``profile_name``  (same rationale)

UpworkSnapshotInProfile  / UpworkSnapshotResponse
  • ``profileName`` field added — every snapshot row carries a human-readable
    label; clients never need a second profile lookup.

Design notes
────────────
• afterUpwork is NEVER accepted from the client — always server-computed.
• availableWithdrawAfterFee = availableWithdraw × 0.90 (view-only, not stored).
• Monetary fields use Decimal for precision; float only in aggregate totals.
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Fee constant (mirrors service.py — keep in sync) ─────────────────────────
_UPWORK_FEE = Decimal("0.10")


# ─────────────────────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────────────────────

class UpworkProfileCreate(BaseModel):
    """
    Create a new Upwork profile.

    If ``available_withdraw`` is supplied, an initial snapshot is recorded
    for ``snapshot_date`` (defaults to today).
    """
    profileName: str = Field(..., min_length=1, max_length=100)

    # Optional initial-snapshot fields ───────────────────────────────────────
    snapshot_date:      Optional[date]    = Field(default=None, description="Defaults to today.")
    available_withdraw: Optional[Decimal] = Field(default=None, ge=0, description="Seeds an initial snapshot.")
    pending:            Decimal           = Field(default=Decimal("0"), ge=0)
    in_review:          Decimal           = Field(default=Decimal("0"), ge=0)
    work_in_progress:   Decimal           = Field(default=Decimal("0"), ge=0)
    withdrawn:          Decimal           = Field(default=Decimal("0"), ge=0)
    connects:           int               = Field(default=0, ge=0)
    upwork_plus:        bool              = False


class UpworkProfileResponse(BaseModel):
    """Lightweight profile row (list / create responses)."""
    id:          str
    profileName: str
    isActive:    bool

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot
# ─────────────────────────────────────────────────────────────────────────────

class UpworkSnapshotCreate(BaseModel):
    """
    Daily financial snapshot — upserts on (profileName, date).

    ``profile_name`` replaced ``profile_id`` in v5.
    The service resolves the name to a profile record server-side.
    """
    profile_name:      str     = Field(
        ..., min_length=1, max_length=100,
        description="Exact Upwork profile name (case-insensitive match).",
    )
    date:              date
    available_withdraw: Decimal = Field(..., ge=0)
    pending:           Decimal  = Field(default=Decimal("0"), ge=0)
    in_review:         Decimal  = Field(default=Decimal("0"), ge=0)
    work_in_progress:  Decimal  = Field(default=Decimal("0"), ge=0)
    withdrawn:         Decimal  = Field(default=Decimal("0"), ge=0)
    connects:          int      = Field(default=0, ge=0)
    upwork_plus:       bool     = False


class UpworkSnapshotResponse(BaseModel):
    """Full snapshot row returned by POST /snapshots and GET .../snapshots."""
    id:                        str
    profileId:                 str
    profileName:               str      # ← v5: human-readable label
    date:                      date
    availableWithdraw:         Decimal
    availableWithdrawAfterFee: Decimal  # computed: × 0.90
    pending:                   Decimal
    inReview:                  Decimal
    workInProgress:            Decimal
    withdrawn:                 Decimal
    connects:                  int
    upworkPlus:                bool
    createdAt:                 datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Order
# ─────────────────────────────────────────────────────────────────────────────

class UpworkOrderCreate(BaseModel):
    """
    Log a new Upwork order.

    ``profile_name`` replaced ``profile_id`` in v5.
    ``afterUpwork`` (amount × 0.90) is always computed server-side.
    """
    profile_name: str     = Field(
        ..., min_length=1, max_length=100,
        description="Exact Upwork profile name (case-insensitive match).",
    )
    date:         date
    client_name:  str     = Field(..., min_length=1)
    order_id:     str     = Field(..., min_length=1)
    amount:       Decimal = Field(..., gt=0)


class UpworkOrderResponse(BaseModel):
    """Full order row."""
    id:          str
    profileId:   str
    date:        date
    clientName:  str
    orderId:     str
    amount:      Decimal
    afterUpwork: Decimal
    createdAt:   datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Embedded sub-types (profile list / detail responses)
# ─────────────────────────────────────────────────────────────────────────────

class UpworkSnapshotInProfile(BaseModel):
    """Snapshot row embedded within profile list / detail responses."""
    id:                        str
    profileName:               str    # ← v5
    date:                      date
    availableWithdraw:         float
    availableWithdrawAfterFee: float  # view-only, not stored
    pending:                   float
    inReview:                  float
    workInProgress:            float
    withdrawn:                 float
    connects:                  int
    upworkPlus:                bool
    createdAt:                 datetime


class UpworkOrderInProfile(BaseModel):
    """Order row embedded within profile list / detail responses."""
    id:          str
    date:        date
    clientName:  str
    orderId:     str
    amount:      float
    afterUpwork: float
    createdAt:   datetime


# ─────────────────────────────────────────────────────────────────────────────
# List envelope  GET /profiles
# ─────────────────────────────────────────────────────────────────────────────

class UpworkTotals(BaseModel):
    """Cross-profile aggregate for the selected period."""
    totalAvailableWithdraw:         float
    totalAvailableWithdrawAfterFee: float   # × 0.90
    totalPending:                   float
    totalInReview:                  float
    totalWorkInProgress:            float
    totalWithdrawn:                 float
    totalConnects:                  int
    totalRevenueInPeriod:           float   # Σ afterUpwork
    activeProfileCount:             int


class UpworkProfileSummary(BaseModel):
    """Per-profile row within the paginated list response."""
    id:              str
    profileName:     str
    isActive:        bool
    latestSnapshot:  Optional[UpworkSnapshotInProfile]
    periodTotals:    Dict[str, Any]
    snapshotCount:   int
    orderCount:      int
    revenueInPeriod: float
    orders:          List[UpworkOrderInProfile]


class UpworkListResponse(BaseModel):
    """Top-level envelope for GET /profiles."""
    filter:     Dict[str, Any]
    totals:     UpworkTotals
    pagination: Dict[str, Any]
    profiles:   List[UpworkProfileSummary]


# ─────────────────────────────────────────────────────────────────────────────
# Single-profile detail  GET /profiles/{id}
# ─────────────────────────────────────────────────────────────────────────────

class UpworkProfileDetailTotals(BaseModel):
    availableWithdraw:         float
    availableWithdrawAfterFee: float
    pending:                   float
    inReview:                  float
    workInProgress:            float
    withdrawn:                 float
    connects:                  int
    revenueInPeriod:           float
    snapshotCount:             int
    orderCount:                int


class UpworkProfileDetailResponse(BaseModel):
    """Full drill-down for GET /profiles/{id}."""
    filter:       Dict[str, Any]
    profile:      UpworkProfileResponse
    periodTotals: UpworkProfileDetailTotals
    pagination:   Dict[str, Any]
    snapshots:    List[UpworkSnapshotInProfile]
    orders:       List[UpworkOrderInProfile]