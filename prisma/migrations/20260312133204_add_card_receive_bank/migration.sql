/*
  Warnings:

  - You are about to drop the column `cardReceiveBack` on the `card_sharing` table. All the data in the column will be lost.

*/
-- AlterTable
ALTER TABLE "card_sharing" DROP COLUMN "cardReceiveBack",
ADD COLUMN     "cardReceiveBank" TEXT NOT NULL DEFAULT '';
