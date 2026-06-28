"""
Tests for pricing strategies — fully implemented.

These tests are the SPECIFICATION for what your code must do.
Read each test, then make it pass.
"""

from decimal import Decimal

import pytest

from billing_engine.money import Money
from billing_engine.pricing import FlatRate, UsageBased, TieredPricing, Tier, Freemium


# ========================================================
# FlatRate
# ========================================================
class TestFlatRate:
    def test_returns_fixed_amount(self):
        strat = FlatRate(Money("999", "INR"))
        assert strat.calculate(0) == Money("999", "INR")
        assert strat.calculate(10_000) == Money("999", "INR")

    def test_negative_amount_rejected(self):
        with pytest.raises(ValueError):
            FlatRate(Money("-100", "INR"))

    def test_non_money_rejected(self):
        with pytest.raises(TypeError):
            FlatRate(100)   # type: ignore[arg-type]

    def test_zero_amount_allowed(self):
        # A "free" plan is still a flat-rate plan with amount=0.
        strat = FlatRate(Money("0", "INR"))
        assert strat.calculate(50).is_zero()


# ========================================================
# UsageBased
# ========================================================
class TestUsageBased:
    def test_zero_usage(self):
        strat = UsageBased(Money("0.50", "INR"))
        assert strat.calculate(0) == Money("0", "INR")

    def test_simple_multiplication(self):
        strat = UsageBased(Money("0.50", "INR"))
        assert strat.calculate(100) == Money("50.00", "INR")

    def test_large_quantity(self):
        strat = UsageBased(Money("0.001", "INR"))
        # 1 million * 0.001 = 1000 exactly
        assert strat.calculate(1_000_000) == Money("1000.000", "INR")

    def test_negative_quantity_rejected(self):
        strat = UsageBased(Money("0.50", "INR"))
        with pytest.raises(ValueError):
            strat.calculate(-1)

    def test_negative_price_rejected(self):
        with pytest.raises(ValueError):
            UsageBased(Money("-0.50", "INR"))


# ========================================================
# TieredPricing
# ========================================================
class TestTieredPricing:
    @pytest.fixture
    def three_tier(self) -> TieredPricing:
        # 0–1000 @ ₹2.00 ; 1000–5000 @ ₹1.50 ; 5000+ @ ₹1.00
        return TieredPricing([
            Tier(0, 1000, Money("2.00", "INR")),
            Tier(1000, 5000, Money("1.50", "INR")),
            Tier(5000, None, Money("1.00", "INR")),
        ])

    def test_zero_quantity_costs_nothing(self, three_tier):
        assert three_tier.calculate(0) == Money("0", "INR")

    def test_within_first_tier(self, three_tier):
        # 500 units * ₹2 = ₹1000
        assert three_tier.calculate(500) == Money("1000.00", "INR")

    def test_exactly_at_first_tier_boundary(self, three_tier):
        # 1000 units * ₹2 = ₹2000 (still entirely in tier 1)
        assert three_tier.calculate(1000) == Money("2000.00", "INR")

    def test_one_above_first_tier_boundary(self, three_tier):
        # 1001 = 1000@₹2 + 1@₹1.5 = 2000 + 1.5 = 2001.5
        assert three_tier.calculate(1001) == Money("2001.50", "INR")

    def test_within_middle_tier(self, three_tier):
        # 3000 = 1000@₹2 + 2000@₹1.5 = 2000 + 3000 = 5000
        assert three_tier.calculate(3000) == Money("5000.00", "INR")

    def test_spans_three_tiers(self, three_tier):
        # 6000 = 1000@₹2 + 4000@₹1.50 + 1000@₹1.00 = 2000 + 6000 + 1000 = 9000
        assert three_tier.calculate(6000) == Money("9000.00", "INR")

    def test_huge_quantity_in_top_tier(self, three_tier):
        # 100000 = 1000@₹2 + 4000@₹1.50 + 95000@₹1 = 2000 + 6000 + 95000 = 103000
        assert three_tier.calculate(100_000) == Money("103000.00", "INR")

    def test_negative_quantity_rejected(self, three_tier):
        with pytest.raises(ValueError):
            three_tier.calculate(-1)

    def test_empty_tiers_rejected(self):
        with pytest.raises(ValueError):
            TieredPricing([])

    def test_non_contiguous_tiers_rejected(self):
        with pytest.raises(ValueError):
            TieredPricing([
                Tier(0, 1000, Money("2", "INR")),
                Tier(2000, None, Money("1", "INR")),   # gap from 1000-2000
            ])

    def test_top_tier_must_be_open_ended(self):
        with pytest.raises(ValueError):
            TieredPricing([
                Tier(0, 1000, Money("2", "INR")),
                Tier(1000, 5000, Money("1", "INR")),    # closed top tier - invalid
            ])

    def test_mixed_currencies_rejected(self):
        with pytest.raises(ValueError):
            TieredPricing([
                Tier(0, 1000, Money("2", "INR")),
                Tier(1000, None, Money("1", "USD")),
            ])


# ========================================================
# Freemium
# ========================================================
class TestFreemium:
    def test_below_quota_returns_zero(self):
        plan = Freemium(free_quota=1000, overage_strategy=UsageBased(Money("0.50", "INR")))
        assert plan.calculate(800) == Money("0", "INR")

    def test_exactly_at_quota_is_free(self):
        plan = Freemium(free_quota=1000, overage_strategy=UsageBased(Money("0.50", "INR")))
        assert plan.calculate(1000) == Money("0", "INR")

    def test_overage_delegates_to_inner(self):
        # 1200 = 200 overage * ₹0.50 = ₹100
        plan = Freemium(free_quota=1000, overage_strategy=UsageBased(Money("0.50", "INR")))
        assert plan.calculate(1200) == Money("100.00", "INR")

    def test_returns_inner_currency_when_free(self):
        plan = Freemium(free_quota=100, overage_strategy=UsageBased(Money("1", "USD")))
        assert plan.calculate(50).currency == "USD"

    def test_negative_quota_rejected(self):
        with pytest.raises(ValueError):
            Freemium(free_quota=-1, overage_strategy=UsageBased(Money("1", "INR")))

    def test_non_strategy_rejected(self):
        with pytest.raises(TypeError):
            Freemium(free_quota=100, overage_strategy="not a strategy")   # type: ignore[arg-type]

    def test_composition_with_tiered_inner(self):
        # First 100 units free, then tiered: 0–500@₹2, 500+@₹1
        inner = TieredPricing([
            Tier(0, 500, Money("2.00", "INR")),
            Tier(500, None, Money("1.00", "INR")),
        ])
        plan = Freemium(free_quota=100, overage_strategy=inner)
        # 700 total = 100 free + 600 overage
        # 600 in the tiered inner = 500@₹2 + 100@₹1 = 1000 + 100 = 1100
        assert plan.calculate(700) == Money("1100.00", "INR")
