-- ============================================================================
-- Migration: 20260326051848_role_matrix_integrated
--
-- ROOT CAUSE OF P3009 FAILURE:
--   Migration 202603151231_fix_card_receive_bank_column already ran on the
--   production database and added the "cardReceiveBank" column and the
--   "card_sharing_accountId_fkey" foreign key to card_sharing.
--   This migration originally duplicated both of those statements verbatim,
--   causing PostgreSQL to throw "column already exists" / "constraint already
--   exists", which Prisma recorded as a FAILED migration (P3009) and blocked
--   all subsequent deploys.
--
============================================================================

-- CreateEnum
-- (VisibilityStatus is new — does not exist on production yet)
CREATE TYPE "VisibilityStatus" AS ENUM ('VISIBLE', 'HIDDEN');

-- AlterTable: add cardReceiveBank only if it does not already exist
-- (202603151231_fix_card_receive_bank_column may have already added it)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name  = 'card_sharing'
          AND column_name = 'cardReceiveBank'
    ) THEN
        ALTER TABLE "card_sharing" ADD COLUMN "cardReceiveBank" TEXT NOT NULL DEFAULT '';
    END IF;
END $$;

-- CreateTable: permission_rules
CREATE TABLE "permission_rules" (
    "id"              TEXT               NOT NULL,
    "moduleName"      TEXT               NOT NULL,
    "ceo_access"      "VisibilityStatus" NOT NULL DEFAULT 'VISIBLE',
    "director_access" "VisibilityStatus" NOT NULL DEFAULT 'VISIBLE',
    "hr_access"       "VisibilityStatus" NOT NULL DEFAULT 'HIDDEN',
    "bdev_access"     "VisibilityStatus" NOT NULL DEFAULT 'HIDDEN',
    "displayOrder"    INTEGER            NOT NULL DEFAULT 0,
    "createdAt"       TIMESTAMP(3)       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt"       TIMESTAMP(3)       NOT NULL,

    CONSTRAINT "permission_rules_pkey" PRIMARY KEY ("id")
);

-- CreateTable: terms_conditions
CREATE TABLE "terms_conditions" (
    "id"        TEXT         NOT NULL,
    "content"   TEXT         NOT NULL,
    "version"   INTEGER      NOT NULL DEFAULT 1,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "terms_conditions_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "permission_rules_moduleName_key" ON "permission_rules"("moduleName");

-- CreateIndex
CREATE INDEX "permission_rules_moduleName_idx" ON "permission_rules"("moduleName");

-- AddForeignKey: add constraint only if it does not already exist
-- (an earlier migration may have already added card_sharing_accountId_fkey)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'card_sharing_accountId_fkey'
          AND table_name      = 'card_sharing'
    ) THEN
        ALTER TABLE "card_sharing"
            ADD CONSTRAINT "card_sharing_accountId_fkey"
            FOREIGN KEY ("accountId")
            REFERENCES "payoneer_accounts"("id")
            ON DELETE RESTRICT
            ON UPDATE CASCADE;
    END IF;
END $$;