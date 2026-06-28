"""
BillingCycle — finds due subscriptions, generates invoices, posts ledger DEBITs,
advances the subscription period. Must be IDEMPOTENT (safe to run twice).
"""
from __future__ import annotations

import sqlite3
from datetime import date
from dataclasses import dataclass
from typing import Callable, Optional

from billing_engine.billing.pipeline import build_invoice
from billing_engine.billing.proration import compute_proration

from billing_engine.db import (
    Database,
    CustomerRepository,
    PlanRepository,
    SubscriptionRepository,
    UsageRecordRepository,
    InvoiceRepository,
    InvoiceLineItemRepository,
    LedgerRepository,
)

from billing_engine.models import (
    Subscription,
    SubscriptionStatus,
    InvoiceStatus,
    Invoice,
    InvoiceLineItem,
    LineItemKind,
    LedgerEntry,
    LedgerDirection,
)


@dataclass
class BillingResult:
    invoices_created: int
    invoices_skipped_duplicate: int
    trials_activated: int


class BillingCycle:
    """Day-3 deliverable. Day-4 stretch: add `upgrade_subscription(...)`."""

    def __init__(
        self,
        db: Database,
        customer_repo: CustomerRepository,
        plan_repo: PlanRepository,
        subscription_repo: SubscriptionRepository,
        usage_repo: UsageRecordRepository,
        invoice_repo: InvoiceRepository,
        line_item_repo: InvoiceLineItemRepository,
        ledger_repo: LedgerRepository,
        strategy_factory: Callable,    # given a Plan, returns a PricingStrategy
        discount_factory: Callable,    # given a discount_id or None, returns a Discount or None
        tax_factory: Callable,         # given a Customer, returns (TaxCalculator, TaxContext)
    ) -> None:
        self.db = db
        self.customer_repo = customer_repo
        self.plan_repo = plan_repo
        self.subscription_repo = subscription_repo
        self.usage_repo = usage_repo
        self.invoice_repo = invoice_repo
        self.line_item_repo = line_item_repo
        self.ledger_repo = ledger_repo
        self.strategy_factory = strategy_factory
        self.discount_factory = discount_factory
        self.tax_factory = tax_factory

    # --------------------------------------------------------
    def run(self, as_of: date) -> BillingResult:
        """Bill all subscriptions whose current period ends on or before `as_of`."""
        # TODO Day 3
        invoices_created = 0
        invoices_skipped = 0
        trials_activated = 0

        # ---------------- Phase 1: Promote trials ----------------
        for sub in self.subscription_repo.list_all():
            if (
                sub.status == SubscriptionStatus.TRIAL
                and sub.trial_end
                and sub.trial_end <= as_of
            ):
                self.subscription_repo.update_status(sub.id, SubscriptionStatus.ACTIVE)
                trials_activated += 1

        # ---------------- Phase 2: Bill due subscriptions ----------------
        due = self.subscription_repo.get_due_for_billing(as_of)

        for sub in due:
            plan = self.plan_repo.get(sub.plan_id)
            customer = self.customer_repo.get(sub.customer_id)

            strategy = self.strategy_factory(plan)
            discount = self.discount_factory(sub.discount_id)
            tax_calc, tax_context = self.tax_factory(customer)

            usage = self.usage_repo.sum_for_period(
                sub.id,
                "units",
                sub.current_period_start,
                sub.current_period_end,
            )

            invoice_count = self.invoice_repo.count_for_subscription(sub.id)

            draft = build_invoice(
                subscription=sub,
                plan=plan,
                strategy=strategy,
                discount=discount,
                tax_calc=tax_calc,
                tax_context=tax_context,
                usage_quantity=usage,
                period_start=sub.current_period_start,
                period_end=sub.current_period_end,
                invoice_count_so_far=invoice_count,
            )

            try:
                saved_invoice = self.invoice_repo.add(draft)

                self.invoice_repo.update_status(saved_invoice.id, InvoiceStatus.ISSUED)

                for line in draft.line_items:
                    self.line_item_repo.add(
                        InvoiceLineItem(
                            id=None,
                            invoice_id=saved_invoice.id,
                            description=line.description,
                            amount=line.amount,
                            kind=line.kind,
                        )
                    )

                self.ledger_repo.post_debit(
                    customer_id=sub.customer_id,
                    amount=draft.total,
                    description=(
                        f"Invoice {saved_invoice.id} "
                        f"for subscription {sub.id}"
                    ),
                    as_of=as_of,
                )

                self.subscription_repo.advance_period(sub.id)

                invoices_created += 1

            except sqlite3.IntegrityError:
                invoices_skipped += 1

        return BillingResult(
            invoices_created,
            invoices_skipped,
            trials_activated,
        )

    # --------------------------------------------------------
    def upgrade_subscription(self, subscription_id: int, new_plan_id: int, switch_date: date) -> None:
        """Mid-cycle upgrade — Day 4 stretch."""
        # TODO Day 4
        with self.db.transaction() as conn:
            # 1. Load subscription + plans + customer
            subscription = self.subscription_repo.get(subscription_id)
            old_plan = self.plan_repo.get(subscription.plan_id)
            new_plan = self.plan_repo.get(new_plan_id)
            customer = self.customer_repo.get(subscription.customer_id)

            # 2. Get pricing strategies
            old_strategy = self.strategy_factory(old_plan)
            new_strategy = self.strategy_factory(new_plan)

            # Assume base price retrieval from strategy/plan
            old_price = old_strategy.price_for(subscription)
            new_price = new_strategy.price_for(subscription)

            # 3. Tax setup
            tax_calc, tax_context = self.tax_factory(customer)

            # 4. Compute proration
            pr = compute_proration(
                old_plan_price=old_price,
                new_plan_price=new_price,
                period_start=subscription.current_period_start,
                period_end=subscription.current_period_end,
                switch_date=switch_date,
                tax_calc=tax_calc,
                tax_context=tax_context,
            )

            # 5. Create proration invoice
            invoice = self.invoice_repo.add(
                Invoice(
                    id=None,
                    subscription_id=subscription_id,
                    customer_id=subscription.customer_id,
                    status=InvoiceStatus.ISSUED,
                    total=(
                        pr.charge_amount
                        + pr.charge_tax
                        - pr.credit_amount
                        - pr.credit_tax
                    ),
                    created_at=switch_date,
                )
            )

            # 6. Credit line item
            self.line_item_repo.add(
                InvoiceLineItem(
                    id=None,
                    invoice_id=invoice.id,
                    description="Proration credit",
                    amount=pr.credit_amount,
                    kind=LineItemKind.PRORATION_CREDIT,
                )
            )

            # 7. Charge line item
            self.line_item_repo.add(
                InvoiceLineItem(
                    id=None,
                    invoice_id=invoice.id,
                    description="Proration charge",
                    amount=pr.charge_amount,
                    kind=LineItemKind.PRORATION_CHARGE,
                )
            )

            # 8. Ledger DEBIT (customer owes net amount)
            self.ledger_repo.add(
                LedgerEntry(
                    id=None,
                    invoice_id=invoice.id,
                    customer_id=subscription.customer_id,
                    amount=invoice.total,
                    direction=LedgerDirection.DEBIT,
                    reason=f"Proration for subscription upgrade {subscription_id}",
                )
            )

            # 9. Switch subscription plan
            self.subscription_repo.update_plan(subscription_id, new_plan_id)
