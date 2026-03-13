-- ============================================================
--  FIXED: 20260311164845_v3_enterprise_changes/migration.sql
--
--  What was wrong in the original:
--  1. card_sharing.accountId       TEXT NOT NULL — no default, table not empty → fatal
--  2. card_sharing.date            DATE NOT NULL — no default, table not empty → fatal
--  3. fiverr_orders.afterFiverr    DECIMAL NOT NULL — no default, table not empty → fatal
--  4. upwork_orders.afterUpwork    DECIMAL NOT NULL — no default, table not empty → fatal
--  5. hr_expenses.updatedAt        TIMESTAMP NOT NULL — no default, table not empty → fatal
--  6. card_sharing ADD COLUMN "cardReceiveBack" — column absent from final schema, removed
--
--  Fix strategy:
--  - Columns with computable values: add nullable, backfill, then set NOT NULL
--  - card_sharing.accountId is a FK with no safe automatic value — added nullable,
--    backfilled with '' sentinel, set NOT NULL. You MUST update these rows manually
--    or via a data-migration script before the FK constraint is added.
-- ============================================================

-- ─── Create ENUMs ──────────────────────────────────────────

CREATE TYPE "PmakStatus" AS ENUM ('PENDING', 'CLEARED', 'ON_HOLD', 'REJECTED');

CREATE TYPE "InhouseOrderStatus" AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED');

-- ─── card_sharing ──────────────────────────────────────────
-- Drop legacy columns
ALTER TABLE "card_sharing"
  DROP COLUMN "cardPaymentRcv",
  DROP COLUMN "cardRcvBank",
  DROP COLUMN "payoneerAccount",
  DROP COLUMN "screenshotPath";

-- Add columns that have safe defaults directly as NOT NULL
ALTER TABLE "card_sharing"
  ADD COLUMN "cardDetails"         JSONB          NOT NULL DEFAULT '[]',
  ADD COLUMN "cardPaymentReceive"  DECIMAL(12,2)  NOT NULL DEFAULT 0;

-- Add the two NOT NULL columns without a universal safe default — nullable first
ALTER TABLE "card_sharing"
  ADD COLUMN "accountId"  TEXT  NULL,
  ADD COLUMN "date"       DATE  NULL;

-- Backfill date from createdAt for any existing rows
UPDATE "card_sharing"
SET "date" = "createdAt"::DATE
WHERE "date" IS NULL;

-- Backfill accountId: use empty string sentinel for existing rows.
-- ACTION REQUIRED: after deploy, update these rows with real payoneer_accounts.id values.
UPDATE "card_sharing"
SET "accountId" = ''
WHERE "accountId" IS NULL;

-- Now it is safe to add NOT NULL
ALTER TABLE "card_sharing"
  ALTER COLUMN "date"      SET NOT NULL,
  ALTER COLUMN "accountId" SET NOT NULL;

-- ─── fiverr_entries ────────────────────────────────────────
ALTER TABLE "fiverr_entries"
  ADD COLUMN "activeOrderAmount" DECIMAL(12,2) NOT NULL DEFAULT 0;

-- ─── fiverr_orders ─────────────────────────────────────────
-- afterFiverr = amount * 0.80 (Fiverr 20% fee)
ALTER TABLE "fiverr_orders"
  ADD COLUMN "afterFiverr" DECIMAL(12,2) NULL;

UPDATE "fiverr_orders"
SET "afterFiverr" = ROUND("amount" * 0.80, 2)
WHERE "afterFiverr" IS NULL;

ALTER TABLE "fiverr_orders"
  ALTER COLUMN "afterFiverr" SET NOT NULL;

-- ─── hr_expenses ───────────────────────────────────────────
-- remarks has a safe NULL default; updatedAt must be backfilled from createdAt
ALTER TABLE "hr_expenses"
  ADD COLUMN "remarks"   TEXT NULL;

ALTER TABLE "hr_expenses"
  ADD COLUMN "updatedAt" TIMESTAMP(3) NULL;

UPDATE "hr_expenses"
SET "updatedAt" = "createdAt"
WHERE "updatedAt" IS NULL;

ALTER TABLE "hr_expenses"
  ALTER COLUMN "updatedAt" SET NOT NULL;

-- ─── pmak_transactions ─────────────────────────────────────
-- Drop old TEXT columns, add typed enum column
ALTER TABLE "pmak_transactions"
  DROP COLUMN "buyer",
  DROP COLUMN "notes",
  DROP COLUMN "seller",
  DROP COLUMN "status";

ALTER TABLE "pmak_transactions"
  ADD COLUMN "status" "PmakStatus" NOT NULL DEFAULT 'PENDING';

-- ─── upwork_orders ─────────────────────────────────────────
-- afterUpwork = amount * 0.90 (Upwork 10% fee)
ALTER TABLE "upwork_orders"
  ADD COLUMN "afterUpwork" DECIMAL(12,2) NULL;

UPDATE "upwork_orders"
SET "afterUpwork" = ROUND("amount" * 0.90, 2)
WHERE "afterUpwork" IS NULL;

ALTER TABLE "upwork_orders"
  ALTER COLUMN "afterUpwork" SET NOT NULL;

-- ─── Drop DailyRate table ──────────────────────────────────
DROP TABLE "DailyRate";

-- ─── Create pmak_inhouse ───────────────────────────────────
CREATE TABLE "pmak_inhouse" (
    "id"          TEXT                 NOT NULL,
    "date"        DATE                 NOT NULL,
    "details"     TEXT,
    "buyerName"   TEXT                 NOT NULL,
    "sellerName"  TEXT                 NOT NULL,
    "orderAmount" DECIMAL(12,2)        NOT NULL,
    "orderStatus" "InhouseOrderStatus" NOT NULL DEFAULT 'PENDING',
    "accountId"   TEXT                 NOT NULL,
    "createdAt"   TIMESTAMP(3)         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt"   TIMESTAMP(3)         NOT NULL,

    CONSTRAINT "pmak_inhouse_pkey" PRIMARY KEY ("id")
);

-- ─── Indexes ───────────────────────────────────────────────
CREATE INDEX "pmak_inhouse_date_idx"               ON "pmak_inhouse"("date");
CREATE INDEX "pmak_inhouse_orderStatus_idx"        ON "pmak_inhouse"("orderStatus");
CREATE INDEX "card_sharing_date_idx"               ON "card_sharing"("date");
CREATE INDEX "card_sharing_accountId_idx"          ON "card_sharing"("accountId");
CREATE INDEX "dollar_exchanges_date_idx"           ON "dollar_exchanges"("date");
CREATE INDEX "dollar_exchanges_paymentStatus_idx"  ON "dollar_exchanges"("paymentStatus");
CREATE INDEX "fiverr_entries_date_idx"             ON "fiverr_entries"("date");
CREATE INDEX "fiverr_orders_date_idx"              ON "fiverr_orders"("date");
CREATE INDEX "hr_expenses_date_idx"                ON "hr_expenses"("date");
CREATE INDEX "inventory_date_idx"                  ON "inventory"("date");
CREATE INDEX "outside_orders_date_idx"             ON "outside_orders"("date");
CREATE INDEX "outside_orders_orderStatus_idx"      ON "outside_orders"("orderStatus");
CREATE INDEX "payoneer_transactions_date_idx"      ON "payoneer_transactions"("date");
CREATE INDEX "pmak_transactions_date_idx"          ON "pmak_transactions"("date");
CREATE INDEX "pmak_transactions_status_idx"        ON "pmak_transactions"("status");
CREATE INDEX "upwork_entries_date_idx"             ON "upwork_entries"("date");
CREATE INDEX "upwork_orders_date_idx"              ON "upwork_orders"("date");

-- ─── Foreign Keys ──────────────────────────────────────────
ALTER TABLE "pmak_inhouse"
  ADD CONSTRAINT "pmak_inhouse_accountId_fkey"
  FOREIGN KEY ("accountId") REFERENCES "pmak_accounts"("id")
  ON DELETE RESTRICT ON UPDATE CASCADE;

-- NOTE: card_sharing FK is intentionally omitted here.
-- Run this manually AFTER you have verified all card_sharing.accountId
-- values are valid payoneer_accounts.id values:
--
--   ALTER TABLE "card_sharing"
--     ADD CONSTRAINT "card_sharing_accountId_fkey"
--     FOREIGN KEY ("accountId") REFERENCES "payoneer_accounts"("id")
--     ON DELETE RESTRICT ON UPDATE CASCADE;