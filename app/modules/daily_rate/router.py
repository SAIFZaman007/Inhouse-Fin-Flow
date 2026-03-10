"""
app/modules/daily_rate/router.py
---------------------------------
Endpoints for HR-managed daily USD→BDT exchange rate.

Role access:
  GET  /current           → ALL_ROLES  (dashboard needs it)
  GET  /                  → HR_AND_ABOVE
  GET  /{rate_id}         → HR_AND_ABOVE
  POST /                  → HR_AND_ABOVE  (set today's rate)
  PATCH /{rate_id}        → HR_AND_ABOVE
  DELETE /{rate_id}       → CEO_DIRECTOR
  GET  /convert           → ALL_ROLES
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import ALL_ROLES, CEO_DIRECTOR, HR_AND_ABOVE

from .schema import DailyRateCreate, DailyRateResponse, DailyRateUpdate
from .service import (
    convert_usd_to_bdt, delete_rate, get_current_rate, get_rate_for_date,
    list_rates, update_rate, upsert_rate,
)

router = APIRouter(prefix="/daily-rate", tags=["Daily Rate (USD→BDT)"])


@router.get("/current", response_model=DailyRateResponse, summary="Latest HR-set USD→BDT rate")
async def current_rate(db: Prisma = Depends(get_db), _=Depends(ALL_ROLES)):
    return await get_current_rate(db)


@router.get("/convert", summary="Convert USD amount to BDT using latest rate")
async def convert(
    usd: float = Query(..., gt=0, description="USD amount to convert"),
    db: Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await convert_usd_to_bdt(db, usd)


@router.get("", response_model=list[DailyRateResponse], summary="List recent daily rates")
async def list_all_rates(
    limit: int = Query(default=30, ge=1, le=365),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await list_rates(db, limit)


@router.post("", response_model=DailyRateResponse, status_code=201,
             summary="Set today\'s USD→BDT rate (HR only)")
async def set_rate(
    body: DailyRateCreate,
    db: Prisma = Depends(get_db),
    current_user=Depends(HR_AND_ABOVE),
):
    # Pass current user email for audit trail
    user_email = getattr(current_user, "email", None)
    return await upsert_rate(db, body, set_by_email=user_email)


@router.get("/{rate_id}", response_model=DailyRateResponse)
async def get_rate(rate_id: str, db: Prisma = Depends(get_db), _=Depends(HR_AND_ABOVE)):
    return await get_rate_for_date(db, rate_id)


@router.patch("/{rate_id}", response_model=DailyRateResponse)
async def patch_rate(
    rate_id: str,
    body: DailyRateUpdate,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await update_rate(db, rate_id, body)


@router.delete("/{rate_id}", status_code=204)
async def remove_rate(rate_id: str, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)):
    await delete_rate(db, rate_id)