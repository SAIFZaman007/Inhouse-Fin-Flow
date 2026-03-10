"""
app/modules/pmak/service.py

Changes:
  - add_transaction now persists `status` and `notes`
  - New update_transaction_status() — the only write BDev may perform
  - get_account_transactions orders desc by date (consistent with other modules)
"""
from fastapi import HTTPException
from prisma import Prisma

from .schema import PmakAccountCreate, PmakTransactionCreate, PmakTransactionStatusUpdate


async def create_account(db: Prisma, data: PmakAccountCreate):
    existing = await db.pmakaccount.find_unique(where={"accountName": data.accountName})
    if existing:
        raise HTTPException(status_code=409, detail="Account name already exists")
    return await db.pmakaccount.create(data={"accountName": data.accountName})


async def list_accounts(db: Prisma):
    accounts = await db.pmakaccount.find_many(
        where={"isActive": True},
        include={"transactions": {"take": 5}},
        order={"accountName": "asc"},
    )
    for acc in accounts:
        if acc.transactions:
            acc.transactions.sort(key=lambda t: t.date, reverse=True)
    return accounts


async def add_transaction(db: Prisma, data: PmakTransactionCreate):
    account = await db.pmakaccount.find_unique(where={"id": data.account_id})
    if not account:
        raise HTTPException(status_code=404, detail="PMAK account not found")

    return await db.pmaktransaction.create(
        data={
            "accountId":        data.account_id,
            "date":             data.date,
            "details":          data.details,
            "accountFrom":      data.accountFrom,
            "accountTo":        data.accountTo,
            "debit":            data.debit,
            "credit":           data.credit,
            "remainingBalance": data.remaining_balance,
            "status":           data.status.value if data.status else None,
            "notes":            data.notes,
        }
    )


async def update_transaction_status(
    db: Prisma,
    transaction_id: str,
    data: PmakTransactionStatusUpdate,
) -> object:
    """
    Restricted PATCH — only `status` and `notes` are touched.
    Safe for BDev role: no financial fields are exposed.
    """
    tx = await db.pmaktransaction.find_unique(where={"id": transaction_id})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    update_data: dict = {}
    if data.status is not None:
        update_data["status"] = data.status.value
    if data.notes is not None:
        update_data["notes"] = data.notes

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    return await db.pmaktransaction.update(
        where={"id": transaction_id},
        data=update_data,
    )


async def get_account_transactions(db: Prisma, account_id: str, date_filter: dict):
    account = await db.pmakaccount.find_unique(where={"id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    where: dict = {"accountId": account_id}
    if date_filter:
        where["date"] = date_filter
    return await db.pmaktransaction.find_many(where=where, order={"date": "desc"})


async def delete_transaction(db: Prisma, transaction_id: str):
    tx = await db.pmaktransaction.find_unique(where={"id": transaction_id})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.pmaktransaction.delete(where={"id": transaction_id})