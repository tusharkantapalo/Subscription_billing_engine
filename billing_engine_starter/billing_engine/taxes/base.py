"""
Tax calculator abstract base class + factory.

✅ ABC + factory wiring is COMPLETE. Subclasses live in sibling files.

Contract:
    apply(taxable_amount, context) -> TaxBreakdown
        Returns the breakdown of taxes (so PDFs can show line items like
        "CGST 9% + SGST 9%"). The TOTAL is what gets added to the invoice.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from billing_engine.money import Money


@dataclass(frozen=True)
class TaxContext:
    """Information a tax calculator may need."""
    customer_country: str       # ISO country code, e.g. "IN", "DE"
    customer_state: str = ""    # e.g. Indian state code; "" if not applicable
    seller_state: str = ""      # for GST intra vs inter-state determination


@dataclass(frozen=True)
class TaxBreakdown:
    """Per-component breakdown of taxes plus the total."""
    components: list[tuple[str, Money]]   # [("CGST 9%", ₹90), ("SGST 9%", ₹90)]
    total: Money


class TaxCalculator(ABC):
    """Computes tax on a taxable amount, returning a breakdown."""

    @abstractmethod
    def apply(self, taxable: Money, context: TaxContext) -> TaxBreakdown:
        raise NotImplementedError

    # ----------------- factory -----------------
    @staticmethod
    def for_country(country_code: str) -> "TaxCalculator":
        """Pick the right tax calculator based on the customer's country."""
        # ✅ COMPLETE — students do not need to touch this.
        # NOTE: import here to avoid circular imports.
        from .no_tax import NoTax
        from .vat import VATCalculator
        from .gst import GSTCalculator
        from decimal import Decimal

        code = country_code.upper()
        if code == "IN":
            return GSTCalculator(cgst=Decimal("0.09"), sgst=Decimal("0.09"), igst=Decimal("0.18"))
        if code in {"DE", "FR", "ES", "IT", "NL"}:
            return VATCalculator(rate=Decimal("0.19"))
        return NoTax()
