"""
TieredPricing — different price per unit depending on the tier the quantity falls into.

This is the "cumulative" / "stacked" tier model, NOT the "volume" model:
    Tiers: [(0, 1000, ₹2.00), (1000, 5000, ₹1.50), (5000, None, ₹1.00)]
    Quantity = 6000:
        First 1000 units  @ ₹2.00 = ₹2000
        Next  4000 units  @ ₹1.50 = ₹6000
        Last  1000 units  @ ₹1.00 = ₹1000
        ------------------------------------
        Total                     = ₹9000

A tier with `to_units = None` is the open-ended top tier.

Tier boundaries are HALF-OPEN on the right: a tier (from, to, price)
covers units strictly less than `to` (i.e. [from, to)).
"""

from dataclasses import dataclass
from typing import Optional

from billing_engine.money import Money
from billing_engine.pricing.base import PricingStrategy


@dataclass(frozen=True)
class Tier:
    from_units: int
    to_units: Optional[int]   # None means "unlimited" / open-ended
    unit_price: Money


class TieredPricing(PricingStrategy):
    """Charges across multiple price tiers based on cumulative quantity."""

    def __init__(self, tiers: list[Tier]) -> None:

        if not tiers:
            raise ValueError("At least one tier is required!")
        
        for i in range(len(tiers) - 1):
            curr_tier = tiers[i]
            next_tier = tiers[i + 1]

            if curr_tier.to_units != next_tier.from_units:
                raise ValueError("Tiers are not contiguous")
            
        for i in range(len(tiers) - 1):
            if tiers[i].to_units is None:
                raise ValueError("Any beginning tier may have to_units is None")
            
        for tier in tiers:
            if tier.unit_price.currency != tiers[0].unit_price.currency:
                raise ValueError("All tiers must have the same currency")
        
        if tiers[-1].to_units is not None:
            raise ValueError("Top tier must be open-ended")
        
        self.tiers = tiers

    def calculate(self, quantity: int) -> Money:

        if quantity < 0:
            raise ValueError("Quantity cannot be negative!")
        
        currency = self.tiers[0].unit_price.currency
        total = Money.zero(currency)

        for tier in self.tiers:
            if tier.to_units is None or quantity < tier.to_units:
                units_in_tier = quantity - tier.from_units
            else:
                units_in_tier = tier.to_units - tier.from_units
            
            if units_in_tier > 0:
                total += tier.unit_price * units_in_tier
            
            if tier.to_units is not None and quantity < tier.to_units:
                break

        return total
