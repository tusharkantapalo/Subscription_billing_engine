"""
FixedAmountDiscount — e.g., flat ₹500 off.

CAPPING RULE: if the fixed amount exceeds the subtotal, return subtotal
(so the discounted total never goes below zero).
"""

from billing_engine.money import Money
from billing_engine.discounts.base import Discount, DiscountContext


class FixedAmountDiscount(Discount):
    def __init__(self, amount: Money) -> None:
        
        if not isinstance(amount, Money):
            raise TypeError("Amount must be of type Money!")
        
        if amount.is_negative():
            raise ValueError("Amount cannot be negative!")
        
        self.amount = amount

    def apply(self, subtotal: Money, context: DiscountContext) -> Money:
        
        if self.amount.currency == subtotal.currency:
            return min(self.amount, subtotal)
        else:
            raise ValueError("Currency mismatch between amount and subtotal!")
        