-- =============================================================================
-- Migration: rename card_sharing.cardReceiverBank → cardReceiveBank
-- =============================================================================
-- ROOT CAUSE (Bug B):
--   The Prisma schema (v4) renamed the column from "cardReceiverBank" to
--   "cardReceiveBank".  The migration was applied locally but was NEVER run
--   on the Coolify production database.  The generated Prisma client therefore
--   references a column that does not exist in the live DB, causing:
--
--     PrismaError: The column `card_sharing.cardReceiveBank` does not exist
--                  in the current database.
--
-- HOW TO APPLY:
--   Option A — via psql (recommended for Coolify):
--     psql "$DATABASE_URL" -f fix_card_receive_bank_column.sql
--
--   Option B — paste directly into your Coolify DB console.
--
--   Option C — via Prisma migrate (if you have a migrations folder):
--     Copy this SQL into a new migration file and run:
--       prisma migrate deploy
-- =============================================================================

BEGIN;

-- Step 1: Check if the OLD column name exists (safe guard)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM   information_schema.columns
    WHERE  table_name  = 'card_sharing'
    AND    column_name = 'cardReceiverBank'
  ) THEN
    -- Rename the old column to match the Prisma schema
    ALTER TABLE card_sharing
      RENAME COLUMN "cardReceiverBank" TO "cardReceiveBank";

    RAISE NOTICE 'SUCCESS: Renamed cardReceiverBank → cardReceiveBank on card_sharing table.';

  ELSIF EXISTS (
    SELECT 1
    FROM   information_schema.columns
    WHERE  table_name  = 'card_sharing'
    AND    column_name = 'cardReceiveBank'
  ) THEN
    RAISE NOTICE 'SKIPPED: cardReceiveBank already exists — no rename needed. Database is up to date.';

  ELSE
    -- Neither column exists — something is very wrong; abort loudly
    RAISE EXCEPTION
      'NEITHER cardReceiverBank NOR cardReceiveBank found on card_sharing. '
      'Check your migration history before proceeding.';
  END IF;
END $$;

COMMIT;

-- =============================================================================
-- POST-MIGRATION VERIFICATION
-- Run this SELECT to confirm the column is correctly named:
-- =============================================================================
-- SELECT column_name, data_type
-- FROM   information_schema.columns
-- WHERE  table_name = 'card_sharing'
-- ORDER  BY ordinal_position;