"""
app/modules/upwork/schema.py
════════════════════════════════════════════════════════════════════════════════
v9 — Enterprise Edition

Changes vs v8
─────────────
UpworkSnapshotCreate      NEW OPTIONAL FIELD — ``active_amount``
                            Optional alias for ``work_in_progress``.  Both map
                            to the same ``workInProgress`` DB column.
                            • Only ``work_in_progress`` supplied  → unchanged behaviour.
                            • Only ``active_amount``   supplied   → treated as wip.
                            • Both supplied                       → values are summed.
                            Omitting ``active_amount`` has zero effect on existing flows.

UpworkSnapshotResponse    NEW FIELD — ``activeAmount``
UpworkSnapshotInProfile   Always equals ``workInProgress``; surfaced as a sibling
                            key so all consumer endpoints expose both names.

UpworkProfileDetailTotals Field order aligned with list response for consistency.

UpworkOrderCreate         Doc-string updated to describe order → snapshot sync.

Everything else is unchanged from v8.
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


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


class UpworkProfileUpdate(BaseModel):
    """
    PATCH /profiles/{id} — partial update for an Upwork profile.

    All fields are optional — only supplied fields are written.

    Profile identity fields
    ───────────────────────
    ``profileName``  Renames the profile (uniqueness enforced server-side).
    ``isActive``     ``false`` soft-deletes; ``true`` restores a deactivated profile.

    Snapshot fields  (v7 addition)
    ──────────────────────────────
    When any snapshot field is supplied the service performs an **upsert** on
    today's snapshot (or ``snapshot_date`` if provided), so a single PATCH
    keeps both profile metadata and the current-day balance in sync.

    ``snapshot_date``    Target date for the upsert (defaults to today).
    ``available_withdraw`` Current available-withdraw balance.
    ``pending``          Funds pending clearance.
    ``in_review``        Funds currently in review.
    ``work_in_progress`` Active contract work-in-progress value.
    ``withdrawn``        Total withdrawn amount.
    ``connects``         Available Connects count.
    ``upwork_plus``      Upwork Plus subscription flag.
    """
    # ── Profile metadata ─────────────────────────────────────────────────────
    profileName: Optional[str]  = Field(default=None, min_length=1, max_length=100)
    isActive:    Optional[bool] = Field(
        default=None,
        description="Set false to soft-delete; true to restore a deactivated profile.",
    )

    # ── Snapshot fields (v7) ─────────────────────────────────────────────────
    snapshot_date:      Optional[date]    = Field(
        default=None,
        description="Date for the snapshot upsert. Defaults to today when any snapshot field is supplied.",
    )
    available_withdraw: Optional[Decimal] = Field(default=None, ge=0)
    pending:            Optional[Decimal] = Field(default=None, ge=0)
    in_review:          Optional[Decimal] = Field(default=None, ge=0)
    work_in_progress:   Optional[Decimal] = Field(default=None, ge=0)
    withdrawn:          Optional[Decimal] = Field(default=None, ge=0)
    connects:           Optional[int]     = Field(default=None, ge=0)
    upwork_plus:        Optional[bool]    = None                          # FIXED: no bare Field()


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
    Daily financial snapshot — additive accumulation on (profileName, date).

    ``profile_name`` replaced ``profile_id`` in v5.
    The service resolves the name to a profile record server-side.

    Submission behaviour
    ────────────────────
    • First submission for (profileName, date)
        → INSERT the row with the incoming values as-is.
    • Subsequent submission for the same (profileName, date)
        → ADD (accumulate) the incoming numeric values to the existing stored
          values rather than replacing them.
        → ``upwork_plus`` uses OR semantics: once True for the day it stays True.

    This ensures that multiple HR inputs throughout the same day accumulate
    into a running total rather than silently overwriting previous entries.
    The response always reflects the current accumulated state of the row.

    ``active_amount`` / ``work_in_progress`` duality
    ─────────────────────────────────────────────────
    ``active_amount`` is an **optional alias** for ``work_in_progress``.
    Both fields map to the same ``workInProgress`` DB column.

    • Only ``work_in_progress`` supplied  → stored as-is (unchanged behaviour).
    • Only ``active_amount``   supplied   → treated identically to ``work_in_progress``.
    • Both supplied                       → their values are **summed** before storage.
    • Neither supplied                    → defaults to 0.

    Both ``workInProgress`` and ``activeAmount`` are always returned in every
    response with identical values, for full forward/backward compatibility.
    """
    profile_name:       str     = Field(
        ..., min_length=1, max_length=100,
        description="Exact Upwork profile name (case-insensitive match).",
    )
    date:               date
    available_withdraw: Decimal = Field(..., ge=0)
    pending:            Decimal = Field(default=Decimal("0"), ge=0)
    in_review:          Decimal = Field(default=Decimal("0"), ge=0)
    work_in_progress:   Decimal = Field(default=Decimal("0"), ge=0)
    # Optional alias ──────────────────────────────────────────────────────────
    active_amount:      Optional[Decimal] = Field(
        default=None, ge=0,
        description=(
            "Optional alias for work_in_progress. "
            "When supplied its value is added to work_in_progress before storage. "
            "The response always reflects the merged value under both keys."
        ),
    )
    withdrawn:          Decimal = Field(default=Decimal("0"), ge=0)
    connects:           int     = Field(default=0, ge=0)
    upwork_plus:        bool    = False

    @model_validator(mode="after")
    def _merge_active_amount(self) -> "UpworkSnapshotCreate":
        """
        Collapse ``active_amount`` into ``work_in_progress`` so the service
        layer always works through a single field name.
        """
        if self.active_amount is not None:
            self.work_in_progress = self.work_in_progress + self.active_amount
        # Mirror back so the response always carries both keys.
        self.active_amount = self.work_in_progress
        return self


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
    activeAmount:              Decimal  # v9: alias — always equals workInProgress
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

    Automatic snapshot sync
    ───────────────────────
    After persisting the order row the service additively updates the snapshot
    for ``(profileName, date)``:

    • ``workInProgress`` and ``activeAmount`` on the matching snapshot are
      each incremented by ``amount`` (they are the same DB column; both
      response keys reflect the updated value).
    • If no snapshot exists yet for that date one is **upserted** automatically
      with the order amount seeding ``workInProgress`` / ``activeAmount``.
    • The aggregated ``periodTotals`` and ``totals`` values returned by
      GET /profiles update automatically to reflect the new order.

    No extra API call is needed after POST /orders — the platform stays
    fully in-sync with a single request.
    """
    profile_name: str     = Field(
        ..., min_length=1, max_length=100,
        description="Exact Upwork profile name (case-insensitive match).",
    )
    date:         date
    client_name:  str     = Field(..., min_length=1)
    order_id:     str     = Field(..., min_length=1)
    amount:       Decimal = Field(..., gt=0)


class UpworkOrderUpdate(BaseModel):
    """
    PATCH /orders/{id} — partial update for a logged Upwork order.

    All fields are optional — only supplied fields are written.
    If ``amount`` is updated, ``afterUpwork`` is automatically re-computed
    server-side (amount × 0.90) — clients must never send ``afterUpwork``.
    ``order_id`` uniqueness is enforced server-side on rename.

    Sending an empty body ``{}`` returns the current order unchanged (idempotent).
    """
    date:        date
    client_name: Optional[str]     = Field(default=None, min_length=1)
    order_id:    Optional[str]     = Field(default=None, min_length=1)
    amount:      Optional[Decimal] = Field(default=None, gt=0)


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
    activeAmount:              float  # v9: alias — always equals workInProgress
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
    totalActiveAmount:              float   # v8: Σ order.amount across all profiles
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
    activeAmount:              float   # v8: Σ order.amount for this profile
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