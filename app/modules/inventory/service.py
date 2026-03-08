"""
app/modules/inventory/service.py

All field names verified against schema.prisma (model Inventory):
  date, itemName, category, quantity, unitPrice, totalPrice,
  condition, assignedTo, notes, createdAt, updatedAt
"""
from fastapi import HTTPException
from prisma import Prisma

from .schema import InventoryCreate, InventoryUpdate


async def list_inventory(db: Prisma, date_filter: dict):
    where: dict = {}
    if date_filter:
        where["date"] = date_filter
    return await db.inventory.find_many(where=where, order={"date": "desc"})


async def create_item(db: Prisma, data: InventoryCreate):
    return await db.inventory.create(
        data={
            "date":       data.date,
            "itemName":   data.itemName,            # schema: itemName
            "category":   data.category,
            "quantity":   data.quantity,
            "unitPrice":  data.unitPrice,           # schema: unitPrice
            "totalPrice": data.totalPrice,          # schema: totalPrice (computed in schema)
            "condition":  data.condition,
            "assignedTo": data.assignedTo,          # schema: assignedTo
            "notes":      data.notes,
        }
    )


async def update_item(db: Prisma, item_id: str, data: InventoryUpdate):
    existing = await db.inventory.find_unique(where={"id": item_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    update_data = data.model_dump(exclude_none=True)

    # Recompute totalPrice if quantity or unitPrice changed
    new_quantity = update_data.get("quantity", existing.quantity)
    new_unit_price = update_data.get("unitPrice", existing.unitPrice)
    update_data["totalPrice"] = new_unit_price * new_quantity

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