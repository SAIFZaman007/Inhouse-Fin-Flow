-- Migration: 202603151231_fix_card_receive_bank_column
-- Replaces the broken PL/pgSQL version that caused P3009.
-- Plain DDL only — fully supported by prisma migrate deploy.
--
-- IMPORTANT: Before Coolify redeploys, run resolve_failed_migration.sql
-- directly on the production DB first to unblock Prisma's migration history.
-- After that, this file can be left as-is in the migrations folder —
-- Prisma will see the migration as "rolled back" and re-apply this clean version.
 
ALTER TABLE card_sharing RENAME COLUMN "cardReceiverBank" TO "cardReceiveBank";