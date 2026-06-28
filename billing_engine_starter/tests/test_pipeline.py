"""Tests for the invoicing pipeline (pure function) — fully implemented."""

from datetime import date
from decimal import Decimal

import pytest

from billing_engine.money import Money
from billing_engine.billing.pipeline import build_invoice
from billing_engine.pricing import FlatRate, UsageBased
from billing_engine.discounts import PercentageDiscount, FixedAmountDiscount
from billing_engine.taxes import GSTCalculator, NoTax, VATCalculator, TaxContext
from billing_engine.models import (
    Subscription, SubscriptionStatus, Plan, PricingType, BillingPeriod,
    InvoiceStatus, LineItemKind,
)


def _sub() -> Subscription:
    return Subscription(
        id=1, customer_id=1, plan_id=1,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=date(2026, 1, 1),
        current_period_end=date(2026, 2, 1),
    )


def _plan() -> Plan:
    return Plan(
        id=1, name="Pro",
        pricing_type=PricingType.FLAT,
        billing_period=BillingPeriod.MONTHLY,
        currency="INR",
    )


class TestPipeline:
    def test_flat_no_discount_no_tax(self):
        inv = build_invoice(
            subscription=_sub(), plan=_plan(),
            strategy=FlatRate(Money("1000", "INR")),
            discount=None,
            tax_calc=NoTax(),
            tax_context=TaxContext(customer_country="AE"),
            usage_quantity=0,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            invoice_count_so_far=0,
        )
        assert inv.subtotal == Money("1000", "INR")
        assert inv.discount_total == Money("0", "INR")
        assert inv.tax_total == Money("0", "INR")
        assert inv.total == Money("1000", "INR")
        assert inv.status == InvoiceStatus.DRAFT

    def test_discount_then_tax_order(self):
        # ₹1000 flat - 10% discount = ₹900 taxable - 18% GST = ₹162 tax → total ₹1062
        inv = build_invoice(
            subscription=_sub(), plan=_plan(),
            strategy=FlatRate(Money("1000", "INR")),
            discount=PercentageDiscount(Decimal("0.10")),
            tax_calc=GSTCalculator(Decimal("0.09"), Decimal("0.09"), Decimal("0.18")),
            tax_context=TaxContext(customer_country="IN", customer_state="MH", seller_state="MH"),
            usage_quantity=0,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            invoice_count_so_far=0,
        )
        assert inv.subtotal == Money("1000.00", "INR")
        assert inv.discount_total == Money("100.00", "INR")
        assert inv.tax_total == Money("162.00", "INR")
        assert inv.total == Money("1062.00", "INR")

    def test_line_items_for_intra_state_gst(self):
        inv = build_invoice(
            subscription=_sub(), plan=_plan(),
            strategy=FlatRate(Money("1000", "INR")),
            discount=PercentageDiscount(Decimal("0.10")),
            tax_calc=GSTCalculator(Decimal("0.09"), Decimal("0.09"), Decimal("0.18")),
            tax_context=TaxContext(customer_country="IN", customer_state="MH", seller_state="MH"),
            usage_quantity=0,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            invoice_count_so_far=0,
        )
        kinds = [li.kind for li in inv.line_items]
        assert LineItemKind.BASE in kinds
        assert LineItemKind.DISCOUNT in kinds
        # Intra-state GST → two TAX components
        assert kinds.count(LineItemKind.TAX) == 2

    def test_usage_based_plan(self):
        # 500 calls * ₹0.50 = ₹250
        inv = build_invoice(
            subscription=_sub(), plan=_plan(),
            strategy=UsageBased(Money("0.50", "INR")),
            discount=None,
            tax_calc=NoTax(),
            tax_context=TaxContext("AE"),
            usage_quantity=500,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            invoice_count_so_far=0,
        )
        assert inv.subtotal == Money("250.00", "INR")
        assert inv.total == Money("250.00", "INR")

    def test_no_discount_means_no_discount_line_item(self):
        inv = build_invoice(
            subscription=_sub(), plan=_plan(),
            strategy=FlatRate(Money("1000", "INR")),
            discount=None,
            tax_calc=NoTax(),
            tax_context=TaxContext("AE"),
            usage_quantity=0,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            invoice_count_so_far=0,
        )
        assert all(li.kind != LineItemKind.DISCOUNT for li in inv.line_items)

    def test_no_tax_means_no_tax_line_items(self):
        inv = build_invoice(
            subscription=_sub(), plan=_plan(),
            strategy=FlatRate(Money("1000", "INR")),
            discount=None,
            tax_calc=NoTax(),
            tax_context=TaxContext("AE"),
            usage_quantity=0,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            invoice_count_so_far=0,
        )
        assert all(li.kind != LineItemKind.TAX for li in inv.line_items)

    def test_vat_produces_single_tax_line_item(self):
        # ₹1000 + 19% VAT = ₹1190
        inv = build_invoice(
            subscription=_sub(), plan=_plan(),
            strategy=FlatRate(Money("1000", "EUR")),
            discount=None,
            tax_calc=VATCalculator(Decimal("0.19")),
            tax_context=TaxContext("DE"),
            usage_quantity=0,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            invoice_count_so_far=0,
        )
        assert inv.tax_total == Money("190.00", "EUR")
        assert inv.total == Money("1190.00", "EUR")
        kinds = [li.kind for li in inv.line_items]
        assert kinds.count(LineItemKind.TAX) == 1

    def test_fixed_amount_discount(self):
        # ₹1000 - ₹200 fixed = ₹800 taxable, no tax → total ₹800
        inv = build_invoice(
            subscription=_sub(), plan=_plan(),
            strategy=FlatRate(Money("1000", "INR")),
            discount=FixedAmountDiscount(Money("200", "INR")),
            tax_calc=NoTax(),
            tax_context=TaxContext("AE"),
            usage_quantity=0,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            invoice_count_so_far=0,
        )
        assert inv.discount_total == Money("200.00", "INR")
        assert inv.total == Money("800.00", "INR")
