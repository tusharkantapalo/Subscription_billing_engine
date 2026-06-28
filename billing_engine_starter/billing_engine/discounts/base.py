"""
Discount abstract base class.

✅ COMPLETE. Subclasses live in sibling files.

Contract:
    apply(subtotal, context) -> Money
        Returns the discount AMOUNT (a non-negative Money) to subtract from
        subtotal. Never returns more than subtotal — the discounted total
        must never go below zero.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from billing_engine.money import Money


@dataclass(frozen=True)
class DiscountContext:
    """Extra information a discount may need to make its decision.

    Add more fields here if a new discount type requires them.
    """
    invoice_count_so_far: int   # 0 = this is the first invoice for the subscription


class Discount(ABC):
    """Computes a discount amount to subtract from a subtotal."""

    @abstractmethod
    def apply(self, subtotal: Money, context: DiscountContext) -> Money:
        """Return the non-negative discount amount, capped at subtotal."""
        raise NotImplementedError
