"""
app/shared/constants.py
========================
Application-wide enumerations and role access matrix.

Role Matrix (source of truth):
  CEO      — full access, all modules, all operations
  DIRECTOR — full access, all modules, all operations
  HR       — Fiverr profiles, Upwork profiles, PMAK (read + update status/notes),
             HR Expense, Inventory
  BDEV     — PMAK only (read + PATCH/update status/notes)
"""
from enum import Enum


class RoleEnum(str, Enum):
    CEO      = "CEO"
    DIRECTOR = "DIRECTOR"
    HR       = "HR"
    BDEV     = "BDEV"


class OrderStatusEnum(str, Enum):
    PENDING     = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED   = "COMPLETED"
    CANCELLED   = "CANCELLED"


class PaymentStatusEnum(str, Enum):
    RECEIVED = "RECEIVED"
    DUE      = "DUE"


class PmakTransactionStatus(str, Enum):
    """Status values for PMAK transactions — editable by HR and BDev."""
    PENDING  = "PENDING"
    CLEARED  = "CLEARED"
    REJECTED = "REJECTED"
    ON_HOLD  = "ON_HOLD"


class ExportPeriod(str, Enum):
    """Time-period granularity for Excel export endpoints."""
    DAILY   = "daily"
    WEEKLY  = "weekly"
    MONTHLY = "monthly"
    YEARLY  = "yearly"