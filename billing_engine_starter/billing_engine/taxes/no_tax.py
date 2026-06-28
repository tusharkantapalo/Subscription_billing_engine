"""
NoTax — for jurisdictions where you don't charge tax (or the customer is tax-exempt).
"""

from billing_engine.money import Money
from billing_engine.taxes.base import TaxCalculator, TaxContext, TaxBreakdown


class NoTax:
    def apply(self, taxable, context):
        return type("TaxResult", (), {
            "total": Money("0", taxable.currency),
            "components": []
        })()
