"""
app/modules/pmak/router.py
════════════════════════════════════════════════════════════════════════════════
v4 — Enterprise Edition

Endpoint matrix
───────────────────────────────────────────────────────────────────────────────
GET    /accounts                        PMAK_EDITORS  Combined totals + all accounts
                                                      Period + ?name= filter. Paginated.
POST   /accounts                        CEO_DIRECTOR  Create account (returns rich response)
DELETE /accounts/{id}                   CEO_DIRECTOR  Soft-delete (isActive → false)

POST   /transactions                    HR_AND_ABOVE  Add transaction (by accountName)
GET    /accounts/{id}/transactions      PMAK_EDITORS  Paginated transactions + accountName
PATCH  /transactions/{id}/status        PMAK_EDITORS  Status-only PATCH (BDev entry-point)
DELETE /transactions/{id}               CEO_DIRECTOR  Hard delete

POST   /inhouse                         HR_AND_ABOVE  Add inhouse deal (by accountName)
GET    /accounts/{id}/inhouse           PMAK_EDITORS  Paginated inhouse + status summary
PATCH  /inhouse/{id}                    PMAK_EDITORS  Update status / details
DELETE /inhouse/{id}                    CEO_DIRECTOR  Hard delete

GET    /export                          PMAK_EDITORS  All-accounts Excel (period-aware)
GET    /export/{account_id}             CEO_DIRECTOR  Single-account Excel (Ledger + Inhouse)
════════════════════════════════════════════════════════════════════════════════
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR, HR_AND_ABOVE, PMAK_EDITORS
from app.shared.filters import DateRangeFilter
from app.shared.pagination import PageParams
from app.modules.export.schema import ExportQueryParams
from app.modules.export.service import export_pmak    # existing all-accounts exporter

from .schema import (
    PmakAccountCreate,
    PmakInhouseCreate, PmakInhouseStatusUpdate,
    PmakTransactionCreate, PmakTransactionStatusUpdate,
)
from .service import (
    add_transaction,
    create_account,
    create_inhouse_deal,
    deactivate_account,
    delete_inhouse_deal,
    delete_transaction,
    export_account_excel,
    get_account_inhouse_deals,
    get_account_transactions,
    list_accounts,
    update_inhouse_deal,
    update_transaction_status,
)

router = APIRouter(prefix="/pmak", tags=["PMAK"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _xlsx(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Accounts
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/accounts",
    summary="All PMAK accounts — combined totals + per-account breakdown",
    description="""
Returns a **single response** containing:

- **Combined totals** across all active accounts:
  `totalBalance`, `totalCredit`, `totalDebit`, `totalTransactions`,
  `totalInhouse`, `totalInhouseAmount`, `inhouseByStatus`
  (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED` — each with `count`
  and `totalAmount`), `activeAccountCount`.
- **Paginated per-account breakdown** (50 accounts per page by default),
  each including current balance, period credit/debit, transaction + inhouse
  counts, status breakdown, and the 5 most recent items per type.

Use `?name=` for a case-insensitive partial search on account name.

Period params: `daily` | `weekly` | `monthly` | `yearly` | `all` (default).
    """,
)
async def get_accounts(
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    name: Annotated[
        Optional[str],
        Query(description="Case-insensitive partial search on account name."),
    ] = None,
    db: Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    return await list_accounts(db, filters, name=name, pagination=pagination)


@router.post(
    "/accounts",
    status_code=201,
    summary="Create a PMAK account",
    description="""
Creates a new PMAK ledger account.

Response includes an enriched breakdown:
`currentBalance`, `totalTransactions`, `totalInhouse`, `inhouseByStatus`
— all starting at zero, ready for data entry.

**Required:** `accountName`

**Access:** CEO and Director only.
    """,
)
async def add_account(
    body: PmakAccountCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await create_account(db, body)


@router.delete(
    "/accounts/{account_id}",
    status_code=204,
    summary="Soft-delete a PMAK account (sets isActive = false)",
)
async def remove_account(
    account_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await deactivate_account(db, account_id)


# ─────────────────────────────────────────────────────────────────────────────
# Ledger Transactions
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/transactions",
    status_code=201,
    summary="Add a PMAK ledger transaction",
    description="""
Adds a transaction to the specified PMAK account's ledger.

**`account_name`** — the human-readable account name (case-insensitive).
The system resolves it to an internal record — staff never handle UUIDs.

**Access:** HR and above (BDev may NOT create transactions).
    """,
)
async def add_transaction_entry(
    body: PmakTransactionCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await add_transaction(db, body)


@router.get(
    "/accounts/{account_id}/transactions",
    summary="Transactions for one PMAK account (period-aware, paginated)",
    description="""
Returns paginated ledger transactions for a single account.

Each row includes **`accountName`** for client convenience.
Response also contains `currentBalance`, `periodCredit`, `periodDebit`.

Default: 50 transactions per page, newest first.
    """,
)
async def account_transactions(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    return await get_account_transactions(
        db, account_id, filters.to_prisma_filter(), pagination=pagination
    )


@router.patch(
    "/transactions/{transaction_id}/status",
    summary="Update transaction status — BDev, HR, CEO, Director",
    description="""
Restricted PATCH — only `status` may be updated.

This is the **BDev entry-point**: no financial fields are exposed.
BDev can mark transactions CLEARED / ON_HOLD / REJECTED / PENDING.
    """,
)
async def patch_transaction_status(
    transaction_id: str,
    body: PmakTransactionStatusUpdate,
    db:   Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    return await update_transaction_status(db, transaction_id, body)


@router.delete(
    "/transactions/{transaction_id}",
    status_code=204,
    summary="Delete a PMAK transaction (hard delete — CEO/Director only)",
)
async def remove_transaction(
    transaction_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_transaction(db, transaction_id)


# ─────────────────────────────────────────────────────────────────────────────
# Inhouse Deals
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/inhouse",
    status_code=201,
    summary="Add a PMAK inhouse deal",
    description="""
Creates a new buyer/seller inhouse deal for the specified PMAK account.

**`account_name`** — the human-readable account name (case-insensitive).
The system resolves it automatically — staff never handle internal UUIDs.

**Access:** HR and above (BDev may NOT create inhouse deals).
    """,
)
async def add_inhouse_deal(
    body: PmakInhouseCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await create_inhouse_deal(db, body)


@router.get(
    "/accounts/{account_id}/inhouse",
    summary="Inhouse deals for one PMAK account (period-aware, paginated)",
    description="""
Returns paginated inhouse deals for a single account.

Each row includes **`accountName`**. Response also contains a full
`inhouseByStatus` breakdown (`PENDING`, `IN_PROGRESS`, `COMPLETED`,
`CANCELLED` — each with `count` and `totalAmount`).

Default: 50 deals per page, newest first.
    """,
)
async def account_inhouse_deals(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    return await get_account_inhouse_deals(
        db, account_id, filters.to_prisma_filter(), pagination=pagination
    )


@router.patch(
    "/inhouse/{deal_id}",
    summary="Update inhouse deal status / details — BDev, HR, CEO, Director",
)
async def patch_inhouse_deal(
    deal_id: str,
    body:    PmakInhouseStatusUpdate,
    db:      Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    return await update_inhouse_deal(db, deal_id, body)


@router.delete(
    "/inhouse/{deal_id}",
    status_code=204,
    summary="Delete a PMAK inhouse deal (hard delete — CEO/Director only)",
)
async def remove_inhouse_deal(
    deal_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_inhouse_deal(db, deal_id)


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/export",
    summary="Export all PMAK accounts to Excel (period-aware, multi-sheet)",
    description="""
Downloads a multi-sheet Excel workbook covering **all active PMAK accounts**
for the selected period.

Supports `period` / `from` / `to` / `year` / `month` / `export_date` params.

**Access:** All roles with PMAK access (PMAK_EDITORS).
    """,
)
async def export_all_accounts(
    params: ExportQueryParams = Depends(),
    db:     Prisma            = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    data, filename = await export_pmak(db, params)
    return _xlsx(data, filename)


@router.get(
    "/export/{account_id}",
    summary="Export a single PMAK account to Excel (period-aware)",
    description="""
Downloads a two-sheet Excel workbook for **one account**:
- **Sheet 1** — Ledger Transactions (date, details, account from/to, debit, credit, balance, status)
- **Sheet 2** — Inhouse Deals (date, buyer, seller, amount, status, details)

**Access:** CEO and Director only.
    """,
)
async def export_single_account(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    db:         Prisma          = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    data, filename = await export_account_excel(db, account_id, filters)
    return _xlsx(data, filename)