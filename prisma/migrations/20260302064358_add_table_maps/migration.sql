/*
  Warnings:

  - You are about to drop the column `cardCvcEncrypted` on the `card_sharing` table. All the data in the column will be lost.
  - You are about to drop the column `cardNoEncrypted` on the `card_sharing` table. All the data in the column will be lost.
  - You are about to drop the column `cardScreenshot` on the `card_sharing` table. All the data in the column will be lost.
  - You are about to alter the column `cardLimit` on the `card_sharing` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to alter the column `cardPaymentRcv` on the `card_sharing` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to drop the column `fromParty` on the `dollar_exchanges` table. All the data in the column will be lost.
  - You are about to drop the column `toParty` on the `dollar_exchanges` table. All the data in the column will be lost.
  - You are about to drop the column `updatedAt` on the `dollar_exchanges` table. All the data in the column will be lost.
  - You are about to alter the column `debit` on the `dollar_exchanges` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to alter the column `credit` on the `dollar_exchanges` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to alter the column `rate` on the `dollar_exchanges` table. The data in that column could be lost. The data in that column will be cast from `Decimal(10,4)` to `Decimal(8,2)`.
  - You are about to alter the column `totalBdt` on the `dollar_exchanges` table. The data in that column could be lost. The data in that column will be cast from `Decimal(16,2)` to `Decimal(14,2)`.
  - You are about to drop the column `clientName` on the `fiverr_orders` table. All the data in the column will be lost.
  - You are about to alter the column `amount` on the `fiverr_orders` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to drop the column `createdAt` on the `fiverr_profiles` table. All the data in the column will be lost.
  - You are about to drop the column `name` on the `fiverr_profiles` table. All the data in the column will be lost.
  - You are about to drop the column `updatedAt` on the `fiverr_profiles` table. All the data in the column will be lost.
  - You are about to drop the column `fromParty` on the `hr_expenses` table. All the data in the column will be lost.
  - You are about to drop the column `toParty` on the `hr_expenses` table. All the data in the column will be lost.
  - You are about to alter the column `debit` on the `hr_expenses` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to alter the column `credit` on the `hr_expenses` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to alter the column `remainingBalance` on the `hr_expenses` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to drop the column `vendor` on the `inventory` table. All the data in the column will be lost.
  - You are about to alter the column `unitPrice` on the `inventory` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to alter the column `totalPrice` on the `inventory` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to drop the column `status` on the `outside_orders` table. All the data in the column will be lost.
  - You are about to alter the column `orderAmount` on the `outside_orders` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to alter the column `receiveAmount` on the `outside_orders` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to alter the column `dueAmount` on the `outside_orders` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to drop the column `createdAt` on the `payoneer_accounts` table. All the data in the column will be lost.
  - You are about to drop the column `name` on the `payoneer_accounts` table. All the data in the column will be lost.
  - You are about to drop the column `updatedAt` on the `payoneer_accounts` table. All the data in the column will be lost.
  - You are about to drop the column `fromParty` on the `payoneer_transactions` table. All the data in the column will be lost.
  - You are about to drop the column `toParty` on the `payoneer_transactions` table. All the data in the column will be lost.
  - You are about to alter the column `debit` on the `payoneer_transactions` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to alter the column `credit` on the `payoneer_transactions` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to alter the column `remainingBalance` on the `payoneer_transactions` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to drop the column `createdAt` on the `pmak_accounts` table. All the data in the column will be lost.
  - You are about to drop the column `name` on the `pmak_accounts` table. All the data in the column will be lost.
  - You are about to drop the column `updatedAt` on the `pmak_accounts` table. All the data in the column will be lost.
  - You are about to drop the column `fromParty` on the `pmak_transactions` table. All the data in the column will be lost.
  - You are about to drop the column `toParty` on the `pmak_transactions` table. All the data in the column will be lost.
  - You are about to alter the column `debit` on the `pmak_transactions` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to alter the column `credit` on the `pmak_transactions` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to alter the column `remainingBalance` on the `pmak_transactions` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to alter the column `amount` on the `upwork_orders` table. The data in that column could be lost. The data in that column will be cast from `Decimal(14,2)` to `Decimal(12,2)`.
  - You are about to drop the column `createdAt` on the `upwork_profiles` table. All the data in the column will be lost.
  - You are about to drop the column `name` on the `upwork_profiles` table. All the data in the column will be lost.
  - You are about to drop the column `updatedAt` on the `upwork_profiles` table. All the data in the column will be lost.
  - You are about to drop the `fiverr_snapshots` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `upwork_snapshots` table. If the table is not empty, all the data it contains will be lost.
  - A unique constraint covering the columns `[profileName]` on the table `fiverr_profiles` will be added. If there are existing duplicate values, this will fail.
  - A unique constraint covering the columns `[accountName]` on the table `payoneer_accounts` will be added. If there are existing duplicate values, this will fail.
  - A unique constraint covering the columns `[accountName]` on the table `pmak_accounts` will be added. If there are existing duplicate values, this will fail.
  - A unique constraint covering the columns `[profileName]` on the table `upwork_profiles` will be added. If there are existing duplicate values, this will fail.
  - Added the required column `cardCvc` to the `card_sharing` table without a default value. This is not possible if the table is not empty.
  - Added the required column `cardNo` to the `card_sharing` table without a default value. This is not possible if the table is not empty.
  - Added the required column `buyerName` to the `fiverr_orders` table without a default value. This is not possible if the table is not empty.
  - Added the required column `profileName` to the `fiverr_profiles` table without a default value. This is not possible if the table is not empty.
  - Added the required column `accountName` to the `payoneer_accounts` table without a default value. This is not possible if the table is not empty.
  - Added the required column `accountName` to the `pmak_accounts` table without a default value. This is not possible if the table is not empty.
  - Added the required column `profileName` to the `upwork_profiles` table without a default value. This is not possible if the table is not empty.

*/
-- DropForeignKey
ALTER TABLE "fiverr_orders" DROP CONSTRAINT "fiverr_orders_profileId_fkey";

-- DropForeignKey
ALTER TABLE "fiverr_snapshots" DROP CONSTRAINT "fiverr_snapshots_profileId_fkey";

-- DropForeignKey
ALTER TABLE "payoneer_transactions" DROP CONSTRAINT "payoneer_transactions_accountId_fkey";

-- DropForeignKey
ALTER TABLE "pmak_transactions" DROP CONSTRAINT "pmak_transactions_accountId_fkey";

-- DropForeignKey
ALTER TABLE "upwork_orders" DROP CONSTRAINT "upwork_orders_profileId_fkey";

-- DropForeignKey
ALTER TABLE "upwork_snapshots" DROP CONSTRAINT "upwork_snapshots_profileId_fkey";

-- DropIndex
DROP INDEX "fiverr_profiles_name_key";

-- DropIndex
DROP INDEX "outside_orders_clientId_key";

-- DropIndex
DROP INDEX "payoneer_accounts_name_key";

-- DropIndex
DROP INDEX "pmak_accounts_name_key";

-- DropIndex
DROP INDEX "upwork_profiles_name_key";

-- AlterTable
ALTER TABLE "card_sharing" DROP COLUMN "cardCvcEncrypted",
DROP COLUMN "cardNoEncrypted",
DROP COLUMN "cardScreenshot",
ADD COLUMN     "cardCvc" TEXT NOT NULL,
ADD COLUMN     "cardNo" TEXT NOT NULL,
ADD COLUMN     "screenshotPath" TEXT,
ALTER COLUMN "serialNo" DROP DEFAULT,
ALTER COLUMN "serialNo" SET DATA TYPE TEXT,
ALTER COLUMN "details" DROP NOT NULL,
ALTER COLUMN "cardLimit" SET DATA TYPE DECIMAL(12,2),
ALTER COLUMN "cardPaymentRcv" SET DATA TYPE DECIMAL(12,2);
DROP SEQUENCE "card_sharing_serialNo_seq";

-- AlterTable
ALTER TABLE "dollar_exchanges" DROP COLUMN "fromParty",
DROP COLUMN "toParty",
DROP COLUMN "updatedAt",
ADD COLUMN     "accountFrom" TEXT,
ADD COLUMN     "accountTo" TEXT,
ALTER COLUMN "debit" SET DATA TYPE DECIMAL(12,2),
ALTER COLUMN "credit" SET DATA TYPE DECIMAL(12,2),
ALTER COLUMN "rate" SET DATA TYPE DECIMAL(8,2),
ALTER COLUMN "totalBdt" SET DATA TYPE DECIMAL(14,2);

-- AlterTable
ALTER TABLE "fiverr_orders" DROP COLUMN "clientName",
ADD COLUMN     "buyerName" TEXT NOT NULL,
ALTER COLUMN "amount" SET DATA TYPE DECIMAL(12,2);

-- AlterTable
ALTER TABLE "fiverr_profiles" DROP COLUMN "createdAt",
DROP COLUMN "name",
DROP COLUMN "updatedAt",
ADD COLUMN     "profileName" TEXT NOT NULL;

-- AlterTable
ALTER TABLE "hr_expenses" DROP COLUMN "fromParty",
DROP COLUMN "toParty",
ADD COLUMN     "accountFrom" TEXT,
ADD COLUMN     "accountTo" TEXT,
ALTER COLUMN "debit" SET DATA TYPE DECIMAL(12,2),
ALTER COLUMN "credit" SET DATA TYPE DECIMAL(12,2),
ALTER COLUMN "remainingBalance" SET DATA TYPE DECIMAL(12,2);

-- AlterTable
ALTER TABLE "inventory" DROP COLUMN "vendor",
ADD COLUMN     "assignedTo" TEXT,
ADD COLUMN     "condition" TEXT,
ALTER COLUMN "unitPrice" SET DATA TYPE DECIMAL(12,2),
ALTER COLUMN "totalPrice" SET DATA TYPE DECIMAL(12,2);

-- AlterTable
ALTER TABLE "outside_orders" DROP COLUMN "status",
ADD COLUMN     "orderStatus" "OrderStatus" NOT NULL DEFAULT 'PENDING',
ALTER COLUMN "orderAmount" SET DATA TYPE DECIMAL(12,2),
ALTER COLUMN "receiveAmount" SET DATA TYPE DECIMAL(12,2),
ALTER COLUMN "dueAmount" SET DATA TYPE DECIMAL(12,2);

-- AlterTable
ALTER TABLE "payoneer_accounts" DROP COLUMN "createdAt",
DROP COLUMN "name",
DROP COLUMN "updatedAt",
ADD COLUMN     "accountName" TEXT NOT NULL;

-- AlterTable
ALTER TABLE "payoneer_transactions" DROP COLUMN "fromParty",
DROP COLUMN "toParty",
ADD COLUMN     "accountFrom" TEXT,
ADD COLUMN     "accountTo" TEXT,
ALTER COLUMN "debit" SET DATA TYPE DECIMAL(12,2),
ALTER COLUMN "credit" SET DATA TYPE DECIMAL(12,2),
ALTER COLUMN "remainingBalance" SET DATA TYPE DECIMAL(12,2);

-- AlterTable
ALTER TABLE "pmak_accounts" DROP COLUMN "createdAt",
DROP COLUMN "name",
DROP COLUMN "updatedAt",
ADD COLUMN     "accountName" TEXT NOT NULL;

-- AlterTable
ALTER TABLE "pmak_transactions" DROP COLUMN "fromParty",
DROP COLUMN "toParty",
ADD COLUMN     "accountFrom" TEXT,
ADD COLUMN     "accountTo" TEXT,
ALTER COLUMN "debit" SET DATA TYPE DECIMAL(12,2),
ALTER COLUMN "credit" SET DATA TYPE DECIMAL(12,2),
ALTER COLUMN "remainingBalance" SET DATA TYPE DECIMAL(12,2);

-- AlterTable
ALTER TABLE "upwork_orders" ALTER COLUMN "amount" SET DATA TYPE DECIMAL(12,2);

-- AlterTable
ALTER TABLE "upwork_profiles" DROP COLUMN "createdAt",
DROP COLUMN "name",
DROP COLUMN "updatedAt",
ADD COLUMN     "profileName" TEXT NOT NULL;

-- DropTable
DROP TABLE "fiverr_snapshots";

-- DropTable
DROP TABLE "upwork_snapshots";

-- CreateTable
CREATE TABLE "fiverr_entries" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "availableWithdraw" DECIMAL(12,2) NOT NULL,
    "notCleared" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "activeOrders" INTEGER NOT NULL DEFAULT 0,
    "submitted" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "withdrawn" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "sellerPlus" BOOLEAN NOT NULL DEFAULT false,
    "promotion" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "profileId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "fiverr_entries_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "upwork_entries" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "availableWithdraw" DECIMAL(12,2) NOT NULL,
    "pending" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "inReview" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "workInProgress" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "withdrawn" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "connects" INTEGER NOT NULL DEFAULT 0,
    "upworkPlus" BOOLEAN NOT NULL DEFAULT false,
    "profileId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "upwork_entries_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "fiverr_entries_profileId_date_key" ON "fiverr_entries"("profileId", "date");

-- CreateIndex
CREATE UNIQUE INDEX "upwork_entries_profileId_date_key" ON "upwork_entries"("profileId", "date");

-- CreateIndex
CREATE UNIQUE INDEX "fiverr_profiles_profileName_key" ON "fiverr_profiles"("profileName");

-- CreateIndex
CREATE UNIQUE INDEX "payoneer_accounts_accountName_key" ON "payoneer_accounts"("accountName");

-- CreateIndex
CREATE UNIQUE INDEX "pmak_accounts_accountName_key" ON "pmak_accounts"("accountName");

-- CreateIndex
CREATE UNIQUE INDEX "upwork_profiles_profileName_key" ON "upwork_profiles"("profileName");

-- AddForeignKey
ALTER TABLE "fiverr_entries" ADD CONSTRAINT "fiverr_entries_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "fiverr_profiles"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "fiverr_orders" ADD CONSTRAINT "fiverr_orders_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "fiverr_profiles"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "upwork_entries" ADD CONSTRAINT "upwork_entries_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "upwork_profiles"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "upwork_orders" ADD CONSTRAINT "upwork_orders_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "upwork_profiles"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "payoneer_transactions" ADD CONSTRAINT "payoneer_transactions_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "payoneer_accounts"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "pmak_transactions" ADD CONSTRAINT "pmak_transactions_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "pmak_accounts"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
