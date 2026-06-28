"""Tests for DunningProcess (retry FSM) — fully implemented.

Uses ScriptedGateway so failures are deterministic.
"""

from datetime import date, datetime, timedelta

import pytest

from billing_engine.billing.dunning import (
    DunningProcess, DunningState, RETRY_DELAYS_DAYS, MAX_ATTEMPTS,
)
from billing_engine.models import (
    Customer, Plan, PricingType, BillingPeriod,
    Subscription, SubscriptionStatus,
    Invoice, InvoiceStatus,
)
from billing_engine.money import Money
from billing_engine.payments.gateway import ScriptedGateway, PaymentResult


# ----------------------------------------------------------------
# helpers
# ----------------------------------------------------------------
def _seed_subscription(repos) -> tuple[int, int]:
    cust = repos.customers.add(Customer(None, "Alice", "a@x.com", "AE"))
    plan = repos.plans.add(Plan(None, "Pro", PricingType.FLAT, BillingPeriod.MONTHLY, "INR"))
    sub = repos.subscriptions.add(Subscription(
        None, cust.id, plan.id, SubscriptionStatus.ACTIVE,
        date(2026, 1, 1), date(2026, 2, 1),
    ))
    return cust.id, sub.id


def _seed_invoice(repos, sub_id: int) -> Invoice:
    return repos.invoices.add(Invoice(
        id=None, subscription_id=sub_id,
        period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
        subtotal=Money("1000", "INR"), discount_total=Money("0", "INR"),
        tax_total=Money("0", "INR"), total=Money("1000", "INR"),
        status=InvoiceStatus.ISSUED,
    ))


def _build_dunning(repos, gateway: ScriptedGateway) -> DunningProcess:
    return DunningProcess(
        gateway=gateway,
        invoice_repo=repos.invoices,
        ledger_repo=repos.ledger,
        subscription_repo=repos.subscriptions,
        attempt_repo=repos.attempts,
    )


NOW = datetime(2026, 2, 1, 10, 0, 0)


# ----------------------------------------------------------------
class TestDunningProcess:
    def test_first_attempt_success(self, repos):
        cust_id, sub_id = _seed_subscription(repos)
        invoice = _seed_invoice(repos, sub_id)

        gw = ScriptedGateway([PaymentResult(True)])
        outcome = _build_dunning(repos, gw).attempt(invoice, cust_id, NOW)

        assert outcome.state == DunningState.SUCCEEDED
        assert outcome.attempt_no == 1
        assert outcome.next_retry_at is None
        assert repos.invoices.get(invoice.id).status == InvoiceStatus.PAID

    def test_first_failure_schedules_1_day(self, repos):
        cust_id, sub_id = _seed_subscription(repos)
        invoice = _seed_invoice(repos, sub_id)

        gw = ScriptedGateway([PaymentResult(False, "INSUFFICIENT_FUNDS")])
        outcome = _build_dunning(repos, gw).attempt(invoice, cust_id, NOW)

        assert outcome.state == DunningState.RETRYING
        assert outcome.attempt_no == 1
        assert outcome.next_retry_at == NOW + timedelta(days=1)

    def test_second_failure_schedules_3_days(self, repos):
        cust_id, sub_id = _seed_subscription(repos)
        invoice = _seed_invoice(repos, sub_id)

        gw = ScriptedGateway([
            PaymentResult(False, "INSUFFICIENT_FUNDS"),
            PaymentResult(False, "CARD_DECLINED"),
        ])
        d = _build_dunning(repos, gw)
        d.attempt(invoice, cust_id, NOW)
        second_attempt_time = NOW + timedelta(days=1)
        outcome = d.attempt(invoice, cust_id, second_attempt_time)

        assert outcome.state == DunningState.RETRYING
        assert outcome.attempt_no == 2
        # 2nd failure occurred at NOW+1d, schedules 3 days later → NOW+4d
        assert outcome.next_retry_at == second_attempt_time + timedelta(days=3)

    def test_third_failure_marks_final_and_past_due(self, repos):
        cust_id, sub_id = _seed_subscription(repos)
        invoice = _seed_invoice(repos, sub_id)

        gw = ScriptedGateway([
            PaymentResult(False, "INSUFFICIENT_FUNDS"),
            PaymentResult(False, "CARD_DECLINED"),
            PaymentResult(False, "EXPIRED"),
        ])
        d = _build_dunning(repos, gw)
        d.attempt(invoice, cust_id, NOW)
        d.attempt(invoice, cust_id, NOW + timedelta(days=1))
        outcome = d.attempt(invoice, cust_id, NOW + timedelta(days=4))

        assert outcome.state == DunningState.FAILED_FINAL
        assert outcome.attempt_no == MAX_ATTEMPTS
        assert outcome.next_retry_at is None
        assert repos.subscriptions.get(sub_id).status == SubscriptionStatus.PAST_DUE
        assert repos.invoices.get(invoice.id).status == InvoiceStatus.FAILED

    def test_eventual_success_recovers(self, repos):
        cust_id, sub_id = _seed_subscription(repos)
        invoice = _seed_invoice(repos, sub_id)

        gw = ScriptedGateway([
            PaymentResult(False, "INSUFFICIENT_FUNDS"),
            PaymentResult(True),
        ])
        d = _build_dunning(repos, gw)
        d.attempt(invoice, cust_id, NOW)
        outcome = d.attempt(invoice, cust_id, NOW + timedelta(days=1))

        assert outcome.state == DunningState.SUCCEEDED
        assert outcome.attempt_no == 2
        assert repos.invoices.get(invoice.id).status == InvoiceStatus.PAID


class TestShouldCancel:
    def test_after_7_days_returns_true(self):
        assert DunningProcess.should_cancel(
            past_due_since=date(2026, 2, 1),
            today=date(2026, 2, 8),
        ) is True

    def test_within_grace_returns_false(self):
        assert DunningProcess.should_cancel(
            past_due_since=date(2026, 2, 1),
            today=date(2026, 2, 5),
        ) is False
