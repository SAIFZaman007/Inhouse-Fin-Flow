"""
app/modules/outside_orders/schema.py
================================================================================
v2 — Enterprise Edition
================================================================================
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from prisma.enums import OrderStatus


# ─────────────────────────────────────────────────────────────────────────────
# Create
# ─────────────────────────────────────────────────────────────────────────────

class OutsideOrderCreate(BaseModel):
    """
    POST /outside-orders — create a new outside order.

    ``clientId`` and ``clientName`` uniquely identify the client.
    ``orderDetails`` is the main description field — case-insensitively
    searchable via ``?search=`` on GET endpoints.
    ``orderSheet`` is an optional URL (Google Doc, Drive link, etc.) —
    also case-insensitively searchable via ``?search=``.
    ``orderAmount`` is the gross value in USD.
    ``receiveAmount`` / ``dueAmount`` track payment flow.
    """
    date:                date
    clientId:            str            = Field(..., min_length=1, max_length=100)
    clientName:          str            = Field(..., min_length=1, max_length=200)
    clientLink:          Optional[str]  = Field(default=None)
    orderDetails:        str            = Field(..., min_length=1)
    orderSheet:          Optional[str]  = Field(
        default=None,
        description="Documented order link (Google Doc, Drive URL, etc.).",
    )
    assignTeam:          Optional[str]  = Field(default=None)
    orderStatus:         OrderStatus    = Field(default=OrderStatus.PENDING)
    orderAmount:         Decimal        = Field(..., gt=0, description="Gross order value in USD.")
    receiveAmount:       Decimal        = Field(default=Decimal("0"), ge=0)
    dueAmount:           Decimal        = Field(default=Decimal("0"), ge=0)
    paymentMethod:       Optional[str]  = Field(default=None)
    paymentMethodDetails: Optional[str] = Field(default=None)


# ─────────────────────────────────────────────────────────────────────────────
# Update
# ─────────────────────────────────────────────────────────────────────────────

class OutsideOrderUpdate(BaseModel):
    """
    PATCH /outside-orders/{id} — partial update.

    All fields are optional — only supplied fields are written.
    Sending an empty body ``{}`` is accepted and returns the current state
    unchanged (idempotent).
    """
    date:                Optional[date]        = None
    clientId:            Optional[str]         = Field(default=None, min_length=1, max_length=100)
    clientName:          Optional[str]         = Field(default=None, min_length=1, max_length=200)
    clientLink:          Optional[str]         = None
    orderDetails:        Optional[str]         = Field(default=None, min_length=1)
    orderSheet:          Optional[str]         = None
    assignTeam:          Optional[str]         = None
    orderStatus:         Optional[OrderStatus] = None
    orderAmount:         Optional[Decimal]     = Field(default=None, gt=0)
    receiveAmount:       Optional[Decimal]     = Field(default=None, ge=0)
    dueAmount:           Optional[Decimal]     = Field(default=None, ge=0)
    paymentMethod:       Optional[str]         = None
    paymentMethodDetails: Optional[str]        = None


# ─────────────────────────────────────────────────────────────────────────────
# Response
# ─────────────────────────────────────────────────────────────────────────────

class OutsideOrderResponse(BaseModel):
    """
    Full outside-order row returned by every write and read endpoint.

    ``createdAt`` and ``updatedAt`` are native Prisma columns on the
    ``OutsideOrder`` model — both are populated automatically by the database
    and returned on every response with no extra service-layer work.
    """
    id:                  str
    date:                date
    clientId:            str
    clientName:          str
    clientLink:          Optional[str]
    orderDetails:        str
    orderSheet:          Optional[str]
    assignTeam:          Optional[str]
    orderStatus:         OrderStatus
    orderAmount:         Decimal
    receiveAmount:       Decimal
    dueAmount:           Decimal
    paymentMethod:       Optional[str]
    paymentMethodDetails: Optional[str]
    createdAt:           datetime
    updatedAt:           datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# List envelope  GET /outside-orders
# ─────────────────────────────────────────────────────────────────────────────

class OutsideOrderStatusBreakdown(BaseModel):
    """Row-count and gross amount for one ``OrderStatus`` value."""
    count:       int
    totalAmount: float


class OutsideOrderTotals(BaseModel):
    """Cross-order aggregates for the active filter + period window."""
    totalOrders:        int
    totalOrderAmount:   float
    totalReceiveAmount: float
    totalDueAmount:     float
    byStatus:           Dict[str, OutsideOrderStatusBreakdown]
    # byStatus keys: PENDING | IN_PROGRESS | COMPLETED | CANCELLED


class OutsideOrderListResponse(BaseModel):
    """Top-level envelope for GET /outside-orders."""
    filter:     Dict[str, Any]
    totals:     OutsideOrderTotals
    pagination: Dict[str, Any]
    orders:     List[OutsideOrderResponse]