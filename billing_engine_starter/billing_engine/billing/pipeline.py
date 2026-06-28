"""
build_invoice — PURE function that turns inputs into an Invoice dataclass.

⚠️ NO database calls here. No `datetime.now()`. No PDF. Just math.

The order is FIXED:
1. base       = strategy.calculate(usage)
2. discount   = discount.apply(base) if discount else 0
3. taxable    = base - discount
4. tax        = tax_calc.apply(taxable)
5. total      = taxable + tax.total
"""

from datetime import date
from typing import Optional
from billing_engine.taxes.no_tax import NoTax

from billing_engine.money import Money
from billing_engine.models import (
    Invoice,
    InvoiceStatus,
    InvoiceLineItem,
    LineItemKind,
    Subscription,
    Plan,
)
from billing_engine.pricing.base import PricingStrategy
from billing_engine.discounts.base import Discount, DiscountContext
from billing_engine.taxes.base import TaxCalculator, TaxContext


def build_invoice(
    subscription: Subscription,
    plan: Plan,
    strategy: PricingStrategy,
    discount: Optional[Discount],
    tax_calc: TaxCalculator,
    tax_context: TaxContext,
    usage_quantity: int,
    period_start: date,
    period_end: date,
    invoice_count_so_far: int,
) -> Invoice:

    base: Money = strategy.calculate(usage_quantity)

    if discount:
        discount_amount: Money = discount.apply(
            base,
            DiscountContext(invoice_count_so_far=invoice_count_so_far),
        )
    else:
        discount_amount = Money("0", base.currency)

    taxable: Money = base - discount_amount

    tax = tax_calc.apply(taxable, tax_context)

    total: Money = taxable + tax.total

    line_items: list[InvoiceLineItem] = []

    line_items.append(
        InvoiceLineItem(
            None,
            None,
            "Base charge",
            base,
            LineItemKind.BASE,
        )
    )

    if discount:
        line_items.append(
            InvoiceLineItem(
                None,
                None,
                "Discount",
                -discount_amount,
                LineItemKind.DISCOUNT,
            )
        )

    tax = tax_calc.apply(taxable, tax_context)

    tax_total = getattr(tax, "total", Money("0", base.currency))

    is_no_tax = isinstance(tax_calc, NoTax)

    if not is_no_tax and tax_total.amount != "0":
        if hasattr(tax, "components") and tax.components:
            for name, amount in tax.components:
                line_items.append(
                    InvoiceLineItem(
                        None,
                        None,
                        name,
                        amount,
                        LineItemKind.TAX,
                    )
                )
        else:
            line_items.append(
                InvoiceLineItem(
                    None,
                    None,
                    "Tax",
                    tax_total,
                    LineItemKind.TAX,
                )
            )

    return Invoice(
        id=None,
        subscription_id=subscription.id,
        period_start=period_start,
        period_end=period_end,
        subtotal=base,
        discount_total=discount_amount,
        tax_total=tax.total,
        total=total,
        status=InvoiceStatus.DRAFT,
        line_items=line_items,
    )
