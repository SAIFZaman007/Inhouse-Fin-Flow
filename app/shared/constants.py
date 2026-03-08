from enum import Enum


class RoleEnum(str, Enum):
    CEO = "CEO"
    DIRECTOR = "DIRECTOR"
    HR = "HR"


class OrderStatusEnum(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PaymentStatusEnum(str, Enum):
    RECEIVED = "RECEIVED"
    DUE = "DUE"


# HR role has access to these modules only
HR_ALLOWED_MODULES = {"fiverr", "upwork", "outside_orders", "pmak", "hr_expense", "inventory"}