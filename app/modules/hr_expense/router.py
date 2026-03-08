"""app/modules/hr_expense/router.py"""
from fastapi import APIRouter, Depends
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import ALL_ROLES, CEO_DIRECTOR
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
    _=Depends(CEO_DIRECTOR),
):
    return await create_expense(db, body)


@router.patch("/{expense_id}", response_model=HrExpenseResponse)
async def edit_expense(
    expense_id: str,
    body: HrExpenseUpdate,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await update_expense(db, expense_id, body)


@router.delete("/{expense_id}", status_code=204)
async def remove_expense(
    expense_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_expense(db, expense_id)