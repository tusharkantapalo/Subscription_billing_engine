"""Shared pytest fixtures + helpers."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pytest

from billing_engine.db.database import Database
from billing_engine.db.repository import (
    CustomerRepository, PlanRepository, PlanTierRepository, DiscountRepository,
    SubscriptionRepository, UsageRecordRepository,
    InvoiceRepository, InvoiceLineItemRepository, LedgerRepository,
    PaymentAttemptRepository,
)
from billing_engine.discounts import Discount
from billing_engine.money import Money
from billing_engine.pricing import FlatRate
from billing_engine.taxes import NoTax, TaxContext


@pytest.fixture
def db() -> Database:
    """A fresh, file-backed SQLite database with schema applied.

    File-backed (not :memory:) so the same DB can be opened across multiple
    short-lived connections in a single test (which BillingCycle does).
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(path)
    database.init_schema()
    yield database
    Path(path).unlink(missing_ok=True)


# ----------------------------------------------------------------
# Bundle of repositories (cuts boilerplate in integration-y tests)
# ----------------------------------------------------------------
@dataclass
class Repos:
    db: Database
    customers: CustomerRepository
    plans: PlanRepository
    tiers: PlanTierRepository
    discounts: DiscountRepository
    subscriptions: SubscriptionRepository
    usage: UsageRecordRepository
    invoices: InvoiceRepository
    line_items: InvoiceLineItemRepository
    ledger: LedgerRepository
    attempts: PaymentAttemptRepository


@pytest.fixture
def repos(db) -> Repos:
    return Repos(
        db=db,
        customers=CustomerRepository(db),
        plans=PlanRepository(db),
        tiers=PlanTierRepository(db),
        discounts=DiscountRepository(db),
        subscriptions=SubscriptionRepository(db),
        usage=UsageRecordRepository(db),
        invoices=InvoiceRepository(db),
        line_items=InvoiceLineItemRepository(db),
        ledger=LedgerRepository(db),
        attempts=PaymentAttemptRepository(db),
    )


# ----------------------------------------------------------------
# Factory helpers for BillingCycle tests
# ----------------------------------------------------------------
def make_flat_strategy_factory(amount_per_plan_name: dict[str, Money]) -> Callable:
    """strategy_factory: Plan → FlatRate(amount) keyed by plan.name."""
    def factory(plan):
        if plan.name not in amount_per_plan_name:
            raise KeyError(f"No flat amount for plan {plan.name!r}")
        return FlatRate(amount_per_plan_name[plan.name])
    return factory


def make_discount_factory(
    discount_objects: dict[int, Discount],
) -> Callable[[Optional[int]], Optional[Discount]]:
    """discount_factory: discount_id → Discount instance (or None)."""
    def factory(discount_id: Optional[int]) -> Optional[Discount]:
        if discount_id is None:
            return None
        return discount_objects.get(discount_id)
    return factory


def make_no_tax_factory() -> Callable:
    """tax_factory: Customer → (NoTax, TaxContext)."""
    def factory(customer):
        return (NoTax(), TaxContext(customer_country=customer.country_code))
    return factory
