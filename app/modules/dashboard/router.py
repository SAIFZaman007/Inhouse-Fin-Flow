from fastapi import APIRouter, Depends
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import ALL_ROLES

from .service import get_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", summary="Get full dashboard KPIs with drill-down breakdowns")
async def dashboard_summary(db: Prisma = Depends(get_db), _=Depends(ALL_ROLES)):
    return await get_dashboard_summary(db)