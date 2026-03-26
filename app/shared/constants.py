"""
app/shared/constants.py
════════════════════════════════════════════════════════════════════════════════
Shared enums used across modules.
════════════════════════════════════════════════════════════════════════════════
"""
from enum import Enum
from typing import Final

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
    

# Default visible modules per role (used for seed + documentation)
# The actual live values live in the DB (PermissionRule rows).
ROLE_DEFAULT_MODULES: dict[str, set[str]] = {
    "CEO": {
        "dashboard", "fiverr", "upwork", "payoneer", "pmak",
        "pmak_inhouse", "outside_orders", "card_sharing",
        "dollar_exchange", "hr_expense", "inventory",
    },
    "DIRECTOR": {
        "dashboard", "fiverr", "upwork", "payoneer", "pmak",
        "pmak_inhouse", "outside_orders", "card_sharing",
        "dollar_exchange", "hr_expense", "inventory",
    },
    "HR": {
        "fiverr", "upwork", "outside_orders", "pmak", "pmak_inhouse", "hr_expense", "inventory",
    },
    "BDEV": {
        "pmak", "pmak_inhouse",
    },
}

HR_ALLOWED_MODULES = ROLE_DEFAULT_MODULES["HR"]
    
# Backward-compatible aliases
OrderStatusEnum = OrderStatus
PaymentStatusEnum = PaymentStatus
OrderStatusEnum = OrderStatus