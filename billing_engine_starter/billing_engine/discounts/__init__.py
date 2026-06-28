"""Discount strategies."""
from .base import Discount, DiscountContext
from .percentage import PercentageDiscount
from .fixed import FixedAmountDiscount
from .first_month_free import FirstMonthFree

__all__ = [
    "Discount",
    "DiscountContext",
    "PercentageDiscount",
    "FixedAmountDiscount",
    "FirstMonthFree",
]
