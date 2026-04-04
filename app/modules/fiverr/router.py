"""
app/modules/fiverr/router.py
════════════════════════════════════════════════════════════════════════════════
v3 — Enterprise Edition
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
    FiverrRestoreRequest,
    FiverrSnapshotCreate,
    FiverrSnapshotUpdate,
)
from .service import (
    add_order,
    create_profile,
    create_snapshot,
    export_profile_excel,
    get_profile_detail,
    get_profile_orders,
    get_profile_snapshots,
    get_trash,
    list_profiles_summary,
    restore_trash,
    soft_delete_profile,
    soft_delete_snapshot,
    update_order,
    update_profile,
    update_snapshot,
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

- **Combined totals** across all active profiles for the selected period.
- **Paginated per-profile breakdown** with the latest snapshot + all live orders.

### Dynamic `totalActiveOrders`
`totalActiveOrders` is **fully dynamic**:
- **+1** whenever an order is posted (snapshot sync increments `activeOrders`).
- **-1** whenever a snapshot or order is soft-deleted.
- **-N** (N = profile's active order count) whenever a profile is soft-deleted.

Soft-deleted records are excluded automatically from all calculations.

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
- Period-scoped totals (availableWithdraw, notCleared, activeOrders …)
- Paginated daily **live** snapshots in the window (newest first)
- Paginated **live** orders in the window (newest first)

`orderCount` and `snapshotCount` are **dynamic** — soft-deleted records excluded.
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

If any snapshot field is provided, an initial snapshot is recorded immediately.
`snapshot_date` defaults to today.

All fields are optional — supply only what you need.

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
| `isActive` | `false` soft-deletes; `true` restores a deactivated profile. |

### Snapshot fields
When any snapshot field is present, the service performs an **upsert** on the
snapshot for `snapshot_date` (defaults to today).

Sending an empty body `{}` is idempotent.

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
    summary="Soft-delete a Fiverr profile — full trash registry entry",
    description="""
**Fully soft-deletes** a Fiverr profile:

1. Sets `isActive = false` in the database.
2. Writes the profile + **all its snapshots** + **all its orders** to the persistent trash registry.
3. All trashed records are excluded from every live calculation immediately,
   including `totalActiveOrders`.

The data is never hard-deleted — restore via `POST /restore-trash`.

**Access:** CEO and Director only.
    """,
)
async def remove_profile(
    profile_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await soft_delete_profile(db, profile_id)


# ─────────────────────────────────────────────────────────────────────────────
# Snapshots
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/snapshots",
    status_code=201,
    summary="Add or update a daily Fiverr snapshot (additive accumulation)",
    description="""
**Additively accumulates** a daily financial snapshot for the specified profile + date.

| Scenario | Result |
|---|---|
| **First submission** for `(profile_name, date)` | Row is **inserted** with the incoming values as-is. |
| **Subsequent submission** for the same pair | Incoming numeric values are **added** to the existing stored values. |

`seller_plus` uses OR semantics — once `true` for the day it remains `true`.

All fields are optional — supply only what you need.

**Access:** HR and above.
    """,
)
async def add_snapshot(
    body: FiverrSnapshotCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await create_snapshot(db, body)


@router.patch(
    "/snapshots/{snapshot_id}",
    summary="Edit a daily Fiverr snapshot (SET semantics — correction mode)",
    description="""
Performs a **partial update** on an existing Fiverr snapshot.

**SET semantics** — unlike `POST /snapshots` (which *adds* to existing values),
this endpoint *replaces* only the supplied fields. Use it to correct a
previously submitted snapshot.

All fields are optional — only supplied fields are overwritten.
Sending an empty body `{}` is idempotent.

`profile_name` and `date` are **immutable** after creation and are not accepted.

**Access:** HR and above.
    """,
)
async def patch_snapshot(
    snapshot_id: str,
    body: FiverrSnapshotUpdate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await update_snapshot(db, snapshot_id, body)


@router.delete(
    "/snapshots/{snapshot_id}",
    status_code=200,
    summary="Soft-delete a daily Fiverr snapshot",
    description="""
**Soft-deletes** a snapshot by writing it to the trash registry.

The database row is **not** removed — the record is excluded from all
live calculations (including `totalActiveOrders`) until restored via
`POST /restore-trash`.

**Access:** CEO and Director only.
    """,
)
async def delete_snapshot(
    snapshot_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await soft_delete_snapshot(db, snapshot_id)


@router.get(
    "/profiles/{profile_id}/snapshots",
    summary="All live snapshots for one Fiverr profile (period-aware, paginated)",
    description="""
Returns paginated **live** (non-deleted) daily snapshots for a single profile.

Each snapshot row includes **`profileName`** for full client context.
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

`afterFiverr` (net after 20 % platform fee) is **computed server-side**.

### Automatic snapshot sync
After the order row is persisted:
- `activeOrders` on the matching snapshot is incremented by **+1**.
- `activeOrderAmount` is incremented by `amount`.
- If no snapshot exists yet for that date one is **upserted automatically**.

### Dynamic `totalActiveOrders`
`totalActiveOrders` in all profile responses updates **immediately** after each order.

All fields are optional — supply only what you need.

**Access:** HR and above.
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
    summary="All live orders for one Fiverr profile (period-aware, paginated)",
    description="Returns paginated **live** (non-deleted) orders. Default: 50 per page, newest first.",
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
# Trash & Restore
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/trash",
    summary="Get all soft-deleted Fiverr records",
    description="""
Returns all soft-deleted Fiverr records from the persistent trash registry,
sorted **newest-deleted-first**.

Use `?type=` to filter by record type:
- `profile`  — deleted profiles
- `snapshot` — deleted daily snapshots
- `order`    — deleted orders

Each item includes a full `snapshot` dict of the record at deletion time.

**Access:** CEO and Director only.
    """,
)
async def fiverr_trash(
    type: Annotated[
        Optional[str],
        Query(description="Filter by record type: profile | snapshot | order"),
    ] = None,
    _=Depends(CEO_DIRECTOR),
):
    return await get_trash(record_type=type)


@router.post(
    "/restore-trash",
    summary="Restore soft-deleted Fiverr records by ID",
    description="""
Restores one or more soft-deleted Fiverr records from the trash registry.

- **Profiles** — `isActive` is set back to `true` in the database.
- **Snapshots** / **Orders** — the database rows were never removed; they are
  simply removed from the trash registry and immediately re-appear in all live
  calculations, including `totalActiveOrders`.

Returns lists of successfully `restored` IDs and `failed` IDs.

**Access:** CEO and Director only.
    """,
)
async def fiverr_restore_trash(
    body: FiverrRestoreRequest,
    db:   Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await restore_trash(db, body.ids)


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/export/{profile_id}",
    summary="Export a single Fiverr profile to Excel (period-aware)",
    description="""
Downloads a two-sheet Excel workbook for **one profile**:
- **Sheet 1** — Daily Snapshots (live records only)
- **Sheet 2** — Orders (live records only)

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