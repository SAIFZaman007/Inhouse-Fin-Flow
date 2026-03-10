"""
app/modules/dashboard/router.py
---------------------------------
Dashboard endpoints.

  GET /summary   → ALL_ROLES  (JSON KPI summary)
  GET /export    → ALL_ROLES  (multi-sheet Excel download)
                   — identical data/logic as GET /export/dashboard,
                     but mounted directly under the dashboard prefix for
                     clean REST semantics: /api/v1/dashboard/export
"""
from fastapi import APIRouter, Depends
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


@router.get("/summary", summary="Get full dashboard KPIs with drill-down breakdowns")
async def dashboard_summary(db: Prisma = Depends(get_db), _=Depends(ALL_ROLES)):
    return await get_dashboard_summary(db)


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