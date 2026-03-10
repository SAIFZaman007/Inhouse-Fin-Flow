-- CreateTable
CREATE TABLE "DailyRate" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "rate" DECIMAL(10,4) NOT NULL,
    "setBy" TEXT,
    "note" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "DailyRate_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "DailyRate_date_idx" ON "DailyRate"("date");
