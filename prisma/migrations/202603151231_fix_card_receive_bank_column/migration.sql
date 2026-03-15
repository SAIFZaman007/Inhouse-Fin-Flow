-- Migration: 202603151231_fix_card_receive_bank_column
-- CORRECTED: Column does not exist on production — must ADD it, not RENAME it.
-- Plain DDL only. Prisma wraps this in a transaction automatically.
 
ALTER TABLE card_sharing ADD COLUMN "cardReceiveBank" TEXT NOT NULL DEFAULT '';