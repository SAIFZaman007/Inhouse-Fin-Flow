-- CreateEnum
CREATE TYPE "Role" AS ENUM ('CEO', 'DIRECTOR', 'HR');

-- CreateEnum
CREATE TYPE "OrderStatus" AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED');

-- CreateEnum
CREATE TYPE "PaymentStatus" AS ENUM ('RECEIVED', 'DUE');

-- CreateTable
CREATE TABLE "User" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "passwordHash" TEXT NOT NULL,
    "role" "Role" NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "FiverrProfile" (
    "id" TEXT NOT NULL,
    "profileName" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "FiverrProfile_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "FiverrEntry" (
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

    CONSTRAINT "FiverrEntry_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "FiverrOrder" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "buyerName" TEXT NOT NULL,
    "orderId" TEXT NOT NULL,
    "amount" DECIMAL(12,2) NOT NULL,
    "profileId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "FiverrOrder_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "UpworkProfile" (
    "id" TEXT NOT NULL,
    "profileName" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "UpworkProfile_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "UpworkEntry" (
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

    CONSTRAINT "UpworkEntry_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "UpworkOrder" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "clientName" TEXT NOT NULL,
    "orderId" TEXT NOT NULL,
    "amount" DECIMAL(12,2) NOT NULL,
    "profileId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "UpworkOrder_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PayoneerAccount" (
    "id" TEXT NOT NULL,
    "accountName" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "PayoneerAccount_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PayoneerTransaction" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "details" TEXT NOT NULL,
    "accountFrom" TEXT,
    "accountTo" TEXT,
    "debit" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "credit" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "remainingBalance" DECIMAL(12,2) NOT NULL,
    "accountId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PayoneerTransaction_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PmakAccount" (
    "id" TEXT NOT NULL,
    "accountName" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "PmakAccount_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PmakTransaction" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "details" TEXT NOT NULL,
    "accountFrom" TEXT,
    "accountTo" TEXT,
    "debit" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "credit" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "remainingBalance" DECIMAL(12,2) NOT NULL,
    "accountId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PmakTransaction_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "OutsideOrder" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "clientId" TEXT NOT NULL,
    "clientName" TEXT NOT NULL,
    "clientLink" TEXT,
    "orderDetails" TEXT NOT NULL,
    "orderSheet" TEXT,
    "assignTeam" TEXT,
    "orderStatus" "OrderStatus" NOT NULL DEFAULT 'PENDING',
    "orderAmount" DECIMAL(12,2) NOT NULL,
    "receiveAmount" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "dueAmount" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "paymentMethod" TEXT,
    "paymentMethodDetails" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "OutsideOrder_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DollarExchange" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "details" TEXT NOT NULL,
    "accountFrom" TEXT,
    "accountTo" TEXT,
    "debit" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "credit" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "rate" DECIMAL(8,2) NOT NULL,
    "totalBdt" DECIMAL(14,2) NOT NULL,
    "paymentStatus" "PaymentStatus" NOT NULL DEFAULT 'DUE',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "DollarExchange_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "CardSharing" (
    "id" TEXT NOT NULL,
    "serialNo" TEXT NOT NULL,
    "details" TEXT,
    "payoneerAccount" TEXT NOT NULL,
    "cardNo" TEXT NOT NULL,
    "cardExpire" TEXT NOT NULL,
    "cardCvc" TEXT NOT NULL,
    "cardVendor" TEXT NOT NULL,
    "cardLimit" DECIMAL(12,2) NOT NULL,
    "cardPaymentRcv" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "cardRcvBank" TEXT,
    "mailDetails" TEXT,
    "screenshotPath" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "CardSharing_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "HrExpense" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "details" TEXT NOT NULL,
    "accountFrom" TEXT,
    "accountTo" TEXT,
    "debit" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "credit" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "remainingBalance" DECIMAL(12,2) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "HrExpense_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Inventory" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "itemName" TEXT NOT NULL,
    "category" TEXT,
    "quantity" INTEGER NOT NULL DEFAULT 1,
    "unitPrice" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "totalPrice" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "condition" TEXT,
    "assignedTo" TEXT,
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Inventory_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateIndex
CREATE UNIQUE INDEX "FiverrProfile_profileName_key" ON "FiverrProfile"("profileName");

-- CreateIndex
CREATE UNIQUE INDEX "FiverrEntry_profileId_date_key" ON "FiverrEntry"("profileId", "date");

-- CreateIndex
CREATE UNIQUE INDEX "FiverrOrder_orderId_key" ON "FiverrOrder"("orderId");

-- CreateIndex
CREATE UNIQUE INDEX "UpworkProfile_profileName_key" ON "UpworkProfile"("profileName");

-- CreateIndex
CREATE UNIQUE INDEX "UpworkEntry_profileId_date_key" ON "UpworkEntry"("profileId", "date");

-- CreateIndex
CREATE UNIQUE INDEX "UpworkOrder_orderId_key" ON "UpworkOrder"("orderId");

-- CreateIndex
CREATE UNIQUE INDEX "PayoneerAccount_accountName_key" ON "PayoneerAccount"("accountName");

-- CreateIndex
CREATE UNIQUE INDEX "PmakAccount_accountName_key" ON "PmakAccount"("accountName");

-- CreateIndex
CREATE UNIQUE INDEX "CardSharing_serialNo_key" ON "CardSharing"("serialNo");

-- AddForeignKey
ALTER TABLE "FiverrEntry" ADD CONSTRAINT "FiverrEntry_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "FiverrProfile"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "FiverrOrder" ADD CONSTRAINT "FiverrOrder_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "FiverrProfile"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "UpworkEntry" ADD CONSTRAINT "UpworkEntry_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "UpworkProfile"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "UpworkOrder" ADD CONSTRAINT "UpworkOrder_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "UpworkProfile"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PayoneerTransaction" ADD CONSTRAINT "PayoneerTransaction_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "PayoneerAccount"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PmakTransaction" ADD CONSTRAINT "PmakTransaction_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "PmakAccount"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
