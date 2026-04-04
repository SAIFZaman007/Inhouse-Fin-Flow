"""
app/modules/hr_expense/router.py
========================================
v3 — totals on GET + full PATCH support

  • GET    /hr-expense              → ALL_ROLES
      Returns HrExpenseListResponse: { totals: {...}, records: [...] }
      totals includes: totalRecords, totalDebits, totalCredits, totalRemainingBalance

  • POST   /hr-expense              → HR_AND_ABOVE (CEO, DIRECTOR, HR — excludes BDEV)
      All fields optional — safe defaults applied for omitted values.

  • PATCH  /hr-expense/{expense_id} → HR_AND_ABOVE
      Full partial update: date, details, accountFrom, accountTo,
      debit, credit, remaining_balance, remarks — all patchable.

  • DELETE /hr-expense/{expense_id} → HR_AND_ABOVE + structured response body
"""
from fastapi import APIRouter, Depends
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import ALL_ROLES, HR_AND_ABOVE
from app.shared.filters import DateRangeFilter

from .schema import HrExpenseCreate, HrExpenseListResponse, HrExpenseResponse, HrExpenseUpdate
from .service import create_expense, delete_expense, list_expenses, update_expense

router = APIRouter(prefix="/hr-expense", tags=["HR Expense"])


@router.get("", response_model=HrExpenseListResponse)
async def get_expenses(
    filters: DateRangeFilter = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    """
    List all HR expense records within the requested date range.

    Response envelope:
    - **totals.totalRecords**          — number of records in the window
    - **totals.totalDebits**           — sum of all debit entries
    - **totals.totalCredits**          — sum of all credit entries
    - **totals.totalRemainingBalance** — sum(remainingBalance) + totalCredits − totalDebits
    - **records**                      — full list of expense records (newest first)
    """
    return await list_expenses(db, filters.to_prisma_filter())


@router.post("", response_model=HrExpenseResponse, status_code=201)
async def add_expense(
    body: HrExpenseCreate,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    """
    Create an HR expense record.

    All fields are optional — omitted fields receive safe defaults:
    - **date** defaults to today
    - **details** defaults to an empty string
    - **debit** / **credit** default to `0`
    - **remaining_balance** defaults to `0`

    Accessible by: CEO, DIRECTOR, HR (BDEV excluded).
    """
    return await create_expense(db, body)


@router.patch("/{expense_id}", response_model=HrExpenseResponse)
async def edit_expense(
    expense_id: str,
    body: HrExpenseUpdate,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    """
    Partially update an HR expense record.

    Any combination of the following fields may be patched in a single request:
    `date`, `details`, `accountFrom`, `accountTo`, `debit`, `credit`,
    `remaining_balance`, `remarks`.

    Only the fields present in the request body are written; all others remain
    unchanged. Sending an empty body is a no-op — the existing record is returned.

    Accessible by: CEO, DIRECTOR, HR (BDEV excluded).
    """
    return await update_expense(db, expense_id, body)


@router.delete("/{expense_id}", status_code=200)
async def remove_expense(
    expense_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    """
    Delete an HR expense record.

    Accessible by: CEO, DIRECTOR, HR (BDEV excluded).
    Returns a structured success message.
    """
    await delete_expense(db, expense_id)
    return {
        "success": True,
        "message": "HR expense record deleted successfully.",
        "id": expense_id,
    }