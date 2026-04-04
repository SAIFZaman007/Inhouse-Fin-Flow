"""
app/modules/dashboard/router.py
────────────────────────────────────────────────────────────────────────────────
v2 — Enterprise Edition

Examples
────────
  GET /summary                           → all-time totals
  GET /summary?period=daily              → today
  GET /summary?period=daily&export_date=2025-03-01  → specific day
  GET /summary?period=weekly             → current ISO week (Mon–Sun)
  GET /summary?period=monthly&year=2025&month=3     → March 2025
  GET /summary?period=yearly&year=2025              → full year 2025
  GET /summary?from=2025-01-01&to=2025-03-31        → custom range
"""
from typing import Annotated, List, Literal, Optional

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import Response
from prisma import Prisma
from pydantic import BaseModel, Field

from app.core import trash_store
from app.core.database import get_db
from app.core.dependencies import ALL_ROLES, CEO_DIRECTOR

from .service import get_dashboard_summary
from app.modules.export.schema import ExportQueryParams
from app.modules.export.service import export_dashboard

# Module-specific restore services
from app.modules.fiverr.service import restore_trash as fiverr_restore
from app.modules.upwork.service import restore_trash as upwork_restore

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

PeriodLiteral = Literal["daily", "weekly", "monthly", "yearly", "all"]


# ── Schemas ───────────────────────────────────────────────────────────────────

class DashboardRestoreRequest(BaseModel):
    """
    ``POST /restore-trash`` — restore soft-deleted records by ID.

    Each ID is looked up in the trash registry; the module is determined
    automatically from the stored trash item.
    """
    ids: List[str] = Field(
        ...,
        min_length=1,
        description="List of original record IDs to restore (from any module).",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/summary",
    summary="Full dashboard KPIs with per-module drill-down and time-period filtering",
    description="""
Returns a complete dashboard payload covering all financial modules.

### Filter behaviour
| `period`  | What is returned |
|-----------|-----------------|
| `all`     | All-time aggregate (default) |
| `daily`   | The single day specified by `export_date` (defaults to today) |
| `weekly`  | The ISO week (Mon–Sun) that contains `export_date` |
| `monthly` | The month specified by `year` + `month` |
| `yearly`  | The calendar year specified by `year` |

Use `from` + `to` to override with an arbitrary date range.

### Modules returned
`fiverr`, `upwork`, `outsideOrders`, `cardSharing`, `payoneer`,
`pmak`, `dollarExchange`, `hrExpense`, `inventory`
    """,
)
async def dashboard_summary(
    period: Annotated[
        PeriodLiteral,
        Query(description="Granularity: daily | weekly | monthly | yearly | all"),
    ] = "all",
    export_date: Annotated[
        Optional[str],
        Query(
            alias="export_date",
            description="Reference date (YYYY-MM-DD) for daily/weekly. Defaults to today.",
            pattern=r"^\d{4}-\d{2}-\d{2}$",
        ),
    ] = None,
    year: Annotated[
        Optional[int],
        Query(description="Year for monthly/yearly filter.", ge=2000, le=2100),
    ] = None,
    month: Annotated[
        Optional[int],
        Query(description="Month (1–12) for monthly filter.", ge=1, le=12),
    ] = None,
    from_date: Annotated[
        Optional[str],
        Query(
            alias="from",
            description="Custom range start (YYYY-MM-DD). Overrides period.",
            pattern=r"^\d{4}-\d{2}-\d{2}$",
        ),
    ] = None,
    to_date: Annotated[
        Optional[str],
        Query(
            alias="to",
            description="Custom range end (YYYY-MM-DD). Overrides period.",
            pattern=r"^\d{4}-\d{2}-\d{2}$",
        ),
    ] = None,
    db: Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await get_dashboard_summary(
        db,
        period=period,
        ref_date_str=export_date,
        year=year,
        month=month,
        from_date_str=from_date,
        to_date_str=to_date,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/export",
    summary="Export dashboard to Excel — 11-sheet workbook (KPI + all modules)",
    response_description="Excel workbook download (same data as /export/dashboard)",
)
async def dashboard_export(
    params: ExportQueryParams = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    data, filename = await export_dashboard(db, params)
    return Response(
        content=data,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Trash  (cross-module)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/trash",
    summary="All soft-deleted records across every module",
    description="""
Returns **all** soft-deleted records from every module's trash registry
in a single unified response, sorted **newest-deleted-first**.

Use `?module=` to filter by module:
- `fiverr`  — Fiverr profiles, snapshots, and orders
- `upwork`  — Upwork profiles, snapshots, and orders

Use `?type=` to filter by record type:
- `profile`  — deleted profiles
- `snapshot` — deleted daily snapshots
- `order`    — deleted orders

Both filters can be combined: `?module=fiverr&type=snapshot`

Each item includes:
- `id`        — original DB primary key
- `module`    — source module (`fiverr` | `upwork`)
- `type`      — record type (`profile` | `snapshot` | `order`)
- `deletedAt` — ISO 8601 timestamp of deletion
- `snapshot`  — full record dict at time of deletion

**Access:** CEO and Director only.
    """,
)
async def dashboard_trash(
    module: Annotated[
        Optional[str],
        Query(description="Filter by module: fiverr | upwork"),
    ] = None,
    type: Annotated[
        Optional[str],
        Query(description="Filter by record type: profile | snapshot | order"),
    ] = None,
    _=Depends(CEO_DIRECTOR),
):
    items = await trash_store.get_all(module=module, record_type=type)
    # Group by module for clarity
    fiverr_items = [i for i in items if i["module"] == "fiverr"]
    upwork_items = [i for i in items if i["module"] == "upwork"]

    return {
        "total":  len(items),
        "filter": {
            "module": module,
            "type":   type,
        },
        "summary": {
            "fiverr": len(fiverr_items),
            "upwork": len(upwork_items),
        },
        "items": items,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Restore  (cross-module)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/restore-trash",
    summary="Restore soft-deleted records from any module by ID",
    description="""
Restores one or more soft-deleted records from the persistent trash registry.
The **source module** (`fiverr` or `upwork`) is determined automatically
from the stored trash item — no module parameter is needed.

### Restore behaviour by record type
| Type | Action |
|------|--------|
| `profile` | `isActive` set to `true` in the database. |
| `snapshot` | DB row was never deleted; removed from trash, re-appears in all live calculations immediately. |
| `order` | DB row was never deleted; removed from trash, re-appears in all live calculations immediately. |

### Response
Returns combined `restored` and `failed` ID lists across all modules.

**Access:** CEO and Director only.
    """,
)
async def dashboard_restore_trash(
    body: DashboardRestoreRequest,
    db:   Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    # Partition IDs by module using the trash registry
    fiverr_ids: list[str] = []
    upwork_ids: list[str] = []
    unknown_ids: list[str] = []

    for record_id in body.ids:
        item = await trash_store.get_by_id(record_id)
        if item is None:
            unknown_ids.append(record_id)
        elif item.get("module") == "fiverr":
            fiverr_ids.append(record_id)
        elif item.get("module") == "upwork":
            upwork_ids.append(record_id)
        else:
            unknown_ids.append(record_id)

    # Restore per module
    all_restored: list[str] = []
    all_failed:   list[str] = list(unknown_ids)

    if fiverr_ids:
        result = await fiverr_restore(db, fiverr_ids)
        all_restored.extend(result["restored"])
        all_failed.extend(result["failed"])

    if upwork_ids:
        result = await upwork_restore(db, upwork_ids)
        all_restored.extend(result["restored"])
        all_failed.extend(result["failed"])

    total = len(all_restored)
    return {
        "restored": all_restored,
        "failed":   all_failed,
        "message":  f"{total} record(s) restored successfully across all modules."
                    if total else "No records were restored.",
        "breakdown": {
            "fiverr": [r for r in all_restored if r in fiverr_ids],
            "upwork": [r for r in all_restored if r in upwork_ids],
        },
    }