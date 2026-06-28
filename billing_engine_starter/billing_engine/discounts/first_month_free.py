"""
FirstMonthFree — 100% off the very first invoice for a subscription, 0% after.

Uses DiscountContext.invoice_count_so_far to decide:
    - 0  => this IS the first invoice => discount = subtotal (100% off)
    - >0 => not the first              => discount = 0
"""

from billing_engine.money import Money
from billing_engine.discounts.base import Discount, DiscountContext


class FirstMonthFree(Discount):
    def apply(self, subtotal: Money, context: DiscountContext) -> Money:

        if context.invoice_count_so_far == 0:
            return subtotal
        else:
            return Money.zero(subtotal.currency)
