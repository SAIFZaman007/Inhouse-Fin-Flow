"""
app/modules/pmak/router.py

Role enforcement:
  GET  /accounts                          → PMAK_EDITORS (all roles)
  POST /accounts                          → CEO_DIRECTOR
  POST /transactions                      → HR_AND_ABOVE (CEO/DIRECTOR/HR — not BDev)
  GET  /accounts/{id}/transactions        → PMAK_EDITORS
  PATCH /transactions/{id}/status         → PMAK_EDITORS  ← BDev entry-point
  DELETE /transactions/{id}              → CEO_DIRECTOR
"""
from fastapi import APIRouter, Depends
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR, HR_AND_ABOVE, PMAK_EDITORS
from app.shared.filters import DateRangeFilter

from .schema import (
    PmakAccountCreate, PmakAccountResponse,
    PmakTransactionCreate, PmakTransactionResponse,
    PmakTransactionStatusUpdate,
)
from .service import (
    add_transaction, create_account, delete_transaction,
    get_account_transactions, list_accounts, update_transaction_status,
)

router = APIRouter(prefix="/pmak", tags=["PMAK"])


@router.get("/accounts", response_model=list[PmakAccountResponse])
async def get_accounts(db: Prisma = Depends(get_db), _=Depends(PMAK_EDITORS)):
    return await list_accounts(db)


@router.post("/accounts", response_model=PmakAccountResponse, status_code=201)
async def add_account(
    body: PmakAccountCreate,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await create_account(db, body)


@router.post("/transactions", response_model=PmakTransactionResponse, status_code=201)
async def add_transaction_entry(
    body: PmakTransactionCreate,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),   # BDev may NOT create transactions
):
    return await add_transaction(db, body)


@router.get(
    "/accounts/{account_id}/transactions",
    response_model=list[PmakTransactionResponse],
)
async def account_transactions(
    account_id: str,
    filters: DateRangeFilter = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    return await get_account_transactions(db, account_id, filters.to_prisma_filter())


@router.patch(
    "/transactions/{transaction_id}/status",
    response_model=PmakTransactionResponse,
    summary="Update transaction status/notes — accessible by BDev, HR, CEO, Director",
)
async def patch_transaction_status(
    transaction_id: str,
    body: PmakTransactionStatusUpdate,
    db: Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),   # BDev + HR + CEO + DIRECTOR
):
    return await update_transaction_status(db, transaction_id, body)


@router.delete("/transactions/{transaction_id}", status_code=204)
async def remove_transaction(
    transaction_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),   # BDev / HR cannot delete
):
    await delete_transaction(db, transaction_id)