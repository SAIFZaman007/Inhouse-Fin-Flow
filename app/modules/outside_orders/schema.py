from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, model_validator
from app.shared.constants import OrderStatusEnum, PaymentStatusEnum


class OutsideOrderCreate(BaseModel):
    client_id: str
    client_name: str
    client_link: Optional[str] = None
    order_details: str
    order_sheet: Optional[str] = None
    assign_team: Optional[str] = None
    status: OrderStatusEnum = OrderStatusEnum.PENDING
    order_amount: Decimal
    receive_amount: Decimal = Decimal("0")
    payment_method: Optional[str] = None
    payment_method_details: Optional[str] = None
    date: date

    @model_validator(mode="after")
    def compute_due(self):
        self.due_amount = self.order_amount - self.receive_amount
        return self

    due_amount: Decimal = Decimal("0")


class OutsideOrderUpdate(BaseModel):
    client_name: Optional[str] = None
    client_link: Optional[str] = None
    order_details: Optional[str] = None
    order_sheet: Optional[str] = None
    assign_team: Optional[str] = None
    status: Optional[OrderStatusEnum] = None
    order_amount: Optional[Decimal] = None
    receive_amount: Optional[Decimal] = None
    payment_method: Optional[str] = None
    payment_method_details: Optional[str] = None


class OutsideOrderResponse(BaseModel):
    id: str
    clientId: str
    clientName: str
    clientLink: Optional[str]
    orderDetails: str
    orderSheet: Optional[str]
    assignTeam: Optional[str]
    orderStatus: str
    orderAmount: Decimal
    receiveAmount: Decimal
    dueAmount: Decimal
    paymentMethod: Optional[str]
    paymentMethodDetails: Optional[str]
    date: date

    class Config:
        from_attributes = True