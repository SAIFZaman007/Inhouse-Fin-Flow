"""
app/modules/pmak/router.py
════════════════════════════════════════════════════════════════════════════════
v5 — Enterprise Edition

Endpoint matrix
───────────────────────────────────────────────────────────────────────────────
GET    /accounts                      HR_AND_ABOVE   Combined totals + all accounts
                                                     Period-aware. Paginated.
POST   /accounts                      HR_AND_ABOVE   Create PMAK account
PATCH  /accounts/{account_id}         ALL_ROLES      Rename / toggle isActive
DELETE /accounts/{account_id}         CEO_DIRECTOR   Soft-delete — returns JSON message

POST   /transactions                  ALL_ROLES      Add ledger transaction
PATCH  /transactions/{id}             HR_AND_ABOVE   Full field update
PATCH  /transactions/{id}/status      BDEV_AND_ABOVE Status-only update (BDev entry-point)
GET    /accounts/{id}/transactions    HR_AND_ABOVE   Paginated transactions for one account
DELETE /transactions/{id}             CEO_DIRECTOR   Hard delete — returns JSON message

POST   /inhouse                       ALL_ROLES      Add inhouse deal
PATCH  /inhouse/{deal_id}             ALL_ROLES      Partial update (status / details)
GET    /inhouse                       HR_AND_ABOVE   All inhouse deals (period-aware, paginated)
GET    /accounts/{id}/inhouse         HR_AND_ABOVE   Inhouse deals for one account
DELETE /inhouse/{deal_id}             CEO_DIRECTOR   Hard delete — returns JSON message

GET    /export                        CEO_DIRECTOR   All-accounts Excel (period-aware)
GET    /export/{account_id}           CEO_DIRECTOR   Single-account Excel (period-aware)
════════════════════════════════════════════════════════════════════════════════
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import ALL_ROLES, BDEV_AND_ABOVE, CEO_DIRECTOR, HR_AND_ABOVE
from app.shared.filters import DateRangeFilter
from app.shared.pagination import PageParams
from app.modules.export.schema import ExportQueryParams
from app.modules.export.service import export_pmak

from .schema import (
    PmakAccountCreate,
    PmakInhouseCreate,
    PmakInhouseStatusUpdate,
    PmakTransactionCreate,
    PmakTransactionStatusUpdate,
)
from .service import (
    create_account,
    deactivate_account,
    update_account,
    add_transaction,
    update_transaction,
    update_transaction_status,
    delete_transaction,
    get_account_transactions,
    add_inhouse,
    update_inhouse,
    delete_inhouse,
    get_all_inhouse,
    get_account_inhouse,
    list_accounts,
    export_account_excel,
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

- **Combined totals** across all active accounts for the selected period —
  `totalBalance`, `totalCredit`, `totalDebit`, `totalTransactions`,
  `totalInhouse`, `totalInhouseAmount`, `inhouseByStatus`, `activeAccountCount`.
- **Paginated per-account breakdown** (50 accounts per page by default),
  each including `currentBalance`, period credit/debit, transaction count,
  inhouse deal summary, and the 5 most recent transactions/deals.

Use `?name=` for a case-insensitive partial search on account name.

Period params: `daily` | `weekly` | `monthly` | `yearly` | `all` (default).

**Access:** HR and above.
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
    _=Depends(HR_AND_ABOVE),
):
    return await list_accounts(db, filters, name=name, pagination=pagination)


@router.post(
    "/accounts",
    status_code=201,
    summary="Create a PMAK account",
    description="""
Creates a new PMAK ledger account.

**Required:** `accountName` (unique, 1–100 characters)

**Access:** CEO, Director, and HR.
    """,
)
async def add_account(
    body: PmakAccountCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await create_account(db, body)


@router.patch(
    "/accounts/{account_id}",
    summary="Partially update a PMAK account",
    description="""
Performs a **partial update** on an existing PMAK account.

| Field | Effect |
|---|---|
| `accountName` | Renames the account; uniqueness enforced (409 on conflict). |
| `isActive` | `false` soft-deletes; `true` restores a deactivated account. |

Sending an empty body `{}` is accepted and returns the current state unchanged
(idempotent).

**Access:** CEO, Director, HR, and BDev.
    """,
)
async def patch_account(
    account_id: str,
    body: PmakAccountCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await update_account(db, account_id, body)


@router.delete(
    "/accounts/{account_id}",
    status_code=200,
    summary="Soft-delete a PMAK account (sets isActive = false)",
    description="""
Soft-deletes a PMAK account by setting `isActive` to `false`.

The account and all its historical transactions/deals remain intact in the
database and can be restored via `PATCH /accounts/{id}`.

Returns a JSON confirmation message on success.

**Access:** CEO and Director only.
    """,
)
async def remove_account(
    account_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await deactivate_account(db, account_id)
    return {
        "success": True,
        "message": "PMAK account has been deactivated successfully.",
        "accountId": account_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Transactions
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/transactions",
    status_code=201,
    summary="Add a PMAK ledger transaction",
    description="""
Adds a ledger transaction for the specified PMAK account.

**`account_name`** — the human-readable account name (case-insensitive).
The system resolves it to an internal record automatically.

`remainingBalance` must be supplied by the caller (balance *after* this
transaction). `status` defaults to `PENDING`.

**Access:** All roles (CEO, Director, HR, and BDev).
    """,
)
async def add_transaction_entry(
    body: PmakTransactionCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await add_transaction(db, body)


@router.patch(
    "/transactions/{transaction_id}",
    summary="Partially update a PMAK transaction (all fields)",
    description="""
Performs a **partial update** on an existing PMAK transaction.

All fields are optional — only supplied fields are changed:

| Field | Effect |
|---|---|
| `date` | Changes the transaction date. |
| `details` | Updates the description / reference text. |
| `accountFrom` | Updates the source label (send `null` to clear). |
| `accountTo` | Updates the destination label (send `null` to clear). |
| `debit` | Updates the debit amount. |
| `credit` | Updates the credit amount. |
| `remaining_balance` | Corrects the post-transaction balance (not auto-recomputed). |
| `status` | Updates lifecycle status: `PENDING` \| `CLEARED` \| `ON_HOLD` \| `REJECTED`. |

Sending an empty body `{}` returns the current transaction state unchanged
(idempotent).

**Access:** HR and above.
    """,
)
async def patch_transaction(
    transaction_id: str,
    body: PmakTransactionCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await update_transaction(db, transaction_id, body)


@router.patch(
    "/transactions/{transaction_id}/status",
    summary="Update PMAK transaction status only (BDev entry-point)",
    description="""
**Restricted PATCH** — exposes only the `status` field.

Intended for BDev staff who need to mark transactions as `CLEARED`, `ON_HOLD`,
or `REJECTED` without access to financial field edits.

| Status | Meaning |
|---|---|
| `PENDING` | Awaiting clearance (default). |
| `CLEARED` | Funds confirmed and settled. |
| `ON_HOLD` | Flagged for review. |
| `REJECTED` | Transaction rejected / reversed. |

Sending an empty body `{}` is accepted and returns the current status unchanged
(idempotent).

**Access:** BDev and above (all roles).
    """,
)
async def patch_transaction_status(
    transaction_id: str,
    body: PmakTransactionStatusUpdate,
    db:   Prisma = Depends(get_db),
    _=Depends(BDEV_AND_ABOVE),
):
    return await update_transaction_status(db, transaction_id, body)


@router.get(
    "/accounts/{account_id}/transactions",
    summary="Transactions for one PMAK account (period-aware, paginated)",
    description="""
Returns paginated transactions for a single PMAK account.

Each transaction row includes **`accountName`** so clients always have full
context without a secondary account lookup.

Response also contains `currentBalance` (latest balance across all time),
`periodCredit`, and `periodDebit` for the selected window.

Default: 50 transactions per page, newest first.

**Access:** HR and above.
    """,
)
async def account_transactions(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_account_transactions(
        db, account_id, filters.to_prisma_filter(), pagination=pagination
    )


@router.delete(
    "/transactions/{transaction_id}",
    status_code=200,
    summary="Delete a PMAK transaction (hard delete)",
    description="""
Permanently removes a PMAK transaction from the ledger.

> ⚠️ **This is a hard delete** — the record cannot be recovered.
> Update subsequent `remainingBalance` values manually if needed to maintain
> ledger integrity.

Returns a JSON confirmation message on success.

**Access:** CEO and Director only.
    """,
)
async def remove_transaction(
    transaction_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_transaction(db, transaction_id)
    return {
        "success": True,
        "message": "PMAK transaction has been permanently deleted.",
        "transactionId": transaction_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Inhouse Deals
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/inhouse",
    status_code=201,
    summary="Add a PMAK inhouse deal",
    description="""
Logs a new inhouse deal against the specified PMAK account.

**`account_name`** — the human-readable account name (case-insensitive).
The system resolves it to an internal record automatically.

`order_status` defaults to `PENDING`.

**Access:** All roles (CEO, Director, HR, and BDev).
    """,
)
async def add_inhouse_entry(
    body: PmakInhouseCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await add_inhouse(db, body)


@router.patch(
    "/inhouse/{deal_id}",
    summary="Partially update a PMAK inhouse deal",
    description="""
Performs a **partial update** on an existing inhouse deal.

All fields are optional — only supplied fields are changed:

| Field | Effect |
|---|---|
| `order_status` | Updates lifecycle status: `PENDING` \| `IN_PROGRESS` \| `COMPLETED` \| `CANCELLED`. |
| `details` | Updates the free-text notes / reference code. |

Sending an empty body `{}` returns the current deal state unchanged (idempotent).

**Access:** All roles (CEO, Director, HR, and BDev).
    """,
)
async def patch_inhouse(
    deal_id: str,
    body: PmakInhouseStatusUpdate,
    db:   Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await update_inhouse(db, deal_id, body)


@router.get(
    "/inhouse",
    summary="All PMAK inhouse deals (period-aware, paginated)",
    description="""
Returns paginated inhouse deals across **all accounts** for the selected period.

Response includes aggregate totals (`totalDeals`, `totalAmount`, `byStatus`)
as well as the paginated deal list.

Each deal row includes `accountName` for full client context.

Period params: `daily` | `weekly` | `monthly` | `yearly` | `all` (default).

**Access:** HR and above.
    """,
)
async def get_inhouse(
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_all_inhouse(db, filters, pagination=pagination)


@router.get(
    "/accounts/{account_id}/inhouse",
    summary="Inhouse deals for one PMAK account (period-aware, paginated)",
    description="""
Returns paginated inhouse deals for a single PMAK account.

Response includes deal counts grouped by `orderStatus`
(`PENDING`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`) and a `totalAmount`
for the selected window.

Default: 50 deals per page, newest first.

**Access:** HR and above.
    """,
)
async def account_inhouse(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_account_inhouse(
        db, account_id, filters.to_prisma_filter(), pagination=pagination
    )


@router.delete(
    "/inhouse/{deal_id}",
    status_code=200,
    summary="Delete a PMAK inhouse deal (hard delete)",
    description="""
Permanently removes a PMAK inhouse deal from the ledger.

> ⚠️ **This is a hard delete** — the record cannot be recovered.

Returns a JSON confirmation message on success.

**Access:** CEO and Director only.
    """,
)
async def remove_inhouse(
    deal_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_inhouse(db, deal_id)
    return {
        "success": True,
        "message": "PMAK inhouse deal has been permanently deleted.",
        "dealId": deal_id,
    }


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

**Access:** CEO and Director only.
    """,
)
async def export_all_accounts(
    params: ExportQueryParams = Depends(),
    db:     Prisma            = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    data, filename = await export_pmak(db, params)
    return _xlsx(data, filename)


@router.get(
    "/export/{account_id}",
    summary="Export a single PMAK account to Excel (period-aware)",
    description="""
Downloads a two-sheet Excel workbook for **one account**:
- **Sheet 1** — Ledger Transactions (all fields + status)
- **Sheet 2** — Inhouse Deals (all fields + order status)

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