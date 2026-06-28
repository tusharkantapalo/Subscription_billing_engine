"""
Pricing strategy abstract base class.

✅ This ABC is COMPLETE. Subclasses go in sibling files.
"""

from abc import ABC, abstractmethod
from billing_engine.money import Money


class PricingStrategy(ABC):
    """Computes the base charge for a billing period given a usage quantity.

    Subclasses MUST implement `calculate`. The method takes a non-negative
    integer `quantity` (e.g., API calls, seats, GB transferred) and returns
    a `Money` value in the strategy's configured currency.

    For strategies that ignore usage (e.g., FlatRate), `quantity` is still
    accepted but may be unused.
    """

    @abstractmethod
    def calculate(self, quantity: int) -> Money:
        """Return the charge for the given usage quantity."""
        raise NotImplementedError
