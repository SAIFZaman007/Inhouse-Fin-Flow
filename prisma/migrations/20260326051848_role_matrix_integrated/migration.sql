-- CreateEnum
CREATE TYPE "VisibilityStatus" AS ENUM ('VISIBLE', 'HIDDEN');

-- AlterTable
ALTER TABLE "card_sharing" ADD COLUMN     "cardReceiveBank" TEXT NOT NULL DEFAULT '';

-- CreateTable
CREATE TABLE "permission_rules" (
    "id" TEXT NOT NULL,
    "moduleName" TEXT NOT NULL,
    "ceo_access" "VisibilityStatus" NOT NULL DEFAULT 'VISIBLE',
    "director_access" "VisibilityStatus" NOT NULL DEFAULT 'VISIBLE',
    "hr_access" "VisibilityStatus" NOT NULL DEFAULT 'HIDDEN',
    "bdev_access" "VisibilityStatus" NOT NULL DEFAULT 'HIDDEN',
    "displayOrder" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "permission_rules_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "terms_conditions" (
    "id" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "version" INTEGER NOT NULL DEFAULT 1,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "terms_conditions_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "permission_rules_moduleName_key" ON "permission_rules"("moduleName");

-- CreateIndex
CREATE INDEX "permission_rules_moduleName_idx" ON "permission_rules"("moduleName");

-- AddForeignKey
ALTER TABLE "card_sharing" ADD CONSTRAINT "card_sharing_accountId_fkey" FOREIGN KEY ("accountId") REFERENCES "payoneer_accounts"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
