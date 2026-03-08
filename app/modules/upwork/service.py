"""
app/modules/upwork/service.py
"""
from fastapi import HTTPException
from prisma import Prisma

from .schema import UpworkOrderCreate, UpworkProfileCreate, UpworkSnapshotCreate


async def create_profile(db: Prisma, data: UpworkProfileCreate):
    existing = await db.upworkprofile.find_unique(where={"profileName": data.profileName})
    if existing:
        raise HTTPException(status_code=409, detail="Profile name already exists")
    return await db.upworkprofile.create(data={"profileName": data.profileName})


async def list_profiles(db: Prisma):
    profiles = await db.upworkprofile.find_many(
        where={"isActive": True},
        include={"entries": {"take": 5}},
        order={"profileName": "asc"},
    )
    # Sort each profile's entries descending by date so the latest comes first
    for p in profiles:
        if p.entries:
            p.entries.sort(key=lambda e: e.date, reverse=True)
    return profiles


async def create_snapshot(db: Prisma, data: UpworkSnapshotCreate):
    profile = await db.upworkprofile.find_unique(where={"id": data.profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Upwork profile not found")

    entry_data = {
        "availableWithdraw": data.available_withdraw,
        "pending":           data.pending,
        "inReview":          data.in_review,
        "workInProgress":    data.work_in_progress,
        "withdrawn":         data.withdrawn,
        "connects":          data.connects, 
        "upworkPlus":        data.upwork_plus,
    }

    # Upsert: update existing entry for same profile+date, or create new
    existing = await db.upworkentry.find_first(
        where={"profileId": data.profile_id, "date": data.date}
    )
    if existing:
        return await db.upworkentry.update(where={"id": existing.id}, data=entry_data)
    return await db.upworkentry.create(
        data={"profileId": data.profile_id, "date": data.date, **entry_data}
    )


async def add_order(db: Prisma, data: UpworkOrderCreate):
    profile = await db.upworkprofile.find_unique(where={"id": data.profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Upwork profile not found")

    existing = await db.upworkorder.find_unique(where={"orderId": data.order_id})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Order ID '{data.order_id}' already recorded",
        )

    return await db.upworkorder.create(
        data={
            "profileId":  data.profile_id,
            "date":       data.date,
            "clientName": data.client_name,
            "orderId":    data.order_id,
            "amount":     data.amount,
        }
    )


async def get_profile_snapshots(db: Prisma, profile_id: str, date_filter: dict):
    profile = await db.upworkprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    where: dict = {"profileId": profile_id}
    if date_filter:
        where["date"] = date_filter
    return await db.upworkentry.find_many(where=where, order={"date": "desc"})


async def get_profile_orders(db: Prisma, profile_id: str, date_filter: dict):
    where: dict = {"profileId": profile_id}
    if date_filter:
        where["date"] = date_filter
    return await db.upworkorder.find_many(where=where, order={"date": "desc"})


async def deactivate_profile(db: Prisma, profile_id: str):
    profile = await db.upworkprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return await db.upworkprofile.update(
        where={"id": profile_id}, data={"isActive": False}
    )