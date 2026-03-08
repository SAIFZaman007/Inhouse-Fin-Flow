from fastapi import HTTPException
from prisma import Prisma

from .schema import OutsideOrderCreate, OutsideOrderUpdate


async def create_order(db: Prisma, data: OutsideOrderCreate):
    existing = await db.outsideorder.find_unique(where={"clientId": data.client_id})
    if existing:
        raise HTTPException(status_code=409, detail=f"Client ID '{data.client_id}' already exists")

    due = float(data.order_amount) - float(data.receive_amount)
    return await db.outsideorder.create(
        data={
            "clientId": data.client_id,
            "clientName": data.client_name,
            "clientLink": data.client_link,
            "orderDetails": data.order_details,
            "orderSheet": data.order_sheet,
            "assignTeam": data.assign_team,
            "status": data.status,
            "orderAmount": data.order_amount,
            "receiveAmount": data.receive_amount,
            "dueAmount": due,
            "paymentMethod": data.payment_method,
            "paymentMethodDetails": data.payment_method_details,
            "date": data.date,
        }
    )


async def list_orders(db: Prisma, date_filter: dict, status: str | None = None):
    where: dict = {}
    if date_filter:
        where["date"] = date_filter
    if status:
        where["status"] = status
    return await db.outsideorder.find_many(where=where, order={"date": "desc"})


async def get_order(db: Prisma, order_id: str):
    order = await db.outsideorder.find_unique(where={"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


async def update_order(db: Prisma, order_id: str, data: OutsideOrderUpdate):
    order = await get_order(db, order_id)

    # Build update dict with only provided fields (camelCase for Prisma)
    update_data: dict = {}
    if data.client_name is not None:
        update_data["clientName"] = data.client_name
    if data.client_link is not None:
        update_data["clientLink"] = data.client_link
    if data.order_details is not None:
        update_data["orderDetails"] = data.order_details
    if data.order_sheet is not None:
        update_data["orderSheet"] = data.order_sheet
    if data.assign_team is not None:
        update_data["assignTeam"] = data.assign_team
    if data.status is not None:
        update_data["status"] = data.status
    if data.payment_method is not None:
        update_data["paymentMethod"] = data.payment_method
    if data.payment_method_details is not None:
        update_data["paymentMethodDetails"] = data.payment_method_details

    # Recompute due amount
    order_amount = float(data.order_amount) if data.order_amount is not None else float(order.orderAmount)
    receive_amount = float(data.receive_amount) if data.receive_amount is not None else float(order.receiveAmount)

    if data.order_amount is not None:
        update_data["orderAmount"] = data.order_amount
    if data.receive_amount is not None:
        update_data["receiveAmount"] = data.receive_amount

    update_data["dueAmount"] = order_amount - receive_amount

    return await db.outsideorder.update(where={"id": order_id}, data=update_data)


async def delete_order(db: Prisma, order_id: str):
    await get_order(db, order_id)
    await db.outsideorder.delete(where={"id": order_id})