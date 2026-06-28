"""Tests for repositories — fully implemented. Uses `db` fixture from conftest.py."""

from datetime import date

import pytest
import sqlite3

from billing_engine.money import Money
from billing_engine.db.repository import (
    CustomerRepository, PlanRepository, PlanTierRepository, DiscountRepository,
    SubscriptionRepository, UsageRecordRepository,
    InvoiceRepository, InvoiceLineItemRepository, LedgerRepository,
)
from billing_engine.models import (
    Customer,
    Plan, PricingType, BillingPeriod,
    Subscription, SubscriptionStatus,
    Invoice, InvoiceStatus, InvoiceLineItem, LineItemKind,
    LedgerEntry, LedgerDirection,
)


# ============================================================
# CustomerRepository
# ============================================================
class TestCustomerRepository:
    def test_add_assigns_id(self, db):
        repo = CustomerRepository(db)
        c = repo.add(Customer(id=None, name="Alice", email="a@x.com", country_code="IN"))
        assert c.id is not None
        assert c.name == "Alice"

    def test_get_returns_inserted(self, db):
        repo = CustomerRepository(db)
        added = repo.add(Customer(None, "Alice", "a@x.com", "IN"))
        got = repo.get(added.id)
        assert got is not None
        assert got.email == "a@x.com"

    def test_get_missing_returns_none(self, db):
        assert CustomerRepository(db).get(9999) is None

    def test_find_by_email(self, db):
        repo = CustomerRepository(db)
        repo.add(Customer(None, "Alice", "a@x.com", "IN"))
        assert repo.find_by_email("a@x.com").name == "Alice"

    def test_find_by_email_missing_returns_none(self, db):
        assert CustomerRepository(db).find_by_email("nope@x.com") is None

    def test_duplicate_email_rejected(self, db):
        repo = CustomerRepository(db)
        repo.add(Customer(None, "Alice", "a@x.com", "IN"))
        with pytest.raises(sqlite3.IntegrityError):
            repo.add(Customer(None, "Bob", "a@x.com", "DE"))

    def test_list_all(self, db):
        repo = CustomerRepository(db)
        repo.add(Customer(None, "Alice", "a@x.com", "IN"))
        repo.add(Customer(None, "Bob", "b@x.com", "DE"))
        assert len(repo.list_all()) == 2


# ============================================================
# PlanRepository + PlanTierRepository
# ============================================================
class TestPlanRepository:
    def test_add_and_get(self, db):
        repo = PlanRepository(db)
        p = repo.add(Plan(
            id=None, name="Pro", pricing_type=PricingType.FLAT,
            billing_period=BillingPeriod.MONTHLY, currency="INR",
        ))
        assert p.id is not None
        assert repo.get(p.id).name == "Pro"

    def test_list_all(self, db):
        repo = PlanRepository(db)
        repo.add(Plan(None, "Pro", PricingType.FLAT, BillingPeriod.MONTHLY, "INR"))
        repo.add(Plan(None, "Ent", PricingType.FLAT, BillingPeriod.MONTHLY, "INR"))
        assert len(repo.list_all()) == 2


class TestPlanTierRepository:
    def test_add_and_list(self, db):
        plan = PlanRepository(db).add(Plan(
            None, "Metered", PricingType.TIERED, BillingPeriod.MONTHLY, "INR",
        ))
        tier_repo = PlanTierRepository(db)
        tier_repo.add(plan.id, 0, 1000, Money("2.00", "INR"))
        tier_repo.add(plan.id, 1000, None, Money("1.00", "INR"))

        tiers = tier_repo.list_for_plan(plan.id, "INR")
        assert len(tiers) == 2
        assert tiers[0] == (0, 1000, Money("2.00", "INR"))
        assert tiers[1] == (1000, None, Money("1.00", "INR"))


# ============================================================
# DiscountRepository
# ============================================================
class TestDiscountRepository:
    def test_add_and_get(self, db):
        repo = DiscountRepository(db)
        did = repo.add("HALF", "PERCENT", "0.50")
        row = repo.get_by_code("HALF")
        assert row is not None
        assert row["id"] == did
        assert row["value"] == "0.50"

    def test_missing_returns_none(self, db):
        assert DiscountRepository(db).get_by_code("nope") is None


# ============================================================
# SubscriptionRepository
# ============================================================
class TestSubscriptionRepository:
    def _setup(self, db) -> tuple[int, int]:
        c = CustomerRepository(db).add(Customer(None, "A", "a@x.com", "IN"))
        p = PlanRepository(db).add(
            Plan(None, "P", PricingType.FLAT, BillingPeriod.MONTHLY, "INR")
        )
        return c.id, p.id

    def test_add_and_get(self, db):
        cid, pid = self._setup(db)
        repo = SubscriptionRepository(db)
        s = repo.add(Subscription(
            None, cid, pid, SubscriptionStatus.ACTIVE,
            date(2026, 1, 1), date(2026, 2, 1),
        ))
        assert s.id is not None
        got = repo.get(s.id)
        assert got.status == SubscriptionStatus.ACTIVE
        assert got.current_period_start == date(2026, 1, 1)

    def test_get_due_for_billing(self, db):
        cid, pid = self._setup(db)
        repo = SubscriptionRepository(db)
        repo.add(Subscription(
            None, cid, pid, SubscriptionStatus.ACTIVE,
            date(2026, 1, 1), date(2026, 2, 1),
        ))
        repo.add(Subscription(
            None, cid, pid, SubscriptionStatus.ACTIVE,
            date(2026, 2, 1), date(2026, 3, 1),    # not yet due on Feb 1 — period_end>2026-02-01? 
        ))
        # On 2026-02-01: first sub's period_end <= 2026-02-01 → due
        due = repo.get_due_for_billing(date(2026, 2, 1))
        assert len(due) == 1
        assert due[0].current_period_start == date(2026, 1, 1)

    def test_trial_subs_excluded_from_due(self, db):
        cid, pid = self._setup(db)
        repo = SubscriptionRepository(db)
        repo.add(Subscription(
            None, cid, pid, SubscriptionStatus.TRIAL,
            date(2026, 1, 1), date(2026, 2, 1),
            trial_end=date(2026, 1, 15),
        ))
        assert repo.get_due_for_billing(date(2026, 2, 1)) == []

    def test_update_period(self, db):
        cid, pid = self._setup(db)
        repo = SubscriptionRepository(db)
        s = repo.add(Subscription(
            None, cid, pid, SubscriptionStatus.ACTIVE,
            date(2026, 1, 1), date(2026, 2, 1),
        ))
        repo.update_period(s.id, date(2026, 2, 1), date(2026, 3, 1))
        got = repo.get(s.id)
        assert got.current_period_start == date(2026, 2, 1)
        assert got.current_period_end == date(2026, 3, 1)

    def test_update_status(self, db):
        cid, pid = self._setup(db)
        repo = SubscriptionRepository(db)
        s = repo.add(Subscription(
            None, cid, pid, SubscriptionStatus.TRIAL,
            date(2026, 1, 1), date(2026, 2, 1),
            trial_end=date(2026, 1, 15),
        ))
        repo.update_status(s.id, SubscriptionStatus.ACTIVE)
        assert repo.get(s.id).status == SubscriptionStatus.ACTIVE

    def test_list_all(self, db):
        cid, pid = self._setup(db)
        repo = SubscriptionRepository(db)
        repo.add(Subscription(None, cid, pid, SubscriptionStatus.TRIAL,
                              date(2026, 1, 1), date(2026, 2, 1),
                              trial_end=date(2026, 1, 15)))
        repo.add(Subscription(None, cid, pid, SubscriptionStatus.ACTIVE,
                              date(2026, 1, 1), date(2026, 2, 1)))
        assert len(repo.list_all()) == 2


# ============================================================
# UsageRecordRepository
# ============================================================
class TestUsageRecordRepository:
    def _setup(self, db) -> int:
        c = CustomerRepository(db).add(Customer(None, "A", "a@x.com", "IN"))
        p = PlanRepository(db).add(
            Plan(None, "P", PricingType.USAGE, BillingPeriod.MONTHLY, "INR")
        )
        s = SubscriptionRepository(db).add(Subscription(
            None, c.id, p.id, SubscriptionStatus.ACTIVE,
            date(2026, 1, 1), date(2026, 2, 1),
        ))
        return s.id

    def test_sum_for_period(self, db):
        sid = self._setup(db)
        repo = UsageRecordRepository(db)
        repo.add(sid, "calls", 100)
        repo.add(sid, "calls", 250)
        repo.add(sid, "calls", 50)
        assert repo.sum_for_period(sid, "calls", date(2026, 1, 1), date(2026, 2, 1)) == 400

    def test_sum_empty_returns_zero(self, db):
        sid = self._setup(db)
        repo = UsageRecordRepository(db)
        assert repo.sum_for_period(sid, "calls", date(2026, 1, 1), date(2026, 2, 1)) == 0


# ============================================================
# InvoiceRepository (idempotency!) + LineItemRepository
# ============================================================
class TestInvoiceRepository:
    def _setup(self, db) -> int:
        c = CustomerRepository(db).add(Customer(None, "A", "a@x.com", "IN"))
        p = PlanRepository(db).add(
            Plan(None, "P", PricingType.FLAT, BillingPeriod.MONTHLY, "INR")
        )
        s = SubscriptionRepository(db).add(Subscription(
            None, c.id, p.id, SubscriptionStatus.ACTIVE,
            date(2026, 1, 1), date(2026, 2, 1),
        ))
        return s.id

    def _make_invoice(self, subscription_id: int) -> Invoice:
        return Invoice(
            id=None, subscription_id=subscription_id,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            subtotal=Money("100", "INR"), discount_total=Money("0", "INR"),
            tax_total=Money("18", "INR"), total=Money("118", "INR"),
            status=InvoiceStatus.ISSUED,
        )

    def test_add_assigns_id(self, db):
        sid = self._setup(db)
        repo = InvoiceRepository(db)
        saved = repo.add(self._make_invoice(sid))
        assert saved.id is not None

    def test_duplicate_period_rejected(self, db):
        sid = self._setup(db)
        repo = InvoiceRepository(db)
        repo.add(self._make_invoice(sid))
        with pytest.raises(sqlite3.IntegrityError):
            repo.add(self._make_invoice(sid))

    def test_count_for_subscription(self, db):
        sid = self._setup(db)
        repo = InvoiceRepository(db)
        assert repo.count_for_subscription(sid) == 0
        repo.add(self._make_invoice(sid))
        assert repo.count_for_subscription(sid) == 1

    def test_mark_paid(self, db):
        sid = self._setup(db)
        repo = InvoiceRepository(db)
        saved = repo.add(self._make_invoice(sid))
        repo.mark_paid(saved.id)
        assert repo.get(saved.id).status == InvoiceStatus.PAID

    def test_get_preserves_money_values(self, db):
        sid = self._setup(db)
        repo = InvoiceRepository(db)
        saved = repo.add(self._make_invoice(sid))
        got = repo.get(saved.id)
        assert got.total == Money("118.00", "INR")


class TestInvoiceLineItemRepository:
    def test_add_and_list(self, db):
        # Need an invoice first
        c = CustomerRepository(db).add(Customer(None, "A", "a@x.com", "IN"))
        p = PlanRepository(db).add(Plan(None, "P", PricingType.FLAT, BillingPeriod.MONTHLY, "INR"))
        s = SubscriptionRepository(db).add(Subscription(
            None, c.id, p.id, SubscriptionStatus.ACTIVE,
            date(2026, 1, 1), date(2026, 2, 1),
        ))
        inv = InvoiceRepository(db).add(Invoice(
            id=None, subscription_id=s.id,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            subtotal=Money("100", "INR"), discount_total=Money("0", "INR"),
            tax_total=Money("18", "INR"), total=Money("118", "INR"),
            status=InvoiceStatus.ISSUED,
        ))

        li_repo = InvoiceLineItemRepository(db)
        li_repo.add(InvoiceLineItem(None, inv.id, "Base", Money("100", "INR"), LineItemKind.BASE))
        li_repo.add(InvoiceLineItem(None, inv.id, "Tax", Money("18", "INR"), LineItemKind.TAX))

        items = li_repo.list_for_invoice(inv.id)
        assert len(items) == 2
        assert items[0].kind == LineItemKind.BASE


# ============================================================
# LedgerRepository — APPEND-ONLY
# ============================================================
class TestLedgerRepositoryAppendOnly:
    def test_update_raises(self, db):
        with pytest.raises(NotImplementedError, match="append-only"):
            LedgerRepository(db).update(entry_id=1, amount=Money("1", "INR"))

    def test_delete_raises(self, db):
        with pytest.raises(NotImplementedError, match="append-only"):
            LedgerRepository(db).delete(1)

    def test_add_assigns_id(self, db):
        c = CustomerRepository(db).add(Customer(None, "A", "a@x.com", "IN"))
        repo = LedgerRepository(db)
        entry = repo.add(LedgerEntry(
            id=None, invoice_id=None, customer_id=c.id,
            amount=Money("100", "INR"), direction=LedgerDirection.DEBIT,
            reason="Test",
        ))
        assert entry.id is not None

    def test_list_for_customer_returns_entries(self, db):
        c = CustomerRepository(db).add(Customer(None, "A", "a@x.com", "IN"))
        repo = LedgerRepository(db)
        repo.add(LedgerEntry(None, None, c.id, Money("100", "INR"),
                             LedgerDirection.DEBIT, "Invoice"))
        repo.add(LedgerEntry(None, None, c.id, Money("100", "INR"),
                             LedgerDirection.CREDIT, "Payment"))
        entries = repo.list_for_customer(c.id)
        assert len(entries) == 2
