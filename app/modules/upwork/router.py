"""
app/modules/upwork/router.py
════════════════════════════════════════════════════════════════════════════════
v5 — Enterprise Edition

Endpoint matrix
───────────────────────────────────────────────────────────────────────────────
GET    /profiles                 HR_AND_ABOVE  Combined totals + all profiles
                                              Paginated (50/page). ?name= search.
GET    /profiles/{id}            HR_AND_ABOVE  Single-profile drill-down (paginated)
POST   /profiles                 CEO_DIRECTOR  Create + optional initial snapshot
DELETE /profiles/{id}            CEO_DIRECTOR  Soft-delete (isActive → false)

POST   /snapshots                HR_AND_ABOVE  Upsert daily snapshot (by profileName)
GET    /profiles/{id}/snapshots  HR_AND_ABOVE  Paginated snapshots — includes profileName

POST   /orders                   HR_AND_ABOVE  Log order (by profileName, afterUpwork computed)
GET    /profiles/{id}/orders     HR_AND_ABOVE  Paginated orders for one profile

GET    /export                   CEO_DIRECTOR  All-profiles Excel (period-aware)
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
from app.modules.export.schema import ExportQueryParams
from app.modules.export.service import export_upwork

from .schema import (
    UpworkOrderCreate,
    UpworkProfileCreate,
    UpworkSnapshotCreate,
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
)

router = APIRouter(prefix="/upwork", tags=["Upwork"])

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
    summary="All Upwork profiles — combined totals + per-profile breakdown",
    description="""
Returns a **single response** containing:

- **Combined totals** across all active profiles for the selected period —
  `totalAvailableWithdraw`, `totalAvailableWithdrawAfterFee` (×0.90),
  `totalPending`, `totalInReview`, `totalWorkInProgress`, `totalWithdrawn`,
  `totalConnects`, `totalRevenueInPeriod`.
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
    summary="Single Upwork profile — full drill-down (paginated)",
    description="""
Returns a complete breakdown for **one profile**:
- Period-scoped totals (availableWithdraw, afterFee, pending, inReview, wip, revenue …)
- Paginated daily snapshots in the window (newest first, 50 per page)
- Paginated orders in the window (newest first, 50 per page)

Same period + pagination query params as GET /profiles.
    """,
)
async def get_profile(
    profile_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_profile_detail(db, profile_id, filters, pagination=pagination)


@router.post(
    "/profiles",
    status_code=201,
    summary="Create an Upwork profile (optionally seed with an initial snapshot)",
    description="""
Creates a new Upwork profile.

If `available_withdraw` is provided, an initial snapshot is recorded immediately —
no separate POST /snapshots call needed. `snapshot_date` defaults to today.

**Required:** `profileName`
**Optional snapshot fields:** `snapshot_date`, `available_withdraw`, `pending`,
`in_review`, `work_in_progress`, `withdrawn`, `connects`, `upwork_plus`
    """,
)
async def add_profile(
    body: UpworkProfileCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await create_profile(db, body)


@router.delete(
    "/profiles/{profile_id}",
    status_code=204,
    summary="Soft-delete an Upwork profile (sets isActive = false)",
)
async def remove_profile(
    profile_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await deactivate_profile(db, profile_id)


# ─────────────────────────────────────────────────────────────────────────────
# Snapshots
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/snapshots",
    status_code=201,
    summary="Add or update a daily Upwork snapshot",
    description="""
**Upserts** a daily financial snapshot for the specified profile + date.
If a snapshot already exists for `(profileName, date)` it is **updated**;
otherwise a new one is created.

**`profile_name`** — the human-readable profile name (case-insensitive).
The system resolves it to an internal profile record automatically.
HR staff never need to know or handle internal profile UUIDs.

Use this endpoint for daily HR data entry to keep profile balances current.
    """,
)
async def add_snapshot(
    body: UpworkSnapshotCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await create_snapshot(db, body)


@router.get(
    "/profiles/{profile_id}/snapshots",
    summary="All snapshots for one Upwork profile (period-aware, paginated)",
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
    summary="Log a new Upwork order",
    description="""
Logs an individual Upwork order.

**`profile_name`** — the human-readable profile name (case-insensitive).
The system resolves it to an internal profile record automatically.

`afterUpwork` (net after 10 % service fee) is **computed server-side** —
it is never accepted from the client.
    """,
)
async def add_order_entry(
    body: UpworkOrderCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await add_order(db, body)


@router.get(
    "/profiles/{profile_id}/orders",
    summary="All orders for one Upwork profile (period-aware, paginated)",
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
    "/export",
    summary="Export all Upwork accounts to Excel (period-aware, multi-sheet)",
    description="""
Downloads a multi-sheet Excel workbook covering **all active Upwork profiles**
for the selected period.

Supports the same `period` / `from` / `to` / `year` / `month` / `export_date`
query parameters as all other endpoints.

**Access:** CEO and Director only.
    """,
)
async def export_all_profiles(
    params: ExportQueryParams = Depends(),
    db:     Prisma            = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    data, filename = await export_upwork(db, params)
    return _xlsx(data, filename)


@router.get(
    "/export/{profile_id}",
    summary="Export a single Upwork profile to Excel (period-aware)",
    description="""
Downloads a two-sheet Excel workbook for **one profile**:
- **Sheet 1** — Daily Snapshots (all fields + After Fee column)
- **Sheet 2** — Orders (date, client, orderId, amount, afterUpwork)

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