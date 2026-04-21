"""
app/modules/outside_orders/router.py
================================================================================
v2 — Enterprise Edition

Endpoint matrix
───────────────────────────────────────────────────────────────────────────────
GET    /outside-orders                  HR_AND_ABOVE  Combined totals + paginated list.
                                                      Period + client_name + search
                                                      + order_status filters. Paginated.
POST   /outside-orders                  HR_AND_ABOVE  Create a new order.
GET    /outside-orders/{id}             HR_AND_ABOVE  Single order — full detail.
PATCH  /outside-orders/{id}            HR_AND_ABOVE  Partial update (any field).
DELETE /outside-orders/{id}            CEO_DIRECTOR  Hard delete — returns JSON message.
================================================================================
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR, HR_AND_ABOVE
from app.shared.filters import DateRangeFilter
from app.shared.pagination import PageParams

from .schema import OutsideOrderCreate, OutsideOrderUpdate
from .service import (
    create_order,
    delete_order,
    get_order,
    list_orders,
    update_order,
)

router = APIRouter(prefix="/outside-orders", tags=["Outside Orders"])


# ─────────────────────────────────────────────────────────────────────────────
# GET /outside-orders
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "",
    summary="Get Orders — combined totals + paginated list",
    description="""
Returns a **single response** containing:

- **Combined totals** across all matching orders for the selected period —
  `totalOrders`, `totalOrderAmount`, `totalReceiveAmount`, `totalDueAmount`,
  and `byStatus` breakdown (count + totalAmount per status).
- **Paginated order list** (50 per page by default), each row including
  `createdAt` and `updatedAt`.

### Search & Filter (all combinable)

| Parameter      | Behaviour                                                             |
|----------------|-----------------------------------------------------------------------|
| `client_name`  | Case-insensitive partial match on `clientName`                        |
| `search`       | Case-insensitive keyword search across `orderDetails` **OR** `orderSheet` simultaneously — a single keyword matches either column |
| `order_status` | Exact match: `PENDING` \\| `IN_PROGRESS` \\| `COMPLETED` \\| `CANCELLED` |
| Period params  | `daily` \\| `weekly` \\| `monthly` \\| `yearly` \\| `all` (default)      |

> **Totals guarantee:** aggregates are computed across the **full** matching set
> before pagination — values are identical on every page.

**Access:** HR and above.
    """,
)
async def get_orders(
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    client_name: Annotated[
        Optional[str],
        Query(description="Case-insensitive partial search on client name."),
    ] = None,
    search: Annotated[
        Optional[str],
        Query(
            description=(
                "Case-insensitive keyword search across orderDetails AND orderSheet "
                "(OR logic — a single keyword matches either column). "
                "e.g. ?search=invoice returns all rows whose orderDetails or "
                "orderSheet mention 'invoice'."
            )
        ),
    ] = None,
    order_status: Annotated[
        Optional[str],
        Query(description="Filter by status: PENDING | IN_PROGRESS | COMPLETED | CANCELLED."),
    ] = None,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await list_orders(
        db,
        filters,
        client_name=client_name,
        search=search,
        order_status=order_status,
        pagination=pagination,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /outside-orders
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "",
    status_code=201,
    summary="Add Order",
    description="""
Creates a new outside order.

### Required fields
`date`, `clientId`, `clientName`, `orderDetails`, `orderAmount`

### Optional fields
`clientLink`, `orderSheet` (Google Doc / Drive URL), `assignTeam`,
`orderStatus` (defaults to `PENDING`), `receiveAmount`, `dueAmount`,
`paymentMethod`, `paymentMethodDetails`

### Timestamps
`createdAt` and `updatedAt` are set automatically — callers do not supply them.

**Access:** HR and above.
    """,
)
async def add_order(
    body: OutsideOrderCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await create_order(db, body)


# ─────────────────────────────────────────────────────────────────────────────
# GET /outside-orders/{order_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{order_id}",
    summary="Get Order Detail",
    description="""
Returns the full detail for a single outside order by its ID.

Response includes all order fields plus `createdAt` and `updatedAt`.

Raises HTTP 404 if the order does not exist.

**Access:** HR and above.
    """,
)
async def get_order_detail(
    order_id: str,
    db:       Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_order(db, order_id)


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /outside-orders/{order_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.patch(
    "/{order_id}",
    summary="Update Order Endpoint",
    description="""
Performs a **partial update** on an existing outside order.

All fields are optional — only supplied fields are changed:

| Field | Effect |
|---|---|
| `date` | Changes the order date. |
| `clientId` | Updates the client ID. |
| `clientName` | Updates the client display name. |
| `clientLink` | Updates the client URL (send `null` to clear). |
| `orderDetails` | Updates the main order description. |
| `orderSheet` | Updates the document URL (send `null` to clear). |
| `assignTeam` | Updates the assigned team (send `null` to clear). |
| `orderStatus` | Updates lifecycle status: `PENDING` \\| `IN_PROGRESS` \\| `COMPLETED` \\| `CANCELLED`. |
| `orderAmount` | Updates the gross order amount in USD (must be > 0). |
| `receiveAmount` | Updates the received payment amount. |
| `dueAmount` | Updates the due amount. |
| `paymentMethod` | Updates the payment method (send `null` to clear). |
| `paymentMethodDetails` | Updates payment method details (send `null` to clear). |

Sending an empty body `{}` is accepted and returns the current order state
unchanged (idempotent).

`updatedAt` is bumped automatically on every successful write.

**Access:** HR and above.
    """,
)
async def update_order_endpoint(
    order_id: str,
    body:     OutsideOrderUpdate,
    db:       Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await update_order(db, order_id, body)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /outside-orders/{order_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/{order_id}",
    status_code=200,
    summary="Delete Outside Order (hard delete)",
    description="""
Permanently removes an outside order from the database.

> ⚠️ **This is a hard delete** — the record cannot be recovered.

Returns a JSON confirmation message on success.

**Access:** CEO and Director only.
    """,
)
async def delete_order_endpoint(
    order_id: str,
    db:       Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_order(db, order_id)
    return {
        "success":  True,
        "message":  "Outside order has been permanently deleted.",
        "orderId":  order_id,
    }