/*
  Warnings:

  - You are about to drop the `CardSharing` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `DollarExchange` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `FiverrEntry` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `FiverrOrder` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `FiverrProfile` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `HrExpense` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `Inventory` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `OutsideOrder` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `PayoneerAccount` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `PayoneerTransaction` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `PmakAccount` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `PmakTransaction` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `UpworkEntry` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `UpworkOrder` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `UpworkProfile` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `User` table. If the table is not empty, all the data it contains will be lost.

*/
-- CreateEnum
CREATE TYPE "InvitationStatus" AS ENUM ('PENDING', 'ACCEPTED', 'EXPIRED', 'CANCELLED');

-- DropForeignKey
ALTER TABLE "FiverrEntry" DROP CONSTRAINT "FiverrEntry_profileId_fkey";

-- DropForeignKey
ALTER TABLE "FiverrOrder" DROP CONSTRAINT "FiverrOrder_profileId_fkey";

-- DropForeignKey
ALTER TABLE "PayoneerTransaction" DROP CONSTRAINT "PayoneerTransaction_accountId_fkey";

-- DropForeignKey
ALTER TABLE "PmakTransaction" DROP CONSTRAINT "PmakTransaction_accountId_fkey";

-- DropForeignKey
ALTER TABLE "UpworkEntry" DROP CONSTRAINT "UpworkEntry_profileId_fkey";

-- DropForeignKey
ALTER TABLE "UpworkOrder" DROP CONSTRAINT "UpworkOrder_profileId_fkey";

-- DropTable
DROP TABLE "CardSharing";

-- DropTable
DROP TABLE "DollarExchange";

-- DropTable
DROP TABLE "FiverrEntry";

-- DropTable
DROP TABLE "FiverrOrder";

-- DropTable
DROP TABLE "FiverrProfile";

-- DropTable
DROP TABLE "HrExpense";

-- DropTable
DROP TABLE "Inventory";

-- DropTable
DROP TABLE "OutsideOrder";

-- DropTable
DROP TABLE "PayoneerAccount";

-- DropTable
DROP TABLE "PayoneerTransaction";

-- DropTable
DROP TABLE "PmakAccount";

-- DropTable
DROP TABLE "PmakTransaction";

-- DropTable
DROP TABLE "UpworkEntry";

-- DropTable
DROP TABLE "UpworkOrder";

-- DropTable
DROP TABLE "UpworkProfile";

-- DropTable
DROP TABLE "User";

-- CreateTable
CREATE TABLE "users" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "passwordHash" TEXT NOT NULL,
    "role" "Role" NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "fiverr_profiles" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "fiverr_profiles_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "fiverr_snapshots" (
    "id" TEXT NOT NULL,
    "profileId" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "availableWithdraw" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "notCleared" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "activeOrders" INTEGER NOT NULL DEFAULT 0,
    "submitted" INTEGER NOT NULL DEFAULT 0,
    "withdrawn" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "sellerPlus" BOOLEAN NOT NULL DEFAULT false,
    "promotion" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "fiverr_snapshots_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "fiverr_orders" (
    "id" TEXT NOT NULL,
    "profileId" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "clientName" TEXT NOT NULL,
    "orderId" TEXT NOT NULL,
    "amount" DECIMAL(14,2) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "fiverr_orders_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "upwork_profiles" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "upwork_profiles_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "upwork_snapshots" (
    "id" TEXT NOT NULL,
    "profileId" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "availableWithdraw" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "pending" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "inReview" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "workInProgress" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "withdrawn" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "connect" INTEGER NOT NULL DEFAULT 0,
    "upworkPlus" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "upwork_snapshots_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "upwork_orders" (
    "id" TEXT NOT NULL,
    "profileId" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "clientName" TEXT NOT NULL,
    "orderId" TEXT NOT NULL,
    "amount" DECIMAL(14,2) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "upwork_orders_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "payoneer_accounts" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "payoneer_accounts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "payoneer_transactions" (
    "id" TEXT NOT NULL,
    "accountId" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "details" TEXT NOT NULL,
    "fromParty" TEXT,
    "toParty" TEXT,
    "debit" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "credit" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "remainingBalance" DECIMAL(14,2) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "payoneer_transactions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "pmak_accounts" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "pmak_accounts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "pmak_transactions" (
    "id" TEXT NOT NULL,
    "accountId" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "details" TEXT NOT NULL,
    "fromParty" TEXT,
    "toParty" TEXT,
    "debit" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "credit" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "remainingBalance" DECIMAL(14,2) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "pmak_transactions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "outside_orders" (
    "id" TEXT NOT NULL,
    "clientId" TEXT NOT NULL,
    "clientName" TEXT NOT NULL,
    "clientLink" TEXT,
    "orderDetails" TEXT NOT NULL,
    "orderSheet" TEXT,
    "assignTeam" TEXT,
    "status" "OrderStatus" NOT NULL DEFAULT 'PENDING',
    "orderAmount" DECIMAL(14,2) NOT NULL,
    "receiveAmount" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "dueAmount" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "paymentMethod" TEXT,
    "paymentMethodDetails" TEXT,
    "date" DATE NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "outside_orders_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "dollar_exchanges" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "details" TEXT NOT NULL,
    "fromParty" TEXT,
    "toParty" TEXT,
    "debit" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "credit" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "rate" DECIMAL(10,4) NOT NULL,
    "totalBdt" DECIMAL(16,2) NOT NULL,
    "paymentStatus" "PaymentStatus" NOT NULL DEFAULT 'DUE',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "dollar_exchanges_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "card_sharing" (
    "id" TEXT NOT NULL,
    "serialNo" SERIAL NOT NULL,
    "details" TEXT NOT NULL,
    "payoneerAccount" TEXT NOT NULL,
    "cardNoEncrypted" TEXT NOT NULL,
    "cardExpire" TEXT NOT NULL,
    "cardCvcEncrypted" TEXT NOT NULL,
    "cardScreenshot" TEXT,
    "cardVendor" TEXT NOT NULL,
    "cardLimit" DECIMAL(14,2) NOT NULL,
    "cardPaymentRcv" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "cardRcvBank" TEXT,
    "mailDetails" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "card_sharing_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "hr_expenses" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "details" TEXT NOT NULL,
    "fromParty" TEXT,
    "toParty" TEXT,
    "debit" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "credit" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "remainingBalance" DECIMAL(14,2) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "hr_expenses_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "inventory" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "itemName" TEXT NOT NULL,
    "category" TEXT,
    "quantity" INTEGER NOT NULL DEFAULT 1,
    "unitPrice" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "totalPrice" DECIMAL(14,2) NOT NULL DEFAULT 0,
    "vendor" TEXT,
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "inventory_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "invitations" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "role" "Role" NOT NULL,
    "inviteToken" TEXT NOT NULL,
    "status" "InvitationStatus" NOT NULL DEFAULT 'PENDING',
    "invitedBy" TEXT NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "acceptedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "invitations_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "users_email_key" ON "users"("email");

-- CreateIndex
CREATE UNIQUE INDEX "fiverr_profiles_name_key" ON "fiverr_profiles"("name");

-- CreateIndex
CREATE UNIQUE INDEX "fiverr_snapshots_profileId_date_key" ON "fiverr_snapshots"("profileId", "date");

-- CreateIndex
CREATE UNIQUE INDEX "fiverr_orders_orderId_key" ON "fiverr_orders"("orderId");

-- CreateIndex
CREATE UNIQUE INDEX "upwork_profiles_name_key" ON "upwork_profiles"("name");

-- CreateIndex
CREATE UNIQUE INDEX "upwork_snapshots_profileId_date_key" ON "upwork_snapshots"("profileId", "date");

-- CreateIndex
CREATE UNIQUE INDEX "upwork_orders_orderId_key" ON "upwork_orders"("orderId");

-- CreateIndex
CREATE UNIQUE INDEX "payoneer_accounts_name_key" ON "payoneer_accounts"("name");

-- CreateIndex
CREATE UNIQUE INDEX "pmak_accounts_name_key" ON "pmak_accounts"("name");

-- CreateIndex
CREATE UNIQUE INDEX "outside_orders_clientId_key" ON "outside_orders"("clientId");

-- CreateIndex
CREATE UNIQUE INDEX "card_sharing_serialNo_key" ON "card_sharing"("serialNo");

-- CreateIndex
CREATE UNIQUE INDEX "invitations_inviteToken_key" ON "invitations"("inviteToken");

-- CreateIndex
CREATE INDEX "invitations_email_idx" ON "invitations"("email");

-- CreateIndex
CREATE INDEX "invitations_inviteToken_idx" ON "invitations"("inviteToken");

-- CreateIndex
CREATE INDEX "invitations_status_idx" ON "invitations"("status");

-- AddForeignKey
ALTER TABLE "fiverr_snapshots" ADD CONSTRAINT "fiverr_snapshots_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "fiverr_profiles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "fiverr_orders" ADD CONSTRAINT "fiverr_orders_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "fiverr_profiles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "upwork_snapshots" ADD CONSTRAINT "upwork_snapshots_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "upwork_profiles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "upwork_orders" ADD CONSTRAINT "upwork_orders_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "upwork_profiles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "payoneer_transactions" ADD CONSTRAINT "payoneer_transactions_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "payoneer_accounts"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "pmak_transactions" ADD CONSTRAINT "pmak_transactions_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "pmak_accounts"("id") ON DELETE CASCADE ON UPDATE CASCADE;
