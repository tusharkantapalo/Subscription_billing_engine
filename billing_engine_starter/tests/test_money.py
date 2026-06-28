"""
✅ FULLY WRITTEN — this is the template for the tests you will write
   in test_pricing.py, test_discounts.py, etc.

Read the names. Read the assertions. Notice:
    - Tests are tiny and focused.
    - One assertion per test where reasonable.
    - Edge cases (rounding, zero, currency mismatch) get their own tests.
    - No use of `float` anywhere.
"""

from decimal import Decimal

import pytest

from billing_engine.money import Money


class TestConstruction:
    def test_from_string(self):
        m = Money("1.50", "INR")
        assert m.amount == Decimal("1.50")
        assert m.currency == "INR"

    def test_from_int(self):
        m = Money(100, "USD")
        assert m.amount == Decimal("100")

    def test_from_decimal(self):
        m = Money(Decimal("9.99"), "EUR")
        assert m.amount == Decimal("9.99")

    def test_rejects_float(self):
        with pytest.raises(TypeError, match="float"):
            Money(1.50, "INR")

    def test_currency_upper_cased(self):
        assert Money(1, "inr").currency == "INR"

    def test_invalid_currency_rejected(self):
        with pytest.raises(ValueError):
            Money(1, "RUPEES")
        with pytest.raises(ValueError):
            Money(1, "")


class TestArithmetic:
    def test_add(self):
        a = Money("1.20", "INR")
        b = Money("0.30", "INR")
        assert (a + b).amount == Decimal("1.50")

    def test_subtract(self):
        a = Money("5.00", "INR")
        b = Money("2.50", "INR")
        assert (a - b).amount == Decimal("2.50")

    def test_multiply_by_int(self):
        assert (Money("2.50", "INR") * 4).amount == Decimal("10.00")

    def test_multiply_by_decimal(self):
        # 18% tax on 100 = 18
        assert (Money("100", "INR") * Decimal("0.18")).amount == Decimal("18.00")

    def test_multiply_by_float_rejected(self):
        with pytest.raises(TypeError):
            Money("10", "INR") * 1.5

    def test_multiply_money_by_money_rejected(self):
        with pytest.raises(TypeError):
            Money("10", "INR") * Money("2", "INR")

    def test_negate(self):
        assert (-Money("5", "INR")).amount == Decimal("-5")

    def test_currency_mismatch_addition(self):
        with pytest.raises(ValueError, match="Cannot mix currencies"):
            Money(1, "INR") + Money(1, "USD")


class TestComparison:
    def test_less_than(self):
        assert Money("1", "INR") < Money("2", "INR")

    def test_currency_mismatch_comparison(self):
        with pytest.raises(ValueError):
            assert Money(1, "INR") < Money(1, "USD")

    def test_zero_detection(self):
        assert Money(0, "INR").is_zero()
        assert not Money(1, "INR").is_zero()


class TestRounding:
    def test_banker_rounding_down(self):
        # 0.125 → 0.12 with HALF_EVEN (rounds to even, 2 is even)
        assert Money("0.125", "INR").rounded().amount == Decimal("0.12")

    def test_banker_rounding_up(self):
        # 0.135 → 0.14 (4 is even)
        assert Money("0.135", "INR").rounded().amount == Decimal("0.14")

    def test_storage_form(self):
        assert Money("1.5", "INR").to_storage() == "1.50"
