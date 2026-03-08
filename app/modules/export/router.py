from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR

from .service import build_export

router = APIRouter(prefix="/export", tags=["Export"])

VALID_PERIODS = {"daily", "monthly", "yearly"}


@router.get(
    "/{period}",
    summary="Export financial data as Excel (.xlsx)",
    description="period must be: daily | monthly | yearly. target_date defaults to today.",
    responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}},
)
async def export_excel(
    period: str,
    target_date: date = Query(default=None, description="YYYY-MM-DD (defaults to today)"),
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    if period not in VALID_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period '{period}'. Must be one of: {', '.join(VALID_PERIODS)}",
        )

    if target_date is None:
        target_date = date.today()

    xlsx_bytes = await build_export(db, period, target_date)
    filename = f"MAKTech_Financial_{period.title()}_{target_date}.xlsx"

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )