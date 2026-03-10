"""
app/modules/upwork/router.py

Role matrix:
  GET  profiles / snapshots / orders  → HR_AND_ABOVE
  POST profiles                       → CEO_DIRECTOR
  DELETE profiles                     → CEO_DIRECTOR
  POST snapshots / orders             → HR_AND_ABOVE
"""
from fastapi import APIRouter, Depends
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR, HR_AND_ABOVE
from app.shared.filters import DateRangeFilter

from .schema import (
    UpworkOrderCreate, UpworkOrderResponse,
    UpworkProfileCreate, UpworkProfileResponse,
    UpworkSnapshotCreate, UpworkSnapshotResponse,
)
from .service import (
    add_order, create_profile, create_snapshot,
    deactivate_profile, get_profile_orders, get_profile_snapshots, list_profiles,
)

router = APIRouter(prefix="/upwork", tags=["Upwork"])


@router.get("/profiles", response_model=list[UpworkProfileResponse])
async def get_profiles(db: Prisma = Depends(get_db), _=Depends(HR_AND_ABOVE)):
    return await list_profiles(db)


@router.post("/profiles", response_model=UpworkProfileResponse, status_code=201)
async def add_profile(
    body: UpworkProfileCreate,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await create_profile(db, body)


@router.delete("/profiles/{profile_id}", status_code=204)
async def remove_profile(
    profile_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await deactivate_profile(db, profile_id)


@router.post("/snapshots", response_model=UpworkSnapshotResponse, status_code=201)
async def add_snapshot(
    body: UpworkSnapshotCreate,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await create_snapshot(db, body)


@router.get(
    "/profiles/{profile_id}/snapshots",
    response_model=list[UpworkSnapshotResponse],
)
async def profile_snapshots(
    profile_id: str,
    filters: DateRangeFilter = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_profile_snapshots(db, profile_id, filters.to_prisma_filter())


@router.post("/orders", response_model=UpworkOrderResponse, status_code=201)
async def add_order_entry(
    body: UpworkOrderCreate,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await add_order(db, body)


@router.get(
    "/profiles/{profile_id}/orders",
    response_model=list[UpworkOrderResponse],
)
async def profile_orders(
    profile_id: str,
    filters: DateRangeFilter = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_profile_orders(db, profile_id, filters.to_prisma_filter())