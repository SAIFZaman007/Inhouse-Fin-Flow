/*
  Warnings:

  - You are about to drop the column `cardPaymentRcv` on the `card_sharing` table. All the data in the column will be lost.
  - You are about to drop the column `cardRcvBank` on the `card_sharing` table. All the data in the column will be lost.
  - You are about to drop the column `payoneerAccount` on the `card_sharing` table. All the data in the column will be lost.
  - You are about to drop the column `screenshotPath` on the `card_sharing` table. All the data in the column will be lost.
  - You are about to drop the column `buyer` on the `pmak_transactions` table. All the data in the column will be lost.
  - You are about to drop the column `notes` on the `pmak_transactions` table. All the data in the column will be lost.
  - You are about to drop the column `seller` on the `pmak_transactions` table. All the data in the column will be lost.
  - The `status` column on the `pmak_transactions` table would be dropped and recreated. This will lead to data loss if there is data in the column.
  - You are about to drop the `DailyRate` table. If the table is not empty, all the data it contains will be lost.
  - Added the required column `accountId` to the `card_sharing` table without a default value. This is not possible if the table is not empty.
  - Added the required column `date` to the `card_sharing` table without a default value. This is not possible if the table is not empty.
  - Added the required column `afterFiverr` to the `fiverr_orders` table without a default value. This is not possible if the table is not empty.
  - Added the required column `updatedAt` to the `hr_expenses` table without a default value. This is not possible if the table is not empty.
  - Added the required column `afterUpwork` to the `upwork_orders` table without a default value. This is not possible if the table is not empty.

*/
-- CreateEnum
CREATE TYPE "PmakStatus" AS ENUM ('PENDING', 'CLEARED', 'ON_HOLD', 'REJECTED');

-- CreateEnum
CREATE TYPE "InhouseOrderStatus" AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED');

-- AlterTable
ALTER TABLE "card_sharing" DROP COLUMN "cardPaymentRcv",
DROP COLUMN "cardRcvBank",
DROP COLUMN "payoneerAccount",
DROP COLUMN "screenshotPath",
ADD COLUMN     "accountId" TEXT NOT NULL,
ADD COLUMN     "cardDetails" JSONB NOT NULL DEFAULT '[]',
ADD COLUMN     "cardPaymentReceive" DECIMAL(12,2) NOT NULL DEFAULT 0,
ADD COLUMN     "cardReceiveBack" DECIMAL(12,2) NOT NULL DEFAULT 0,
ADD COLUMN     "date" DATE NOT NULL;

-- AlterTable
ALTER TABLE "fiverr_entries" ADD COLUMN     "activeOrderAmount" DECIMAL(12,2) NOT NULL DEFAULT 0;

-- AlterTable
ALTER TABLE "fiverr_orders" ADD COLUMN     "afterFiverr" DECIMAL(12,2) NOT NULL;

-- AlterTable
ALTER TABLE "hr_expenses" ADD COLUMN     "remarks" TEXT,
ADD COLUMN     "updatedAt" TIMESTAMP(3) NOT NULL;

-- AlterTable
ALTER TABLE "pmak_transactions" DROP COLUMN "buyer",
DROP COLUMN "notes",
DROP COLUMN "seller",
DROP COLUMN "status",
ADD COLUMN     "status" "PmakStatus" NOT NULL DEFAULT 'PENDING';

-- AlterTable
ALTER TABLE "upwork_orders" ADD COLUMN     "afterUpwork" DECIMAL(12,2) NOT NULL;

-- DropTable
DROP TABLE "DailyRate";

-- CreateTable
CREATE TABLE "pmak_inhouse" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "details" TEXT,
    "buyerName" TEXT NOT NULL,
    "sellerName" TEXT NOT NULL,
    "orderAmount" DECIMAL(12,2) NOT NULL,
    "orderStatus" "InhouseOrderStatus" NOT NULL DEFAULT 'PENDING',
    "accountId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "pmak_inhouse_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "pmak_inhouse_date_idx" ON "pmak_inhouse"("date");

-- CreateIndex
CREATE INDEX "pmak_inhouse_orderStatus_idx" ON "pmak_inhouse"("orderStatus");

-- CreateIndex
CREATE INDEX "card_sharing_date_idx" ON "card_sharing"("date");

-- CreateIndex
CREATE INDEX "card_sharing_accountId_idx" ON "card_sharing"("accountId");

-- CreateIndex
CREATE INDEX "dollar_exchanges_date_idx" ON "dollar_exchanges"("date");

-- CreateIndex
CREATE INDEX "dollar_exchanges_paymentStatus_idx" ON "dollar_exchanges"("paymentStatus");

-- CreateIndex
CREATE INDEX "fiverr_entries_date_idx" ON "fiverr_entries"("date");

-- CreateIndex
CREATE INDEX "fiverr_orders_date_idx" ON "fiverr_orders"("date");

-- CreateIndex
CREATE INDEX "hr_expenses_date_idx" ON "hr_expenses"("date");

-- CreateIndex
CREATE INDEX "inventory_date_idx" ON "inventory"("date");

-- CreateIndex
CREATE INDEX "outside_orders_date_idx" ON "outside_orders"("date");

-- CreateIndex
CREATE INDEX "outside_orders_orderStatus_idx" ON "outside_orders"("orderStatus");

-- CreateIndex
CREATE INDEX "payoneer_transactions_date_idx" ON "payoneer_transactions"("date");

-- CreateIndex
CREATE INDEX "pmak_transactions_date_idx" ON "pmak_transactions"("date");

-- CreateIndex
CREATE INDEX "pmak_transactions_status_idx" ON "pmak_transactions"("status");

-- CreateIndex
CREATE INDEX "upwork_entries_date_idx" ON "upwork_entries"("date");

-- CreateIndex
CREATE INDEX "upwork_orders_date_idx" ON "upwork_orders"("date");

-- AddForeignKey
ALTER TABLE "pmak_inhouse" ADD CONSTRAINT "pmak_inhouse_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "pmak_accounts"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "card_sharing" ADD CONSTRAINT "card_sharing_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "payoneer_accounts"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
