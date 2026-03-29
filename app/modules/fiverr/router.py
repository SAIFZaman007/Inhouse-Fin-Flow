"""
app/modules/fiverr/router.py
════════════════════════════════════════════════════════════════════════════════
v1 — Enterprise Edition

Endpoint matrix
───────────────────────────────────────────────────────────────────────────────
GET    /profiles                 HR_AND_ABOVE  Combined totals + all profiles
                                              Paginated (50/page). ?name= search.
GET    /profiles/{id}            HR_AND_ABOVE  Single-profile drill-down (paginated)
                                              + optional ?name= filter
POST   /profiles                 HR_AND_ABOVE  Create + optional initial snapshot
PATCH  /profiles/{id}            HR_AND_ABOVE  Partial update (rename / isActive /
                                              snapshot fields — all optional)
DELETE /profiles/{id}            CEO_DIRECTOR  Soft-delete — returns JSON message

POST   /snapshots                HR_AND_ABOVE  Additive daily snapshot (by profileName)
GET    /profiles/{id}/snapshots  HR_AND_ABOVE  Paginated snapshots — includes profileName

POST   /orders                   HR_AND_ABOVE  Log order (by profileName, afterFiverr computed)
                                              Automatically syncs snapshot activeOrders +
                                              activeOrderAmount for the same date.
PATCH  /orders/{id}              HR_AND_ABOVE  Partial update (date/buyer/orderId/amount)
GET    /profiles/{id}/orders     HR_AND_ABOVE  Paginated orders for one profile

GET    /export/{profile_id}      CEO_DIRECTOR  Single-profile Excel (period-aware)
════════════════════════════════════════════════════════════════════════════════
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR, HR_AND_ABOVE
from app.shared.filters import DateRangeFilter
from app.shared.pagination import PageParams

from .schema import (
    FiverrOrderCreate,
    FiverrOrderUpdate,
    FiverrProfileCreate,
    FiverrProfileUpdate,
    FiverrSnapshotCreate,
)
from .service import (
    add_order,
    create_profile,
    create_snapshot,
    deactivate_profile,
    export_profile_excel,
    get_profile_detail,
    get_profile_orders,
    get_profile_snapshots,
    list_profiles_summary,
    update_order,
    update_profile,
)

router = APIRouter(prefix="/fiverr", tags=["Fiverr"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _xlsx(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Profiles
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/profiles",
    summary="All Fiverr profiles — combined totals + per-profile breakdown",
    description="""
Returns a **single response** containing:

- **Combined totals** across all active profiles for the selected period —
  `totalAvailableWithdraw`, `totalNotCleared`, `totalActiveOrders`,
  `totalActiveOrderAmount`, `totalSubmitted`, `totalWithdrawn`, `totalPromotion`,
  `totalRevenueInPeriod` (Σ afterFiverr), `totalOrderAmount` (Σ order.amount).
- **Paginated per-profile breakdown** with the latest snapshot + all orders
  for the selected window (50 profiles per page by default).

Use `?name=` for a case-insensitive search on profile name.

Period params: `daily` | `weekly` | `monthly` | `yearly` | `all` (default).
    """,
)
async def get_profiles(
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    name: Annotated[
        Optional[str],
        Query(description="Case-insensitive search on profile name."),
    ] = None,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await list_profiles_summary(db, filters, name=name, pagination=pagination)


@router.get(
    "/profiles/{profile_id}",
    summary="Single Fiverr profile — full drill-down (paginated)",
    description="""
Returns a complete breakdown for **one profile**:
- Period-scoped `periodTotals` (availableWithdraw, notCleared, activeOrders,
  activeOrderAmount, submitted, withdrawn, promotion, revenueInPeriod,
  totalOrderAmount, snapshotCount, orderCount)
- Paginated daily snapshots in the window (newest first, 50 per page)
- Paginated orders in the window (newest first, 50 per page)

Use `?name=` for an optional case-insensitive filter on profile name.

Same period + pagination query params as GET /profiles.
    """,
)
async def get_profile(
    profile_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    name: Annotated[
        Optional[str],
        Query(description="Optional case-insensitive filter on profile name."),
    ] = None,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_profile_detail(db, profile_id, filters, pagination=pagination, name=name)


@router.post(
    "/profiles",
    status_code=201,
    summary="Create a Fiverr profile (optionally seed with an initial snapshot)",
    description="""
Creates a new Fiverr profile.

If `available_withdraw` is provided, an initial snapshot is recorded immediately —
no separate POST /snapshots call needed. `snapshot_date` defaults to today.

**Required:** `profileName`
**Optional snapshot fields:** `snapshot_date`, `available_withdraw`, `not_cleared`,
`active_orders`, `active_order_amount`, `submitted`, `withdrawn`, `seller_plus`,
`promotion`

**Access:** CEO, Director, and HR.
    """,
)
async def add_profile(
    body: FiverrProfileCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await create_profile(db, body)


@router.patch(
    "/profiles/{profile_id}",
    summary="Partially update a Fiverr profile (metadata + optional snapshot upsert)",
    description="""
Performs a **partial update** on an existing Fiverr profile.

All fields are optional — only supplied fields are changed.

### Profile metadata

| Field | Effect |
|---|---|
| `profileName` | Renames the profile; uniqueness enforced (409 on conflict). |
| `isActive` | `false` soft-deletes the profile; `true` restores a deactivated one. |

### Snapshot fields

When any snapshot field is present the service performs an **upsert** on the
snapshot for `snapshot_date` (defaults to **today**).

| Field | Description |
|---|---|
| `snapshot_date` | Target date for the upsert (defaults to today). |
| `available_withdraw` | Current available-withdraw balance. |
| `not_cleared` | Funds not yet cleared. |
| `active_orders` | Count of active (in-progress) orders. |
| `active_order_amount` | Total $ value of active orders. |
| `submitted` | Submitted-for-clearance amount. |
| `withdrawn` | Total withdrawn amount. |
| `seller_plus` | Fiverr Seller Plus subscription flag. |
| `promotion` | Promotion credit balance. |

Sending an empty body `{}` is accepted and returns the current profile state
unchanged (idempotent).

**Access:** CEO, Director, and HR.
    """,
)
async def patch_profile(
    profile_id: str,
    body: FiverrProfileUpdate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await update_profile(db, profile_id, body)


@router.delete(
    "/profiles/{profile_id}",
    status_code=200,
    summary="Soft-delete a Fiverr profile (sets isActive = false)",
    description="""
Soft-deletes a Fiverr profile by setting `isActive` to `false`.

The profile and all its historical snapshots/orders remain intact in the
database and can be restored via `PATCH /profiles/{id}` with `isActive: true`.

Returns a JSON confirmation message on success.

**Access:** CEO and Director only.
    """,
)
async def remove_profile(
    profile_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await deactivate_profile(db, profile_id)
    return {
        "success":   True,
        "message":   "Fiverr profile has been deactivated successfully.",
        "profileId": profile_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Snapshots
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/snapshots",
    status_code=201,
    summary="Add or update a daily Fiverr snapshot (additive accumulation)",
    description="""
**Additively accumulates** a daily financial snapshot for the specified profile + date.

### Submission behaviour

| Scenario | Result |
|---|---|
| **First submission** for `(profileName, date)` | Row is **inserted** with the incoming values as-is. |
| **Subsequent submission** for the same `(profileName, date)` | Incoming numeric values are **added** to the existing stored values. The response reflects the new running total. |

> **`seller_plus`** uses OR semantics — once `true` for the day it remains `true`
> regardless of subsequent submissions.

This design ensures that multiple HR inputs throughout the same day accumulate
into a running total rather than silently overwriting previous entries.

The response includes a **`syncedTotals`** block (`revenueAllTime`,
`orderAmountAllTime`) for immediate dashboard refresh.

After this call, `latestSnapshot`, `periodTotals`, and cross-profile `totals`
in `GET /profiles` all reflect the new values on the very next request.

**`profile_name`** — the human-readable profile name (case-insensitive).
The system resolves it to an internal profile record automatically.
    """,
)
async def add_snapshot(
    body: FiverrSnapshotCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await create_snapshot(db, body)


@router.get(
    "/profiles/{profile_id}/snapshots",
    summary="All snapshots for one Fiverr profile (period-aware, paginated)",
    description="""
Returns paginated daily snapshots for a single profile.

Each snapshot row includes **`profileName`** so clients always have full
context without a secondary profile lookup.

Default: 50 snapshots per page, newest first.
    """,
)
async def profile_snapshots(
    profile_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_profile_snapshots(
        db, profile_id, filters.to_prisma_filter(), pagination=pagination
    )


# ─────────────────────────────────────────────────────────────────────────────
# Orders
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/orders",
    status_code=201,
    summary="Log a new Fiverr order",
    description="""
Logs an individual Fiverr order and **automatically syncs** the daily snapshot.

**`profile_name`** — the human-readable profile name (case-insensitive).
The system resolves it to an internal profile record automatically.

`afterFiverr` (net after Fiverr's 20 % platform fee) is **computed server-side**
as `amount × 0.80` — it is never accepted from the client.

### Automatic snapshot sync

After the order row is persisted the system **additively updates** the snapshot
for `(profileName, date)`:

| Field | Change |
|---|---|
| `activeOrders` | **+1** |
| `activeOrderAmount` | **+order.amount** |

If no snapshot exists yet for that date one is **upserted automatically**
with the order amount seeding both fields.

No extra API call is needed — the platform stays fully in-sync in a single request.

The response includes a **`snapshotSync`** summary (date, updated `activeOrders`
and `activeOrderAmount`) and a **`syncedTotals`** block (`revenueAllTime`,
`orderAmountAllTime`) for immediate dashboard display.

After this call, `latestSnapshot`, `periodTotals`, and the cross-profile `totals`
block in `GET /profiles` all reflect the new values on the very next request.

**Access:** CEO, Director, and HR.
    """,
)
async def add_order_entry(
    body: FiverrOrderCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await add_order(db, body)


@router.patch(
    "/orders/{order_id}",
    summary="Partially update a logged Fiverr order",
    description="""
Performs a **partial update** on an existing Fiverr order.

All fields are optional — only supplied fields are changed:

| Field | Effect |
|---|---|
| `date` | Changes the order date. |
| `buyer_name` | Updates the buyer display name. |
| `order_id` | Renames the Fiverr order ID; uniqueness enforced (409 on conflict). |
| `amount` | Updates gross amount **and** auto-recomputes `afterFiverr` (×0.80). |

`afterFiverr` is **always server-computed** — never accepted from the client.

Sending an empty body `{}` returns the current order state unchanged (idempotent).

**Access:** HR and above.
    """,
)
async def patch_order(
    order_id: str,
    body: FiverrOrderUpdate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await update_order(db, order_id, body)


@router.get(
    "/profiles/{profile_id}/orders",
    summary="All orders for one Fiverr profile (period-aware, paginated)",
    description="Returns paginated orders. Default: 50 orders per page, newest first.",
)
async def profile_orders(
    profile_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_profile_orders(
        db, profile_id, filters.to_prisma_filter(), pagination=pagination
    )


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/export/{profile_id}",
    summary="Export a single Fiverr profile to Excel (period-aware)",
    description="""
Downloads a two-sheet Excel workbook for **one profile**:
- **Sheet 1** — Daily Snapshots (all snapshot fields)
- **Sheet 2** — Orders (date, buyer, orderId, amount, afterFiverr)

Supports the same period query parameters as all other endpoints.

**Access:** CEO and Director only.
    """,
)
async def export_single_profile(
    profile_id: str,
    filters:    DateRangeFilter = Depends(),
    db:         Prisma          = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    data, filename = await export_profile_excel(db, profile_id, filters)
    return _xlsx(data, filename)