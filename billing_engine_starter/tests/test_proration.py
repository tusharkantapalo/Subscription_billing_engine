"""Tests for compute_proration — fully implemented (Day 4 stretch)."""

from datetime import date
from decimal import Decimal

import pytest

from billing_engine.billing.proration import compute_proration, ProrationResult
from billing_engine.money import Money
from billing_engine.taxes import GSTCalculator, NoTax, TaxContext


def _no_tax_ctx() -> TaxContext:
    return TaxContext(customer_country="AE")


def _gst_ctx() -> TaxContext:
    return TaxContext(customer_country="IN", customer_state="MH", seller_state="MH")


class TestProrationDayCount:
    def test_midpoint_no_tax(self):
        # Jan: 31 days. Switch on day 16 → used 15 days, remaining 16.
        # ratio = 16/31. Old price ₹1000 → credit ≈ 516.13. New ₹2000 → charge ≈ 1032.26.
        result = compute_proration(
            old_plan_price=Money("1000", "INR"),
            new_plan_price=Money("2000", "INR"),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            switch_date=date(2026, 1, 16),
            tax_calc=NoTax(),
            tax_context=_no_tax_ctx(),
        )
        assert result.credit_amount == Money("516.13", "INR")
        assert result.charge_amount == Money("1032.26", "INR")
        assert result.credit_tax == Money("0", "INR")
        assert result.charge_tax == Money("0", "INR")

    def test_first_day_credits_almost_full(self):
        # Switch on period_start → used 0 days, remaining = total.
        result = compute_proration(
            old_plan_price=Money("1000", "INR"),
            new_plan_price=Money("1000", "INR"),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            switch_date=date(2026, 1, 1),
            tax_calc=NoTax(),
            tax_context=_no_tax_ctx(),
        )
        assert result.credit_amount == Money("1000.00", "INR")
        assert result.charge_amount == Money("1000.00", "INR")

    def test_last_day_credits_zero(self):
        # Switch on period_end → used everything, remaining 0.
        result = compute_proration(
            old_plan_price=Money("1000", "INR"),
            new_plan_price=Money("2000", "INR"),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            switch_date=date(2026, 2, 1),
            tax_calc=NoTax(),
            tax_context=_no_tax_ctx(),
        )
        assert result.credit_amount == Money("0.00", "INR")
        assert result.charge_amount == Money("0.00", "INR")

    def test_downgrade_credit_greater_than_charge(self):
        # ₹2000 → ₹1000 at midpoint
        result = compute_proration(
            old_plan_price=Money("2000", "INR"),
            new_plan_price=Money("1000", "INR"),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            switch_date=date(2026, 1, 16),
            tax_calc=NoTax(),
            tax_context=_no_tax_ctx(),
        )
        assert result.credit_amount > result.charge_amount


class TestProrationTax:
    def test_tax_recalculated_on_both_legs_gst(self):
        # 18% GST on both legs
        result = compute_proration(
            old_plan_price=Money("1000", "INR"),
            new_plan_price=Money("2000", "INR"),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            switch_date=date(2026, 1, 16),
            tax_calc=GSTCalculator(Decimal("0.09"), Decimal("0.09"), Decimal("0.18")),
            tax_context=_gst_ctx(),
        )
        # 18% of 516.13 ≈ 92.90; 18% of 1032.26 ≈ 185.81
        assert result.credit_tax == Money("92.90", "INR")
        assert result.charge_tax == Money("185.81", "INR")


class TestProrationValidation:
    def test_switch_before_period_raises(self):
        with pytest.raises(ValueError):
            compute_proration(
                old_plan_price=Money("1000", "INR"),
                new_plan_price=Money("2000", "INR"),
                period_start=date(2026, 1, 1),
                period_end=date(2026, 2, 1),
                switch_date=date(2025, 12, 31),
                tax_calc=NoTax(),
                tax_context=_no_tax_ctx(),
            )

    def test_switch_after_period_raises(self):
        with pytest.raises(ValueError):
            compute_proration(
                old_plan_price=Money("1000", "INR"),
                new_plan_price=Money("2000", "INR"),
                period_start=date(2026, 1, 1),
                period_end=date(2026, 2, 1),
                switch_date=date(2026, 2, 2),
                tax_calc=NoTax(),
                tax_context=_no_tax_ctx(),
            )

    def test_currency_mismatch_raises(self):
        with pytest.raises(ValueError):
            compute_proration(
                old_plan_price=Money("1000", "INR"),
                new_plan_price=Money("2000", "EUR"),
                period_start=date(2026, 1, 1),
                period_end=date(2026, 2, 1),
                switch_date=date(2026, 1, 16),
                tax_calc=NoTax(),
                tax_context=_no_tax_ctx(),
            )
