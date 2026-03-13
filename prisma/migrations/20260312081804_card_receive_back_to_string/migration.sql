-- ============================================================
--  STEP 1 — Run this on production PostgreSQL first.
--  Unblocks Prisma P3009 for the new failed migration.
-- ============================================================

-- 1. Verify the record exists
SELECT migration_name, started_at, finished_at, rolled_back_at
FROM _prisma_migrations
WHERE migration_name = '20260312081804_card_receive_back_to_string';

-- 2. Mark it as rolled back
UPDATE _prisma_migrations
SET rolled_back_at = NOW()
WHERE migration_name = '20260312081804_card_receive_back_to_string'
  AND finished_at IS NULL;

-- 3. Confirm both problematic migrations are now resolved
SELECT migration_name, started_at, finished_at, rolled_back_at
FROM _prisma_migrations
ORDER BY started_at;

-- Expected: both of these should now have rolled_back_at set:
--   20260311164845_v3_enterprise_changes
--   20260312081804_card_receive_back_to_string
-- ============================================================