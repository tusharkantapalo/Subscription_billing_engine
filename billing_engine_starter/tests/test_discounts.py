"""Tests for discount strategies — fully implemented."""

from decimal import Decimal

import pytest

from billing_engine.money import Money
from billing_engine.discounts import (
    PercentageDiscount, FixedAmountDiscount, FirstMonthFree, DiscountContext,
)


# ========================================================
# PercentageDiscount
# ========================================================
class TestPercentageDiscount:
    def test_twenty_percent(self):
        d = PercentageDiscount(Decimal("0.20"))
        assert d.apply(Money("1000", "INR"), DiscountContext(0)) == Money("200.00", "INR")

    def test_zero_percent_is_no_discount(self):
        d = PercentageDiscount(Decimal("0"))
        assert d.apply(Money("1000", "INR"), DiscountContext(5)) == Money("0", "INR")

    def test_one_hundred_percent(self):
        d = PercentageDiscount(Decimal("1"))
        assert d.apply(Money("750", "INR"), DiscountContext(0)) == Money("750.00", "INR")

    def test_above_one_rejected(self):
        with pytest.raises(ValueError):
            PercentageDiscount(Decimal("1.5"))

    def test_below_zero_rejected(self):
        with pytest.raises(ValueError):
            PercentageDiscount(Decimal("-0.1"))

    def test_float_rejected(self):
        with pytest.raises(TypeError):
            PercentageDiscount(0.20)   # type: ignore[arg-type]

    def test_currency_preserved(self):
        d = PercentageDiscount(Decimal("0.10"))
        assert d.apply(Money("100", "USD"), DiscountContext(0)).currency == "USD"


# ========================================================
# FixedAmountDiscount
# ========================================================
class TestFixedAmountDiscount:
    def test_simple_subtraction_amount(self):
        d = FixedAmountDiscount(Money("100", "INR"))
        assert d.apply(Money("500", "INR"), DiscountContext(0)) == Money("100.00", "INR")

    def test_caps_at_subtotal(self):
        # Discount of ₹2000 against subtotal of ₹500 → discount is capped at ₹500
        d = FixedAmountDiscount(Money("2000", "INR"))
        assert d.apply(Money("500", "INR"), DiscountContext(0)) == Money("500.00", "INR")

    def test_exact_subtotal_returns_subtotal(self):
        d = FixedAmountDiscount(Money("500", "INR"))
        assert d.apply(Money("500", "INR"), DiscountContext(0)) == Money("500.00", "INR")

    def test_currency_mismatch_rejected(self):
        d = FixedAmountDiscount(Money("100", "INR"))
        with pytest.raises(ValueError):
            d.apply(Money("500", "USD"), DiscountContext(0))

    def test_negative_amount_rejected(self):
        with pytest.raises(ValueError):
            FixedAmountDiscount(Money("-100", "INR"))


# ========================================================
# FirstMonthFree
# ========================================================
class TestFirstMonthFree:
    def test_first_invoice_is_free(self):
        d = FirstMonthFree()
        result = d.apply(Money("999", "INR"), DiscountContext(invoice_count_so_far=0))
        assert result == Money("999.00", "INR")

    def test_second_invoice_no_discount(self):
        d = FirstMonthFree()
        result = d.apply(Money("999", "INR"), DiscountContext(invoice_count_so_far=1))
        assert result == Money("0", "INR")

    def test_zero_subtotal_does_not_crash(self):
        d = FirstMonthFree()
        result = d.apply(Money("0", "INR"), DiscountContext(invoice_count_so_far=0))
        assert result == Money("0", "INR")

    def test_currency_preserved(self):
        d = FirstMonthFree()
        result = d.apply(Money("100", "USD"), DiscountContext(invoice_count_so_far=0))
        assert result.currency == "USD"
