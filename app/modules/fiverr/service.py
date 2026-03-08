"""
app/modules/fiverr/service.py
"""
from fastapi import HTTPException
from prisma import Prisma

from .schema import FiverrOrderCreate, FiverrProfileCreate, FiverrSnapshotCreate


async def create_profile(db: Prisma, data: FiverrProfileCreate):
    existing = await db.fiverrprofile.find_unique(where={"profileName": data.profileName})
    if existing:
        raise HTTPException(status_code=409, detail="Profile name already exists")
    return await db.fiverrprofile.create(data={"profileName": data.profileName})


async def list_profiles(db: Prisma):
    profiles = await db.fiverrprofile.find_many(
        where={"isActive": True},
        include={"entries": {"take": 5}},
        order={"profileName": "asc"},
    )
    # Sort each profile's entries descending by date so the latest comes first
    for p in profiles:
        if p.entries:
            p.entries.sort(key=lambda e: e.date, reverse=True)
    return profiles


async def create_snapshot(db: Prisma, data: FiverrSnapshotCreate):
    profile = await db.fiverrprofile.find_unique(where={"id": data.profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Fiverr profile not found")

    entry_data = {
        "availableWithdraw": data.available_withdraw,
        "notCleared":        data.not_cleared,
        "activeOrders":      data.active_orders,
        "submitted":         data.submitted,
        "withdrawn":         data.withdrawn,
        "sellerPlus":        data.seller_plus,
        "promotion":         data.promotion,
    }

    # Upsert: update existing entry for same profile+date, or create new
    existing = await db.fiverrentry.find_first(
        where={"profileId": data.profile_id, "date": data.date}
    )
    if existing:
        return await db.fiverrentry.update(where={"id": existing.id}, data=entry_data)
    return await db.fiverrentry.create(
        data={"profileId": data.profile_id, "date": data.date, **entry_data}
    )


async def add_order(db: Prisma, data: FiverrOrderCreate):
    profile = await db.fiverrprofile.find_unique(where={"id": data.profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Fiverr profile not found")

    existing = await db.fiverrorder.find_unique(where={"orderId": data.order_id})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Order ID '{data.order_id}' already recorded",
        )

    return await db.fiverrorder.create(
        data={
            "profileId": data.profile_id,
            "date":      data.date,
            "buyerName": data.buyer_name,  
            "orderId":   data.order_id,
            "amount":    data.amount,
        }
    )


async def get_profile_snapshots(db: Prisma, profile_id: str, date_filter: dict):
    profile = await db.fiverrprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    where: dict = {"profileId": profile_id}
    if date_filter:
        where["date"] = date_filter
    return await db.fiverrentry.find_many(where=where, order={"date": "desc"})


async def get_profile_orders(db: Prisma, profile_id: str, date_filter: dict):
    where: dict = {"profileId": profile_id}
    if date_filter:
        where["date"] = date_filter
    return await db.fiverrorder.find_many(where=where, order={"date": "desc"})


async def deactivate_profile(db: Prisma, profile_id: str):
    profile = await db.fiverrprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return await db.fiverrprofile.update(
        where={"id": profile_id}, data={"isActive": False}
    )