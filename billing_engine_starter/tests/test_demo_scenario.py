"""End-to-end demo scenario — fully implemented.

This is the Day-3 evening capstone exercise. It exercises the WHOLE system:
    customer creation → subscription → billing cycle → payment → ledger balance.

It's marked @pytest.mark.skip by default — students enable it once their
implementation is complete, as a "final acceptance gate" for the project.

To enable: delete the `@pytest.mark.skip(...)` line below.
"""

from datetime import date, datetime

import pytest

from billing_engine.billing.cycle import BillingCycle
from billing_engine.billing.dunning import DunningProcess, DunningState
from billing_engine.models import (
    Customer, Plan, PricingType, BillingPeriod,
    Subscription, SubscriptionStatus,
    InvoiceStatus, LedgerDirection,
)
from billing_engine.money import Money
from billing_engine.payments.gateway import ScriptedGateway, PaymentResult

from tests.conftest import (
    make_flat_strategy_factory, make_discount_factory, make_no_tax_factory,
)


class TestEndToEndScenario:
    def test_full_lifecycle(self, repos):
        # 1. Seed a customer + plan + active subscription
        cust = repos.customers.add(Customer(None, "Alice", "alice@x.com", "AE"))
        plan = repos.plans.add(Plan(
            None, "Pro", PricingType.FLAT, BillingPeriod.MONTHLY, "INR",
        ))
        sub = repos.subscriptions.add(Subscription(
            None, cust.id, plan.id, SubscriptionStatus.ACTIVE,
            date(2026, 1, 1), date(2026, 2, 1),
        ))

        # 2. Run the billing cycle on 2026-02-01
        cycle = BillingCycle(
            db=repos.db,
            customer_repo=repos.customers,
            plan_repo=repos.plans,
            subscription_repo=repos.subscriptions,
            usage_repo=repos.usage,
            invoice_repo=repos.invoices,
            line_item_repo=repos.line_items,
            ledger_repo=repos.ledger,
            strategy_factory=make_flat_strategy_factory({"Pro": Money("1000", "INR")}),
            discount_factory=make_discount_factory({}),
            tax_factory=make_no_tax_factory(),
        )
        result = cycle.run(as_of=date(2026, 2, 1))
        assert result.invoices_created == 1

        # 3. Customer's subscription period has advanced
        sub_after = repos.subscriptions.get(sub.id)
        assert sub_after.current_period_start == date(2026, 2, 1)
        assert sub_after.current_period_end == date(2026, 3, 1)

        # 4. Ledger has a single DEBIT of ₹1000
        debits = repos.ledger.list_for_customer(cust.id)
        assert len(debits) == 1
        assert debits[0].direction == LedgerDirection.DEBIT
        assert debits[0].amount == Money("1000.00", "INR")

        # 5. Fetch the invoice and pay it via dunning (first try succeeds)
        with repos.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM invoices WHERE subscription_id=?", (sub.id,)
            ).fetchone()
        invoice = repos.invoices.get(row["id"])
        assert invoice.status == InvoiceStatus.ISSUED

        dunning = DunningProcess(
            gateway=ScriptedGateway([PaymentResult(True)]),
            invoice_repo=repos.invoices,
            ledger_repo=repos.ledger,
            subscription_repo=repos.subscriptions,
            attempt_repo=repos.attempts,
        )
        outcome = dunning.attempt(invoice, cust.id, datetime(2026, 2, 1, 10, 0))
        assert outcome.state == DunningState.SUCCEEDED

        # 6. Invoice is now PAID
        assert repos.invoices.get(invoice.id).status == InvoiceStatus.PAID

        # 7. Ledger now has DEBIT 1000 + CREDIT 1000 → net zero balance
        entries = repos.ledger.list_for_customer(cust.id)
        assert len(entries) == 2
        net = sum(
            (e.amount.amount if e.direction == LedgerDirection.DEBIT else -e.amount.amount)
            for e in entries
        )
        assert net == 0
