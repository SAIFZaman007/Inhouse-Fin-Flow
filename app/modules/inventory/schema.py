"""
app/modules/inventory/schema.py

Built directly from schema.prisma (source of truth):

  model Inventory {
    id          String   @id @default(cuid())
    date        DateTime @db.Date
    itemName    String
    category    String?
    quantity    Int      @default(1)
    unitPrice   Decimal  @db.Decimal(12, 2) @default(0)
    totalPrice  Decimal  @db.Decimal(12, 2) @default(0)
    condition   String?
    assignedTo  String?
    notes       String?
    createdAt   DateTime @default(now())
    updatedAt   DateTime @updatedAt
    @@map("inventory")
  }
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, model_validator


class InventoryCreate(BaseModel):
    date: date
    itemName: str                           
    category: Optional[str] = None
    quantity: int = 1
    unitPrice: Decimal = Decimal("0")      
    condition: Optional[str] = None
    assignedTo: Optional[str] = None       
    notes: Optional[str] = None

    @model_validator(mode="after")
    def compute_total_price(self):
        self.totalPrice = self.unitPrice * self.quantity
        return self

    totalPrice: Decimal = Decimal("0")   


class InventoryUpdate(BaseModel):
    itemName: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[int] = None
    unitPrice: Optional[Decimal] = None
    condition: Optional[str] = None
    assignedTo: Optional[str] = None
    notes: Optional[str] = None


class InventoryResponse(BaseModel):
    id: str
    date: date
    itemName: str                           
    category: Optional[str]
    quantity: int
    unitPrice: Decimal                      
    totalPrice: Decimal                    
    condition: Optional[str]
    assignedTo: Optional[str]             
    notes: Optional[str]
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True