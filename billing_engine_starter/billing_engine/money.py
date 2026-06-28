"""
Money — the foundation type for every monetary value in this project.

✅ THIS FILE IS COMPLETE. Read it, understand it, use it everywhere.
   You will NOT modify this file.

Key ideas:
- Wraps `decimal.Decimal` so we never accidentally use `float`.
- Carries a currency code so we cannot add INR to USD by mistake.
- Rounds via ROUND_HALF_EVEN ("banker's rounding") to 2 decimal places
  ONLY when explicitly asked (e.g., for display or persistence).
- Multiplication is allowed by int / Decimal (e.g. price * quantity).
  Multiplication of Money by Money is NOT meaningful and is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, getcontext
from typing import Union

# Set generous precision; rounding happens at display/persistence boundaries.
getcontext().prec = 28

Numeric = Union[int, str, Decimal]


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

    def __init__(self, amount: Numeric, currency: str) -> None:
        if isinstance(amount, float):
            raise TypeError(
                "Money cannot be constructed from float. "
                "Use Decimal or str: Money(Decimal('1.50'), 'INR') or Money('1.50', 'INR')."
            )
        if not currency or not currency.isalpha() or len(currency) != 3:
            raise ValueError(f"Currency must be a 3-letter code, got {currency!r}")

        # frozen dataclass requires object.__setattr__
        object.__setattr__(self, "amount", Decimal(amount))
        object.__setattr__(self, "currency", currency.upper())

    # ---------- factories ----------
    @classmethod
    def zero(cls, currency: str) -> "Money":
        return cls(Decimal("0"), currency)

    # ---------- arithmetic ----------
    def _check_same_currency(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise TypeError(f"Expected Money, got {type(other).__name__}")
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot mix currencies: {self.currency} vs {other.currency}"
            )

    def __add__(self, other: "Money") -> "Money":
        self._check_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Numeric) -> "Money":
        if isinstance(factor, Money):
            raise TypeError("Cannot multiply Money by Money — multiply by a scalar.")
        if isinstance(factor, float):
            raise TypeError("Cannot multiply Money by float. Use Decimal or int.")
        return Money(self.amount * Decimal(factor), self.currency)

    __rmul__ = __mul__

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    # ---------- comparisons ----------
    def __lt__(self, other: "Money") -> bool:
        self._check_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._check_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._check_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._check_same_currency(other)
        return self.amount >= other.amount

    def is_zero(self) -> bool:
        return self.amount == 0

    def is_positive(self) -> bool:
        return self.amount > 0

    def is_negative(self) -> bool:
        return self.amount < 0

    # ---------- rounding (use only at display / persistence boundary) ----------
    def rounded(self) -> "Money":
        """Return a new Money rounded to 2 decimal places using banker's rounding."""
        q = self.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        return Money(q, self.currency)

    def to_storage(self) -> str:
        """Canonical string form for persisting to SQLite TEXT column."""
        return str(self.rounded().amount)

    # ---------- display ----------
    def __str__(self) -> str:
        return f"{self.currency} {self.rounded().amount}"

    def __repr__(self) -> str:
        return f"Money({self.amount!r}, {self.currency!r})"
