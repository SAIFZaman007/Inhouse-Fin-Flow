"""
app/modules/inventory/service.py
========================================
v2 — date + Decimal serialization fix

DateTime @db.Date fields in prisma-py v0.14.0 MUST be passed as
datetime.datetime objects (midnight), using the same pattern as the
working Fiverr module:

    datetime.combine(data.date, time.min)

Decimal fields must be cast to float before being passed to the builder.

All field names verified against schema.prisma (model Inventory):
  date, itemName, category, quantity, unitPrice, totalPrice,
  condition, assignedTo, notes, createdAt, updatedAt
"""
from datetime import date as dt_date, datetime, time
from decimal import Decimal

from fastapi import HTTPException
from prisma import Prisma

from .schema import InventoryCreate, InventoryUpdate


# ── Date helper ───────────────────────────────────────────────────────────────

def _dt(d: dt_date) -> datetime:
    """
    Convert datetime.date → datetime.datetime at midnight.

    prisma-py v0.14.0 requires a full datetime object for every
    DateTime @db.Date field — the same pattern used across the Fiverr
    module: datetime.combine(d, time.min).
    """
    return datetime.combine(d, time.min)


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def list_inventory(db: Prisma, date_filter: dict):
    where: dict = {}
    if date_filter:
        where["date"] = date_filter
    return await db.inventory.find_many(where=where, order={"date": "desc"})


async def create_item(db: Prisma, data: InventoryCreate):
    return await db.inventory.create(
        data={
            "date":       _dt(data.date),            # ← datetime.combine(date, time.min)
            "itemName":   data.itemName,
            "category":   data.category,
            "quantity":   data.quantity,
            "unitPrice":  float(data.unitPrice),     # ← Decimal not serializable
            "totalPrice": float(data.totalPrice),    # ← Decimal not serializable
            "condition":  data.condition,
            "assignedTo": data.assignedTo,
            "notes":      data.notes,
        }
    )


async def update_item(db: Prisma, item_id: str, data: InventoryUpdate):
    existing = await db.inventory.find_unique(where={"id": item_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    update_data = data.model_dump(exclude_none=True)

    # Cast any Decimal values to float before they reach the prisma-py builder
    for key in ("unitPrice", "totalPrice"):
        if key in update_data and isinstance(update_data[key], Decimal):
            update_data[key] = float(update_data[key])

    # Recompute totalPrice if quantity or unitPrice changed
    new_quantity   = update_data.get("quantity",  existing.quantity)
    new_unit_price = update_data.get("unitPrice", float(existing.unitPrice))
    update_data["totalPrice"] = float(new_unit_price) * int(new_quantity)

    return await db.inventory.update(where={"id": item_id}, data=update_data)


async def delete_item(db: Prisma, item_id: str):
    existing = await db.inventory.find_unique(where={"id": item_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    await db.inventory.delete(where={"id": item_id})


async def get_item(db: Prisma, item_id: str):
    item = await db.inventory.find_unique(where={"id": item_id})
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    return item