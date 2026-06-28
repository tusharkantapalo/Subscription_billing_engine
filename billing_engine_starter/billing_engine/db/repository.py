"""
Repositories — the ONLY place SQL lives.

Each repository wraps the Database connection and exposes methods that
take/return domain dataclasses (defined in billing_engine/models/).

⚠️ YOU IMPLEMENT every method body marked TODO.
   The signatures, docstrings, and the LedgerRepository's append-only
   guarantee are already in place — do not change them.

Beginner map (Day 2):
  1) CustomerRepository: add, get, find_by_email, list_all
  2) PlanRepository: add, get, list_all
  3) PlanTierRepository: add, list_for_plan
  4) DiscountRepository: add, get_by_code
  5) SubscriptionRepository: add, get, list_all, get_due_for_billing
  6) UsageRecordRepository: add, sum_for_period
  7) InvoiceRepository: add, get
  8) InvoiceLineItemRepository: add, list_for_invoice

Skip on Day 2 (read-only for now):
  - SubscriptionRepository.update_period / update_status / update_plan
  - InvoiceRepository.count_for_subscription / mark_paid / mark_failed / set_pdf_path
  - LedgerRepository and PaymentAttemptRepository

Conventions:
  - Always use parameterized queries (`?` placeholders) — NEVER f-string SQL.
  - Money values are persisted as TEXT using `money.to_storage()`.
  - Dates are persisted as ISO strings (`date.isoformat()`).

New layering (beginner-friendly):
  - Raw SQL lives in `billing_engine/db/queries.py`.
  - Repository methods call those query helpers.
  - Your Day 2 focus is:
      1) Convert domain -> storage values before helper call
      2) Convert rows -> domain dataclasses after helper call
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from billing_engine.db.database import Database
from billing_engine.db import queries as q
from billing_engine.money import Money
from billing_engine.models import (
    Customer,
    Plan, PricingType, BillingPeriod,
    Subscription, SubscriptionStatus,
    Invoice, InvoiceStatus, InvoiceLineItem, LineItemKind,
    LedgerEntry, LedgerDirection,
)


# ============================================================
# CUSTOMERS
# ============================================================
# Day 2: start here.
class CustomerRepository:
    """Persistence boundary for customers.

    A Customer is the billing account owner: invoices, subscriptions, and
    ledger entries ultimately belong to a customer. This repository hides the
    `customers` table and returns Customer dataclasses so the rest of the app
    does not need to know SQL column names.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, customer: Customer) -> Customer:

        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO customers(name, email, country_code, state_code)
                VALUES (?, ?, ?, ?)
                """,
                (
                    customer.name,
                    customer.email,
                    customer.country_code,
                    customer.state_code,
                ),
            )

        return Customer(
            id=cur.lastrowid,
            name=customer.name,
            email=customer.email,
            country_code=customer.country_code,
            state_code=customer.state_code,
        )

    def get(self, customer_id: int) -> Optional[Customer]:

        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM customers WHERE id = ?",
                (customer_id,),
            ).fetchone()

        if row is None:
            return None

        return Customer(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            country_code=row["country_code"],
            state_code=row["state_code"],
        )

    def find_by_email(self, email: str) -> Optional[Customer]:
        
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM customers WHERE email = ?",
                (email,),
            ).fetchone()

        if row is None:
            return None

        return Customer(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            country_code=row["country_code"],
            state_code=row["state_code"],
        )

    def list_all(self) -> list[Customer]:
        
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM customers ORDER BY id"
            ).fetchall()

        return [
            Customer(
                id=row["id"],
                name=row["name"],
                email=row["email"],
                country_code=row["country_code"],
                state_code=row["state_code"],
            )
            for row in rows
        ]


# ============================================================
# PLANS  +  PLAN TIERS
# ============================================================
# Day 2
class PlanRepository:
    """Persistence boundary for subscription plans.

    A Plan describes what the customer bought: pricing type, billing period,
    currency, and strategy configuration. Pricing code consumes Plan objects,
    while this repository handles the `plans` table representation.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, plan: Plan) -> Plan:
        
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO plans(
                    name,
                    pricing_type,
                    billing_period,
                    currency,
                    config_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    plan.name,
                    plan.pricing_type.value,
                    plan.billing_period.value,
                    plan.currency,
                    plan.config_json,
                ),
            )

        return Plan(
            id=cur.lastrowid,
            name=plan.name,
            pricing_type=plan.pricing_type,
            billing_period=plan.billing_period,
            currency=plan.currency,
            config_json=plan.config_json,
        )

    def get(self, plan_id: int) -> Optional[Plan]:
        
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM plans WHERE id = ?",
                (plan_id,),
            ).fetchone()

        if row is None:
            return None

        return Plan(
            id=row["id"],
            name=row["name"],
            pricing_type=PricingType(row["pricing_type"]),
            billing_period=BillingPeriod(row["billing_period"]),
            currency=row["currency"],
            config_json=row["config_json"],
        )

    def list_all(self) -> list[Plan]:
        
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM plans ORDER BY id"
            ).fetchall()

        return [
            Plan(
                id=row["id"],
                name=row["name"],
                pricing_type=PricingType(row["pricing_type"]),
                billing_period=BillingPeriod(row["billing_period"]),
                currency=row["currency"],
                config_json=row["config_json"],
            )
            for row in rows
        ]


class PlanTierRepository:
    """Persistence boundary for pricing tiers attached to a plan.

    Tiered and usage-based plans need rows such as "0-100 units at 1.00" and
    "101+ units at 0.75". These rows live separately from plans because one
    plan can have many tiers.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, plan_id: int, from_units: int, to_units: Optional[int], unit_price: Money) -> int:
        """Insert a tier; return new id."""
        
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO plan_tiers(
                    plan_id,
                    from_units,
                    to_units,
                    unit_price
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    plan_id,
                    from_units,
                    to_units,
                    unit_price.to_storage(),
                ),
            )

        return cur.lastrowid

    def list_for_plan(self, plan_id: int, currency: str) -> list[tuple[int, Optional[int], Money]]:
        """Return [(from_units, to_units, unit_price)] ordered by from_units.

        Currency is passed in (the plan_tiers table stores only the amount;
        currency lives on the parent plan).
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM plan_tiers
                WHERE plan_id = ?
                ORDER BY from_units
                """,
                (plan_id,),
            ).fetchall()

        return [
            (
                row["from_units"],
                row["to_units"],
                Money(row["unit_price"], currency),
            )
            for row in rows
        ]


# ============================================================
# DISCOUNTS
# ============================================================
# Day 2
class DiscountRepository:
    """Persistence boundary for discount definitions.

    Discounts are stored as flexible rows because different discount types need
    different interpretation: percentage, fixed amount, or first-month-free.
    This repository intentionally returns dictionaries instead of a dataclass.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, code: str, discount_type: str, value: str, currency: Optional[str] = None) -> int:
        
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO discounts(
                    code,
                    discount_type,
                    value,
                    currency
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    code,
                    discount_type,
                    value,
                    currency,
                ),
            )

        return cur.lastrowid

    def get_by_code(self, code: str) -> Optional[dict]:
        """Return raw row as dict, or None. (Discount has no dataclass yet — we use a dict for now.)"""
        
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM discounts
                WHERE code = ?
                """,
                (code,),
            ).fetchone()

        if row is None:
            return None

        return dict(row)


# ============================================================
# SUBSCRIPTIONS
# ============================================================
# Day 2 (only add/get/list_all/get_due_for_billing)
class SubscriptionRepository:
    """Persistence boundary for customer subscriptions.

    A Subscription connects a customer to a plan and tracks lifecycle state:
    TRIAL, ACTIVE, PAST_DUE, or CANCELLED. It also stores the current billing
    period, trial end date, optional discount, and dunning state.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def _row_to_subscription(self, row) -> Subscription:
        return Subscription(
            id=row["id"],
            customer_id=row["customer_id"],
            plan_id=row["plan_id"],
            status=SubscriptionStatus(row["status"]),
            current_period_start=date.fromisoformat(row["current_period_start"]),
            current_period_end=date.fromisoformat(row["current_period_end"]),
            trial_end=(date.fromisoformat(row["trial_end"]) 
                       if row["trial_end"] else None),
            discount_id=row["discount_id"],
            past_due_since=(
                date.fromisoformat(row["past_due_since"])
                if row["past_due_since"] else None
            ),
        )

    def add(self, subscription: Subscription) -> Subscription:
        
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO subscriptions(
                    customer_id,
                    plan_id,
                    status,
                    current_period_start,
                    current_period_end,
                    trial_end,
                    discount_id,
                    past_due_since
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    subscription.customer_id,
                    subscription.plan_id,
                    subscription.status.value,
                    subscription.current_period_start.isoformat(),
                    subscription.current_period_end.isoformat(),
                    subscription.trial_end.isoformat()
                    if subscription.trial_end else None,
                    subscription.discount_id,
                    subscription.past_due_since.isoformat()
                    if subscription.past_due_since else None,
                ),
            )

        return Subscription(
            id=cur.lastrowid,
            customer_id=subscription.customer_id,
            plan_id=subscription.plan_id,
            status=subscription.status,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            trial_end=subscription.trial_end,
            discount_id=subscription.discount_id,
            past_due_since=subscription.past_due_since,
        )

    def get(self, subscription_id: int) -> Optional[Subscription]:

        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE id = ?",
                (subscription_id,),
            ).fetchone()

        if row is None:
            return None

        return self._row_to_subscription(row)

    def list_all(self) -> list[Subscription]:
        """All subscriptions, regardless of status. Used by BillingCycle trial scan."""
        
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM subscriptions ORDER BY id"
            ).fetchall()

        return [self._row_to_subscription(row) for row in rows]

    def get_due_for_billing(self, as_of: date) -> list[Subscription]:
        """Subscriptions whose current_period_end <= as_of AND status is ACTIVE.
        (Hint: trial subscriptions whose trial_end <= as_of should also become billable —
         either handle that here or transition them to ACTIVE first in BillingCycle.)
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM subscriptions
                WHERE status = ?
                AND current_period_end <= ?
                ORDER BY id
                """,
                (
                    SubscriptionStatus.ACTIVE.value,
                    as_of.isoformat(),
                ),
            ).fetchall()

        return [self._row_to_subscription(row) for row in rows]

    # ------------------------------------------------------------------
    # Day 2 boundary:
    # Everything below this line in this class is intentionally deferred.
    # Keep the method stubs so Day 3/4 can build on the same API surface.
    # ------------------------------------------------------------------
    def update_period(self, subscription_id: int, new_start: date, new_end: date) -> None:
        
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE subscriptions
                SET current_period_start = ?,
                    current_period_end = ?
                WHERE id = ?
                """,
                (
                    new_start.isoformat(),
                    new_end.isoformat(),
                    subscription_id,
                ),
            )

    def update_status(
        self,
        subscription_id: int,
        new_status: SubscriptionStatus,
        past_due_since: Optional[date] = None,
    ) -> None:
        
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE subscriptions
                SET status = ?,
                    past_due_since = ?
                WHERE id = ?
                """,
                (
                    new_status.value,
                    past_due_since.isoformat()
                    if past_due_since else None,
                    subscription_id,
                ),
            )

    def advance_period(self, subscription_id: int) -> None:
        """
        Move the billing window forward by one month.

        Example:
        2026-01-01 → 2026-02-01
        becomes
        2026-02-01 → 2026-03-01
        """
        sub = self.get(subscription_id)

        if sub is None:
            return

        old_end = sub.current_period_end

        year = old_end.year
        month = old_end.month + 1

        if month > 12:
            month = 1
            year += 1

        new_end = date(
            year,
            month,
            old_end.day,
        )

        self.update_period(
            subscription_id,
            old_end,
            new_end,
        )

    def update_plan(self, subscription_id: int, new_plan_id: int) -> None:
        # TODO Day 4.
        # Hint: q.update_subscription_plan(...)
        raise NotImplementedError("Day 4: implement SubscriptionRepository.update_plan")


# ============================================================
# USAGE
# ============================================================
# Day 2
class UsageRecordRepository:
    """Persistence boundary for metered usage.

    Usage records store quantities such as API calls, seats, messages, or GBs.
    Usage-based pricing strategies ask this repository for the total quantity
    they should charge for a subscription.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, subscription_id: int, metric: str, quantity: int) -> int:
        
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO usage_records(
                    subscription_id,
                    metric,
                    quantity
                )
                VALUES (?, ?, ?)
                """,
                (
                    subscription_id,
                    metric,
                    quantity,
                ),
            )

        return cur.lastrowid

    def sum_for_period(
        self, subscription_id: int, metric: str, period_start: date, period_end: date
    ) -> int:
        
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(quantity), 0) AS total
                FROM usage_records
                WHERE subscription_id = ?
                  AND metric = ?
                """,
                (
                    subscription_id,
                    metric,
                ),
            ).fetchone()

        return row["total"]


# ============================================================
# INVOICES + LINE ITEMS
# ============================================================
# Day 2 (InvoiceRepository only add/get)
class InvoiceRepository:
    """Persistence boundary for invoice headers.

    An Invoice stores the totals for one subscription period: subtotal,
    discounts, tax, final total, status, issue time, and optional PDF path.
    Line items are stored separately by InvoiceLineItemRepository.
    """

    def update_status(self, invoice_id: int, status: InvoiceStatus) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE invoices SET status=? WHERE id=?",
                (status.value, invoice_id),
            )

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, invoice: Invoice) -> Invoice:
        """Insert invoice (NOT line items — that's the other repo).

        Must respect the UNIQUE(subscription_id, period_start) constraint.
        If a duplicate is attempted, raise sqlite3.IntegrityError naturally
        (caller is responsible for handling it — this gives idempotency).
        """
        
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO invoices(
                    subscription_id,
                    period_start,
                    period_end,
                    currency,
                    subtotal,
                    discount_total,
                    tax_total,
                    total,
                    status,
                    issued_at,
                    pdf_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice.subscription_id,
                    invoice.period_start.isoformat(),
                    invoice.period_end.isoformat(),
                    invoice.total.currency,
                    invoice.subtotal.to_storage(),
                    invoice.discount_total.to_storage(),
                    invoice.tax_total.to_storage(),
                    invoice.total.to_storage(),
                    invoice.status.value,
                    invoice.issued_at.isoformat()
                    if invoice.issued_at else None,
                    invoice.pdf_path,
                ),
            )

        invoice.id = cur.lastrowid
        return invoice

    def get(self, invoice_id: int) -> Optional[Invoice]:
        
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM invoices
                WHERE id = ?
                """,
                (invoice_id,),
            ).fetchone()

        if row is None:
            return None

        return Invoice(
            id=row["id"],
            subscription_id=row["subscription_id"],
            period_start=date.fromisoformat(row["period_start"]),
            period_end=date.fromisoformat(row["period_end"]),
            subtotal=Money(row["subtotal"], row["currency"]),
            discount_total=Money(row["discount_total"], row["currency"]),
            tax_total=Money(row["tax_total"], row["currency"]),
            total=Money(row["total"], row["currency"]),
            status=InvoiceStatus(row["status"]),
            issued_at=(
                datetime.fromisoformat(row["issued_at"])
                if row["issued_at"] else None
            ),
            pdf_path=row["pdf_path"],
        )

    def count_for_subscription(self, subscription_id: int) -> int:
        """Used by FirstMonthFree discount."""
        
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM invoices
                WHERE subscription_id = ?
                """,
                (subscription_id,),
            ).fetchone()

        return row["count"]

    def mark_paid(self, invoice_id: int) -> None:
        
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE invoices
                SET status = ?
                WHERE id = ?
                """,
                (
                    InvoiceStatus.PAID.value,
                    invoice_id,
                ),
            )

    def mark_failed(self, invoice_id: int) -> None:
        
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE invoices
                SET status = ?
                WHERE id = ?
                """,
                (
                    InvoiceStatus.FAILED.value,
                    invoice_id,
                ),
            )

    def set_pdf_path(self, invoice_id: int, path: str) -> None:
        # TODO Day 4.
        # Hint: q.update_invoice_pdf_path(...)
        raise NotImplementedError("Day 4: implement InvoiceRepository.set_pdf_path")


class InvoiceLineItemRepository:
    """Persistence boundary for invoice detail rows.

    Line items explain how the invoice total was built: base charge, usage,
    discount, tax, or proration. They are separate from the invoice header so
    one invoice can contain multiple visible charges and credits.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, line_item: InvoiceLineItem) -> InvoiceLineItem:
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO invoice_line_items(
                    invoice_id,
                    description,
                    amount,
                    kind
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    line_item.invoice_id,
                    line_item.description,
                    line_item.amount.to_storage(),
                    line_item.kind.value,
                ),
            )

        return InvoiceLineItem(
            id=cur.lastrowid,
            invoice_id=line_item.invoice_id,
            description=line_item.description,
            amount=line_item.amount,
            kind=line_item.kind,
        )

    def list_for_invoice(self, invoice_id: int) -> list[InvoiceLineItem]:
        
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT ili.*, i.currency
                FROM invoice_line_items ili
                JOIN invoices i
                ON ili.invoice_id = i.id
                WHERE ili.invoice_id = ?
                ORDER BY ili.id
                """,
                (invoice_id,),
            ).fetchall()

        return [
            InvoiceLineItem(
                id=row["id"],
                invoice_id=row["invoice_id"],
                description=row["description"],
                amount=Money(row["amount"], row["currency"]),
                kind=LineItemKind(row["kind"]),
            )
            for row in rows
        ]


# ============================================================
# DAY 3/4 ONLY — keep stubs for later
# ============================================================

# ============================================================
# LEDGER — APPEND-ONLY (do not implement update/delete)
# ============================================================
class LedgerRepository:
    """Persistence boundary for the append-only accounting ledger.

    The ledger records financial movements: DEBIT when the customer owes money,
    CREDIT when money is received or reversed. It is append-only so history is
    auditable; mistakes should be corrected with reversing entries, not edits.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, entry: LedgerEntry) -> LedgerEntry:
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO ledger_entries(
                    invoice_id,
                    customer_id,
                    amount,
                    currency,
                    direction,
                    reason
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.invoice_id,
                    entry.customer_id,
                    entry.amount.to_storage(),
                    entry.amount.currency,
                    entry.direction.value,
                    entry.reason,
                ),
            )

        return LedgerEntry(
            id=cur.lastrowid,
            invoice_id=entry.invoice_id,
            customer_id=entry.customer_id,
            amount=entry.amount,
            direction=entry.direction,
            reason=entry.reason,
        )
    
    def post_debit(
        self,
        customer_id: int,
        amount,
        description: str,
        as_of=None,):
        """
        Record a DEBIT entry in the ledger.
        """
        from billing_engine.models import (
            LedgerEntry,
            LedgerDirection,
        )

        return self.add(
            LedgerEntry(
                id=None,
                invoice_id=None,
                customer_id=customer_id,
                amount=amount,
                direction=LedgerDirection.DEBIT,
                reason=description,
            )
        )

    def list_for_customer(self, customer_id: int) -> list[LedgerEntry]:
        
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM ledger_entries
                WHERE customer_id = ?
                ORDER BY id
                """,
                (customer_id,),
            ).fetchall()

        return [
            LedgerEntry(
                id=row["id"],
                invoice_id=row["invoice_id"],
                customer_id=row["customer_id"],
                amount=Money(row["amount"], row["currency"]),
                direction=LedgerDirection(row["direction"]),
                reason=row["reason"],
                created_at=(
                    datetime.fromisoformat(row["created_at"])
                    if row["created_at"] else None
                ),
            )
            for row in rows
        ]

    # These two methods are intentionally implemented to REJECT — do not override.
    def update(self, *args, **kwargs):
        raise NotImplementedError("Ledger is append-only. Post a reversing entry instead.")

    def delete(self, *args, **kwargs):
        raise NotImplementedError("Ledger is append-only. Post a reversing entry instead.")


# ============================================================
# PAYMENT ATTEMPTS
# ============================================================
class PaymentAttemptRepository:
    """Persistence boundary for payment retry history.

    Each payment attempt records whether charging an invoice succeeded or
    failed, why it failed, and when the next retry should happen. This history
    powers the Day 3/4 dunning flow.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self,
        invoice_id: int,
        attempt_no: int,
        status: str,
        failure_reason: Optional[str],
        next_retry_at: Optional[datetime],
    ) -> int:
        # TODO Day 3.
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO payment_attempts
                (
                    invoice_id,
                    attempt_no,
                    status,
                    failure_reason,
                    next_retry_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    attempt_no,
                    status,
                    failure_reason,
                    next_retry_at.isoformat()
                    if next_retry_at else None,
                ),
            )

        return int(cur.lastrowid)

    def list_for_invoice(self, invoice_id: int) -> list[dict]:
        # TODO Day 3.
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM payment_attempts
                WHERE invoice_id = ?
                ORDER BY attempt_no
                """,
                (invoice_id,),
            ).fetchall()

        return [
            {
                "id": row["id"],
                "invoice_id": row["invoice_id"],
                "attempt_no": row["attempt_no"],
                "status": row["status"],
                "failure_reason": row["failure_reason"],
                "next_retry_at": (
                    datetime.fromisoformat(row["next_retry_at"])
                    if row["next_retry_at"]
                    else None
                ),
                "created_at": (
                    datetime.fromisoformat(row["created_at"])
                    if row["created_at"]
                    else None
                ),
            }
            for row in rows
        ]

    def count_for_invoice(self, invoice_id: int) -> int:
        # TODO Day 3.
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM payment_attempts
                WHERE invoice_id = ?
                """,
                (invoice_id,),
            ).fetchone()

        return row["count"]
