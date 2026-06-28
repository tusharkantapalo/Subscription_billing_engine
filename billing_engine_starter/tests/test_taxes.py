"""Tests for tax calculators — fully implemented."""

from decimal import Decimal

import pytest

from billing_engine.money import Money
from billing_engine.taxes import NoTax, VATCalculator, GSTCalculator, TaxContext, TaxCalculator


# ========================================================
# NoTax
# ========================================================
class TestNoTax:
    def test_returns_zero_total(self):
        breakdown = NoTax().apply(Money("1000", "INR"), TaxContext(customer_country="AE"))
        assert breakdown.total == Money("0", "INR")

    def test_returns_empty_components(self):
        breakdown = NoTax().apply(Money("1000", "INR"), TaxContext(customer_country="AE"))
        assert breakdown.components == []

    def test_preserves_currency(self):
        breakdown = NoTax().apply(Money("100", "USD"), TaxContext(customer_country="US"))
        assert breakdown.total.currency == "USD"


# ========================================================
# VATCalculator
# ========================================================
class TestVATCalculator:
    def test_nineteen_percent_german_vat(self):
        breakdown = VATCalculator(Decimal("0.19")).apply(
            Money("100", "EUR"), TaxContext(customer_country="DE")
        )
        assert breakdown.total == Money("19.00", "EUR")

    def test_one_component_returned(self):
        breakdown = VATCalculator(Decimal("0.19")).apply(
            Money("100", "EUR"), TaxContext(customer_country="DE")
        )
        assert len(breakdown.components) == 1

    def test_zero_rate_returns_zero(self):
        breakdown = VATCalculator(Decimal("0")).apply(
            Money("100", "EUR"), TaxContext(customer_country="DE")
        )
        assert breakdown.total == Money("0", "EUR")

    def test_rate_above_one_rejected(self):
        with pytest.raises(ValueError):
            VATCalculator(Decimal("1.5"))

    def test_negative_rate_rejected(self):
        with pytest.raises(ValueError):
            VATCalculator(Decimal("-0.1"))

    def test_float_rate_rejected(self):
        with pytest.raises(TypeError):
            VATCalculator(0.19)   # type: ignore[arg-type]


# ========================================================
# GSTCalculator
# ========================================================
class TestGSTCalculator:
    @pytest.fixture
    def gst(self) -> GSTCalculator:
        return GSTCalculator(
            cgst=Decimal("0.09"),
            sgst=Decimal("0.09"),
            igst=Decimal("0.18"),
        )

    def test_intra_state_total(self, gst):
        ctx = TaxContext(customer_country="IN", customer_state="MH", seller_state="MH")
        breakdown = gst.apply(Money("1000", "INR"), ctx)
        assert breakdown.total == Money("180.00", "INR")

    def test_intra_state_splits_cgst_sgst(self, gst):
        ctx = TaxContext(customer_country="IN", customer_state="MH", seller_state="MH")
        breakdown = gst.apply(Money("1000", "INR"), ctx)
        assert len(breakdown.components) == 2

    def test_inter_state_total(self, gst):
        ctx = TaxContext(customer_country="IN", customer_state="KA", seller_state="MH")
        breakdown = gst.apply(Money("1000", "INR"), ctx)
        assert breakdown.total == Money("180.00", "INR")

    def test_inter_state_single_igst_component(self, gst):
        ctx = TaxContext(customer_country="IN", customer_state="KA", seller_state="MH")
        breakdown = gst.apply(Money("1000", "INR"), ctx)
        assert len(breakdown.components) == 1

    def test_no_customer_state_defaults_to_igst(self, gst):
        ctx = TaxContext(customer_country="IN", customer_state="", seller_state="MH")
        breakdown = gst.apply(Money("1000", "INR"), ctx)
        assert len(breakdown.components) == 1

    def test_cgst_sgst_must_equal_igst(self):
        # 0.09 + 0.05 != 0.18 → invalid configuration
        with pytest.raises(ValueError):
            GSTCalculator(
                cgst=Decimal("0.09"),
                sgst=Decimal("0.05"),
                igst=Decimal("0.18"),
            )


# ========================================================
# Factory
# ========================================================
class TestFactory:
    def test_india_returns_gst(self):
        assert isinstance(TaxCalculator.for_country("IN"), GSTCalculator)

    def test_germany_returns_vat(self):
        assert isinstance(TaxCalculator.for_country("DE"), VATCalculator)

    def test_france_returns_vat(self):
        assert isinstance(TaxCalculator.for_country("FR"), VATCalculator)

    def test_unknown_returns_no_tax(self):
        assert isinstance(TaxCalculator.for_country("ZZ"), NoTax)

    def test_lowercase_country_works(self):
        # "in" → "IN" internally
        assert isinstance(TaxCalculator.for_country("in"), GSTCalculator)
