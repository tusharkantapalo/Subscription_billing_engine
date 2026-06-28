"""
SQL helper functions for repositories.

Purpose:
- Keep raw SQL in one place.
- Let repository methods focus on conversions and domain mapping.

Design:
- Functions are thin wrappers over `conn.execute(...)`.
- Repositories pass already-converted values (enum.value, iso dates, money strings).
"""

from __future__ import annotations

import sqlite3
from typing import Optional


# ============================================================
# CUSTOMERS
# ============================================================
def insert_customer(
    conn: sqlite3.Connection,
    name: str,
    email: str,
    country_code: str,
    state_code: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO customers (name, email, country_code, state_code)
        VALUES (?, ?, ?, ?)
        """,
        (name, email, country_code, state_code),
    )
    return int(cur.lastrowid)


def select_customer_by_id(conn: sqlite3.Connection, customer_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()


def select_customer_by_email(conn: sqlite3.Connection, email: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()


def select_all_customers(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM customers ORDER BY id").fetchall()


# ============================================================
# PLANS + PLAN TIERS
# ============================================================
def insert_plan(
    conn: sqlite3.Connection,
    name: str,
    pricing_type: str,
    billing_period: str,
    currency: str,
    config_json: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO plans (name, pricing_type, billing_period, currency, config_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, pricing_type, billing_period, currency, config_json),
    )
    return int(cur.lastrowid)


def select_plan_by_id(conn: sqlite3.Connection, plan_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()


def select_all_plans(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM plans ORDER BY id").fetchall()


def insert_plan_tier(
    conn: sqlite3.Connection,
    plan_id: int,
    from_units: int,
    to_units: Optional[int],
    unit_price: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO plan_tiers (plan_id, from_units, to_units, unit_price)
        VALUES (?, ?, ?, ?)
        """,
        (plan_id, from_units, to_units, unit_price),
    )
    return int(cur.lastrowid)


def select_plan_tiers(conn: sqlite3.Connection, plan_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM plan_tiers WHERE plan_id = ? ORDER BY from_units",
        (plan_id,),
    ).fetchall()


# ============================================================
# DISCOUNTS
# ============================================================
def insert_discount(
    conn: sqlite3.Connection,
    code: str,
    discount_type: str,
    value: str,
    currency: Optional[str],
) -> int:
    cur = conn.execute(
        """
        INSERT INTO discounts (code, discount_type, value, currency)
        VALUES (?, ?, ?, ?)
        """,
        (code, discount_type, value, currency),
    )
    return int(cur.lastrowid)


def select_discount_by_code(conn: sqlite3.Connection, code: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM discounts WHERE code = ?", (code,)).fetchone()


# ============================================================
# SUBSCRIPTIONS
# ============================================================
def insert_subscription(
    conn: sqlite3.Connection,
    customer_id: int,
    plan_id: int,
    status: str,
    current_period_start: str,
    current_period_end: str,
    trial_end: Optional[str],
    discount_id: Optional[int],
    past_due_since: Optional[str],
) -> int:
    cur = conn.execute(
        """
        INSERT INTO subscriptions
        (customer_id, plan_id, status, current_period_start, current_period_end, trial_end, discount_id, past_due_since)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            plan_id,
            status,
            current_period_start,
            current_period_end,
            trial_end,
            discount_id,
            past_due_since,
        ),
    )
    return int(cur.lastrowid)


def select_subscription_by_id(conn: sqlite3.Connection, subscription_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)).fetchone()


def select_all_subscriptions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM subscriptions ORDER BY id").fetchall()


def select_due_subscriptions(conn: sqlite3.Connection, as_of_iso: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM subscriptions
        WHERE status = 'ACTIVE' AND current_period_end <= ?
        ORDER BY id
        """,
        (as_of_iso,),
    ).fetchall()


def update_subscription_period(
    conn: sqlite3.Connection, subscription_id: int, new_start_iso: str, new_end_iso: str
) -> None:
    conn.execute(
        """
        UPDATE subscriptions
        SET current_period_start = ?, current_period_end = ?
        WHERE id = ?
        """,
        (new_start_iso, new_end_iso, subscription_id),
    )


def update_subscription_status(
    conn: sqlite3.Connection, subscription_id: int, new_status: str, past_due_since_iso: Optional[str]
) -> None:
    conn.execute(
        """
        UPDATE subscriptions
        SET status = ?, past_due_since = ?
        WHERE id = ?
        """,
        (new_status, past_due_since_iso, subscription_id),
    )


def update_subscription_plan(conn: sqlite3.Connection, subscription_id: int, new_plan_id: int) -> None:
    conn.execute(
        "UPDATE subscriptions SET plan_id = ? WHERE id = ?",
        (new_plan_id, subscription_id),
    )


# ============================================================
# USAGE
# ============================================================
def insert_usage_record(conn: sqlite3.Connection, subscription_id: int, metric: str, quantity: int) -> int:
    cur = conn.execute(
        """
        INSERT INTO usage_records (subscription_id, metric, quantity)
        VALUES (?, ?, ?)
        """,
        (subscription_id, metric, quantity),
    )
    return int(cur.lastrowid)


def sum_usage_for_subscription_metric(conn: sqlite3.Connection, subscription_id: int, metric: str) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(quantity), 0) AS total
        FROM usage_records
        WHERE subscription_id = ? AND metric = ?
        """,
        (subscription_id, metric),
    ).fetchone()
    return int(row["total"])


# ============================================================
# INVOICES + LINE ITEMS
# ============================================================
def insert_invoice(
    conn: sqlite3.Connection,
    subscription_id: int,
    period_start: str,
    period_end: str,
    currency: str,
    subtotal: str,
    discount_total: str,
    tax_total: str,
    total: str,
    status: str,
    issued_at: Optional[str],
    pdf_path: Optional[str],
) -> int:
    cur = conn.execute(
        """
        INSERT INTO invoices
        (subscription_id, period_start, period_end, currency, subtotal, discount_total, tax_total, total, status, issued_at, pdf_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
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
            pdf_path,
        ),
    )
    return int(cur.lastrowid)


def select_invoice_by_id(conn: sqlite3.Connection, invoice_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()


def count_invoices_for_subscription(conn: sqlite3.Connection, subscription_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM invoices WHERE subscription_id = ?",
        (subscription_id,),
    ).fetchone()
    return int(row["cnt"])


def update_invoice_status(conn: sqlite3.Connection, invoice_id: int, status: str) -> None:
    conn.execute("UPDATE invoices SET status = ? WHERE id = ?", (status, invoice_id))


def update_invoice_pdf_path(conn: sqlite3.Connection, invoice_id: int, path: str) -> None:
    conn.execute("UPDATE invoices SET pdf_path = ? WHERE id = ?", (path, invoice_id))


def insert_invoice_line_item(
    conn: sqlite3.Connection,
    invoice_id: int,
    description: str,
    amount: str,
    kind: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO invoice_line_items (invoice_id, description, amount, kind)
        VALUES (?, ?, ?, ?)
        """,
        (invoice_id, description, amount, kind),
    )
    return int(cur.lastrowid)


def select_line_items_for_invoice(conn: sqlite3.Connection, invoice_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM invoice_line_items WHERE invoice_id = ? ORDER BY id",
        (invoice_id,),
    ).fetchall()


# ============================================================
# LEDGER
# ============================================================
def insert_ledger_entry(
    conn: sqlite3.Connection,
    invoice_id: Optional[int],
    customer_id: int,
    amount: str,
    currency: str,
    direction: str,
    reason: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO ledger_entries (invoice_id, customer_id, amount, currency, direction, reason)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (invoice_id, customer_id, amount, currency, direction, reason),
    )
    return int(cur.lastrowid)


def select_ledger_for_customer(conn: sqlite3.Connection, customer_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM ledger_entries
        WHERE customer_id = ?
        ORDER BY created_at, id
        """,
        (customer_id,),
    ).fetchall()


# ============================================================
# PAYMENT ATTEMPTS
# ============================================================
def insert_payment_attempt(
    conn: sqlite3.Connection,
    invoice_id: int,
    attempt_no: int,
    status: str,
    failure_reason: Optional[str],
    next_retry_at: Optional[str],
) -> int:
    cur = conn.execute(
        """
        INSERT INTO payment_attempts
        (invoice_id, attempt_no, status, failure_reason, next_retry_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (invoice_id, attempt_no, status, failure_reason, next_retry_at),
    )
    return int(cur.lastrowid)


def select_attempts_for_invoice(conn: sqlite3.Connection, invoice_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM payment_attempts WHERE invoice_id = ? ORDER BY attempt_no",
        (invoice_id,),
    ).fetchall()


def count_attempts_for_invoice(conn: sqlite3.Connection, invoice_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM payment_attempts WHERE invoice_id = ?",
        (invoice_id,),
    ).fetchone()
    return int(row["cnt"])
