"""Invoice + InvoiceLineItem dataclasses + enums. ✅ COMPLETE."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional

from billing_engine.money import Money


class InvoiceStatus(str, Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PAID = "PAID"
    FAILED = "FAILED"
    VOID = "VOID"


class LineItemKind(str, Enum):
    BASE = "BASE"
    USAGE = "USAGE"
    DISCOUNT = "DISCOUNT"             # negative amount
    TAX = "TAX"
    PRORATION_CREDIT = "PRORATION_CREDIT"   # negative
    PRORATION_CHARGE = "PRORATION_CHARGE"   # positive


@dataclass(frozen=True)
class InvoiceLineItem:
    id: Optional[int]
    invoice_id: Optional[int]
    description: str
    amount: Money
    kind: LineItemKind


@dataclass
class Invoice:
    id: Optional[int]
    subscription_id: int
    period_start: date
    period_end: date
    subtotal: Money
    discount_total: Money
    tax_total: Money
    total: Money
    status: InvoiceStatus
    issued_at: Optional[datetime] = None
    pdf_path: Optional[str] = None
    line_items: list[InvoiceLineItem] = field(default_factory=list)
