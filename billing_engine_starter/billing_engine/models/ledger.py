"""LedgerEntry — append-only accounting record. ✅ COMPLETE."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from billing_engine.money import Money


class LedgerDirection(str, Enum):
    DEBIT = "DEBIT"     # customer owes us (invoice issued)
    CREDIT = "CREDIT"   # we received money OR reversal


@dataclass(frozen=True)
class LedgerEntry:
    id: Optional[int]
    invoice_id: Optional[int]   # may be None for adjustments
    customer_id: int
    amount: Money
    direction: LedgerDirection
    reason: str
    created_at: Optional[datetime] = None
