"""
app/shared/constants.py
════════════════════════════════════════════════════════════════════════════════
Shared enums used across modules.

v3 changes:
  PmakTransactionStatus renamed → PmakStatus (matches Prisma enum name)
  InhouseOrderStatus added (for PmakInhouse.orderStatus)
  PmakTransactionStatus kept as alias for backward compatibility
════════════════════════════════════════════════════════════════════════════════
"""
from enum import Enum

class RoleEnum(str, Enum):
    """User roles in the system."""
    CEO = "CEO"
    MANAGER = "DIRECTOR"
    HR = "HR"
    BDEV = "BDEV"

class ExportPeriod(str, Enum):
    DAILY   = "daily"
    WEEKLY  = "weekly"
    MONTHLY = "monthly"
    YEARLY  = "yearly"
    ALL     = "all"

class PmakStatus(str, Enum):
    """Lifecycle status for PMAK ledger transactions."""
    PENDING  = "PENDING"
    CLEARED  = "CLEARED"
    ON_HOLD  = "ON_HOLD"
    REJECTED = "REJECTED"

# Backward-compatible alias — existing code using PmakTransactionStatus still works
PmakTransactionStatus = PmakStatus

class InhouseOrderStatus(str, Enum):
    """Lifecycle status for PMAK inhouse deals."""
    PENDING     = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED   = "COMPLETED"
    CANCELLED   = "CANCELLED"


class OrderStatus(str, Enum):
    PENDING     = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED   = "COMPLETED"
    CANCELLED   = "CANCELLED"


class PaymentStatus(str, Enum):
    RECEIVED = "RECEIVED"
    DUE      = "DUE"
    
# Backward-compatible aliases
OrderStatusEnum = OrderStatus
PaymentStatusEnum = PaymentStatus
OrderStatusEnum = OrderStatus