"""
app/modules/role_matrix/constants.py
======================================
Single source of truth for every module name recognised by the role matrix.

`MODULES` drives:
  - DB seed / upsert (initial rows)
  - Validation of `moduleName` in create/update endpoints
  - Frontend module-name autocomplete
"""
from typing import Final

# Canonical module identifiers — snake_case, lower-cased
MODULE_DASHBOARD      : Final = "dashboard"
MODULE_FIVERR         : Final = "fiverr"
MODULE_UPWORK         : Final = "upwork"
MODULE_PAYONEER       : Final = "payoneer"
MODULE_PMAK           : Final = "pmak"
MODULE_PMAK_INHOUSE   : Final = "pmak_inhouse"
MODULE_OUTSIDE_ORDERS : Final = "outside_orders"
MODULE_CARD_SHARING   : Final = "card_sharing"
MODULE_DOLLAR_EXCHANGE: Final = "dollar_exchange"
MODULE_HR_EXPENSE     : Final = "hr_expense"
MODULE_INVENTORY      : Final = "inventory"

# Ordered list — matches displayOrder (0-based index)
MODULES: Final[list[str]] = [
    MODULE_DASHBOARD,        # 0
    MODULE_FIVERR,           # 1
    MODULE_UPWORK,           # 2
    MODULE_PAYONEER,         # 3
    MODULE_PMAK,             # 4
    MODULE_PMAK_INHOUSE,     # 5
    MODULE_OUTSIDE_ORDERS,   # 6
    MODULE_CARD_SHARING,     # 7
    MODULE_DOLLAR_EXCHANGE,  # 8
    MODULE_HR_EXPENSE,       # 9
    MODULE_INVENTORY,        # 10
]

MODULE_SET: Final[set[str]] = set(MODULES)

# Human-readable labels used in API responses
MODULE_LABELS: Final[dict[str, str]] = {
    MODULE_DASHBOARD:       "Dashboard",
    MODULE_FIVERR:          "Fiverr",
    MODULE_UPWORK:          "Upwork",
    MODULE_PAYONEER:        "Payoneer",
    MODULE_PMAK:            "PMAK",
    MODULE_PMAK_INHOUSE:    "PMAK Inhouse",
    MODULE_OUTSIDE_ORDERS:  "Outside Orders",
    MODULE_CARD_SHARING:    "Card Sharing",
    MODULE_DOLLAR_EXCHANGE: "Dollar Exchange",
    MODULE_HR_EXPENSE:      "HR Expense",
    MODULE_INVENTORY:       "Inventory",
}