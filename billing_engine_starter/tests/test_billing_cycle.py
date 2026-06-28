"""Tests for BillingCycle.run — fully implemented.

These tests use the `repos` fixture and helpers from conftest.py.
Tests are deterministic (no datetime.now), one ACTIVE customer per test (mostly).
"""

from datetime import date

import pytest

from billing_engine.billing.cycle import BillingCycle
from billing_engine.discounts import PercentageDiscount
from billing_engine.models import (
    Customer, Plan, PricingType, BillingPeriod,
    Subscription, SubscriptionStatus,
    InvoiceStatus, LedgerDirection,
)
from billing_engine.money import Money
from decimal import Decimal

from tests.conftest import (
    make_flat_strategy_factory, make_discount_factory, make_no_tax_factory,
)


# ----------------------------------------------------------------
# helpers
# ----------------------------------------------------------------
def _seed_active(repos, plan_name: str = "Pro") -> tuple[int, int, int]:
    """Insert one customer + one flat plan + one active subscription. Returns ids."""
    cust = repos.customers.add(Customer(None, "Alice", f"a@{plan_name}.com", "AE"))
    plan = repos.plans.add(Plan(None, plan_name, PricingType.FLAT, BillingPeriod.MONTHLY, "INR"))
    sub = repos.subscriptions.add(Subscription(
        None, cust.id, plan.id, SubscriptionStatus.ACTIVE,
        date(2026, 1, 1), date(2026, 2, 1),
    ))
    return cust.id, plan.id, sub.id


def _build_cycle(repos, *, amounts=None, discounts=None) -> BillingCycle:
    amounts = amounts or {"Pro": Money("1000", "INR")}
    return BillingCycle(
        db=repos.db,
        customer_repo=repos.customers,
        plan_repo=repos.plans,
        subscription_repo=repos.subscriptions,
        usage_repo=repos.usage,
        invoice_repo=repos.invoices,
        line_item_repo=repos.line_items,
        ledger_repo=repos.ledger,
        strategy_factory=make_flat_strategy_factory(amounts),
        discount_factory=make_discount_factory(discounts or {}),
        tax_factory=make_no_tax_factory(),
    )


# ----------------------------------------------------------------
# tests
# ----------------------------------------------------------------
class TestBillingCycleRun:
    def test_no_subscriptions_creates_nothing(self, repos):
        result = _build_cycle(repos).run(as_of=date(2026, 2, 1))
        assert result.invoices_created == 0
        assert result.invoices_skipped_duplicate == 0

    def test_subscription_not_yet_due_is_skipped(self, repos):
        _seed_active(repos)
        # period_end = 2026-02-01; running on 2026-01-15 → not due
        result = _build_cycle(repos).run(as_of=date(2026, 1, 15))
        assert result.invoices_created == 0

    def test_due_subscription_is_invoiced(self, repos):
        _, _, sub_id = _seed_active(repos)
        result = _build_cycle(repos).run(as_of=date(2026, 2, 1))
        assert result.invoices_created == 1
        assert repos.invoices.count_for_subscription(sub_id) == 1

    def test_period_advances_after_billing(self, repos):
        _, _, sub_id = _seed_active(repos)
        _build_cycle(repos).run(as_of=date(2026, 2, 1))
        sub = repos.subscriptions.get(sub_id)
        assert sub.current_period_start == date(2026, 2, 1)
        assert sub.current_period_end == date(2026, 3, 1)

    def test_ledger_debit_posted(self, repos):
        cust_id, _, _ = _seed_active(repos)
        _build_cycle(repos).run(as_of=date(2026, 2, 1))
        entries = repos.ledger.list_for_customer(cust_id)
        assert len(entries) == 1
        assert entries[0].direction == LedgerDirection.DEBIT
        assert entries[0].amount == Money("1000.00", "INR")

    def test_invoice_marked_issued(self, repos):
        _, _, sub_id = _seed_active(repos)
        _build_cycle(repos).run(as_of=date(2026, 2, 1))
        # The invoice for this sub should be ISSUED
        # we don't have list_for_subscription, but count_for_subscription proves it exists
        # and we can query directly
        with repos.db.connect() as conn:
            row = conn.execute(
                "SELECT status FROM invoices WHERE subscription_id=?", (sub_id,)
            ).fetchone()
        assert row["status"] == InvoiceStatus.ISSUED.value

    def test_idempotent_second_run_skips_duplicate(self, repos):
        _, _, sub_id = _seed_active(repos)
        cycle = _build_cycle(repos)
        first = cycle.run(as_of=date(2026, 2, 1))
        assert first.invoices_created == 1

        # Manually rewind the subscription back so we retry the SAME period
        repos.subscriptions.update_period(sub_id, date(2026, 1, 1), date(2026, 2, 1))
        second = cycle.run(as_of=date(2026, 2, 1))
        assert second.invoices_created == 0
        assert second.invoices_skipped_duplicate == 1
        assert repos.invoices.count_for_subscription(sub_id) == 1  # still 1!

    def test_trial_activates_after_trial_end(self, repos):
        cust = repos.customers.add(Customer(None, "Alice", "a@x.com", "AE"))
        plan = repos.plans.add(Plan(None, "Pro", PricingType.FLAT, BillingPeriod.MONTHLY, "INR"))
        sub = repos.subscriptions.add(Subscription(
            None, cust.id, plan.id, SubscriptionStatus.TRIAL,
            date(2026, 1, 1), date(2026, 2, 1),
            trial_end=date(2026, 1, 14),
        ))
        result = _build_cycle(repos).run(as_of=date(2026, 1, 15))
        assert result.trials_activated == 1
        assert repos.subscriptions.get(sub.id).status == SubscriptionStatus.ACTIVE
