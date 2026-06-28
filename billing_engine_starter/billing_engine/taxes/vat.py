"""
VATCalculator — single-rate VAT (e.g. 19% in Germany).
"""

from decimal import Decimal

from billing_engine.money import Money
from billing_engine.taxes.base import TaxCalculator, TaxContext, TaxBreakdown


class VATCalculator(TaxCalculator):
    def __init__(self, rate: Decimal) -> None:

        if isinstance(rate, float):
            raise TypeError("Rate must be of type Decimal!")
        
        if rate < Decimal("0") or rate > Decimal("1"):
            raise ValueError("Rate must be between 0 and 1!")
        
        self.rate = rate

    def apply(self, taxable: Money, context: TaxContext) -> TaxBreakdown:

        vat = taxable * self.rate
        pct = self.rate * 100
        label = f"VAT {pct}%"

        return TaxBreakdown(components=[(label, vat)], total=vat)
