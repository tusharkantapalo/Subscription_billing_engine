"""
GSTCalculator — Indian Goods & Services Tax.

The rule:
    - If customer_state == seller_state (or seller_state is "")  =>  intra-state
        -> charge CGST + SGST (split equally, e.g. 9% + 9% = 18%)
    - Else  =>  inter-state
        -> charge IGST (e.g. 18%)

Customers without a state code default to IGST (safe choice).
"""

from decimal import Decimal

from billing_engine.money import Money
from billing_engine.taxes.base import TaxCalculator, TaxContext, TaxBreakdown


class GSTCalculator(TaxCalculator):
    def __init__(self, cgst: Decimal, sgst: Decimal, igst: Decimal) -> None:

        for rate in (cgst, sgst, igst):
            if isinstance(rate, float):
                raise TypeError("Rates must be Decimal!")

            if rate < Decimal("0") or rate > Decimal("1"):
                raise ValueError("Rates must be between 0 and 1!")

        if cgst + sgst != igst:
            raise ValueError("CGST + SGST must equal IGST!")

        self.cgst = cgst
        self.sgst = sgst
        self.igst = igst

    def apply(self, taxable: Money, context: TaxContext) -> TaxBreakdown:
        intra = (bool(context.customer_state) and context.customer_state == context.seller_state)

        if intra:
            cgst_amt = taxable * self.cgst
            sgst_amt = taxable * self.sgst

            components = [(f"CGST {self.cgst * 100}%", cgst_amt), (f"SGST {self.sgst * 100}%", sgst_amt),]
            total = cgst_amt + sgst_amt

        else:
            igst_amt = taxable * self.igst

            components = [(f"IGST {self.igst * 100}%", igst_amt)]
            total = igst_amt

        breakdown = TaxBreakdown(components=components, total=total)
        return breakdown
