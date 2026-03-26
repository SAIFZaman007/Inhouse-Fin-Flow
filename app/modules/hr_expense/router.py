"""
app/modules/hr_expense/router.py
========================================
v2 — Role & response-body changes:
  • GET    /hr-expense              → ALL_ROLES (unchanged)
  • POST   /hr-expense              → HR_AND_ABOVE (CEO, DIRECTOR, HR — excludes BDEV)
  • PATCH  /hr-expense/{expense_id} → HR_AND_ABOVE
  • DELETE /hr-expense/{expense_id} → HR_AND_ABOVE + structured response body
"""
from fastapi import APIRouter, Depends
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import ALL_ROLES, HR_AND_ABOVE
from app.shared.filters import DateRangeFilter

from .schema import HrExpenseCreate, HrExpenseResponse, HrExpenseUpdate
from .service import create_expense, delete_expense, list_expenses, update_expense

router = APIRouter(prefix="/hr-expense", tags=["HR Expense"])


@router.get("", response_model=list[HrExpenseResponse])
async def get_expenses(
    filters: DateRangeFilter = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await list_expenses(db, filters.to_prisma_filter())


@router.post("", response_model=HrExpenseResponse, status_code=201)
async def add_expense(
    body: HrExpenseCreate,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    """
    Create an HR expense record.

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