"""
app/modules/dashboard/router.py
---------------------------------
Dashboard endpoints.

  GET /summary   → ALL_ROLES  — Full KPI + per-module drill-down
                   Supports DAILY | WEEKLY | MONTHLY | YEARLY | ALL filtering.

  GET /export    → ALL_ROLES  — Multi-sheet Excel download (unchanged)

Query parameters for /summary
------------------------------
  period       string  "daily" | "weekly" | "monthly" | "yearly" | "all"
                       Default: "all"
  export_date  string  ISO date (YYYY-MM-DD) used as reference for daily/weekly.
                       Defaults to today.
  year         int     Year for monthly/yearly filter.
  month        int     Month (1–12) for monthly filter.
  from         string  Explicit range start YYYY-MM-DD. Overrides period.
  to           string  Explicit range end   YYYY-MM-DD. Overrides period.

Examples
--------
  GET /summary                           → all-time totals
  GET /summary?period=daily              → today
  GET /summary?period=daily&export_date=2025-03-01  → specific day
  GET /summary?period=weekly             → current ISO week (Mon–Sun)
  GET /summary?period=monthly&year=2025&month=3     → March 2025
  GET /summary?period=yearly&year=2025              → full year 2025
  GET /summary?from=2025-01-01&to=2025-03-31        → custom range
"""
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import ALL_ROLES

from .service import get_dashboard_summary
from app.modules.export.schema import ExportQueryParams
from app.modules.export.service import export_dashboard

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

PeriodLiteral = Literal["daily", "weekly", "monthly", "yearly", "all"]


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