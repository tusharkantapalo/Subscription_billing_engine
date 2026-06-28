# Day 3 — Billing Cycle Integration and Payment Groundwork

> **Goal by end of Day 3:** `BillingCycle.run(as_of)` is green, and the payment groundwork is in place for Day 4. By end of day, `test_billing_cycle.py` is green and the payment gateway / attempt scaffolding is implemented.

Today is about integration. You already built the pricing math and the storage layer. Now you connect them into the core recurring-billing workflow.

You will learn:
- Wiring repositories to domain logic
- Using a pure pipeline inside an impure workflow
- Grouping related writes into one transaction
- Making billing idempotent with database constraints
- Building deterministic fakes for later workflow testing
- Debugging integration tests step by step

---

## Step 1 — Reconnect
`pytest -v` should show Day 1 and Day 2 tests passing. Today's target is `tests/test_billing_cycle.py`.

## Step 2 — Finish the repository helpers BillingCycle needs
File: `billing_engine/db/repository.py`

Day 2 intentionally skipped a few methods that only matter once the workflow is assembled. Implement these before starting `BillingCycle.run`:

1. `SubscriptionRepository.update_status(...)` — trial activation and dunning status changes.
2. `SubscriptionRepository.update_period(...)` — move a billed subscription to the next period.
3. `InvoiceRepository.count_for_subscription(...)` — needed by first-month-free discount logic.
4. `LedgerRepository.add(...)` — post a DEBIT when an invoice is issued.
5. `LedgerRepository.list_for_customer(...)` — verify customer account history.

Keep these small. They are simple UPDATE, COUNT, INSERT, and SELECT methods.

Use this pattern for each method: first copy the sample shape, then fill fields.

**Code sample (one method):**
```python
def update_period(self, subscription_id: int, new_start: date, new_end: date) -> None:
    with self.db.transaction() as conn:
        conn.execute(
            """
            UPDATE subscriptions
            SET current_period_start = ?, current_period_end = ?
            WHERE id = ?
            """,
            (new_start.isoformat(), new_end.isoformat(), subscription_id),
        )
```

**Pseudocode (for all 5 methods):**
```text
update_status:
  UPDATE subscriptions SET status=?, past_due_since=? WHERE id=?

update_period:
  UPDATE subscriptions SET current_period_start=?, current_period_end=? WHERE id=?

count_for_subscription:
  SELECT COUNT(*) FROM invoices WHERE subscription_id=?

ledger add:
  INSERT INTO ledger_entries (...) VALUES (...)
  return LedgerEntry with id=lastrowid

ledger list_for_customer:
  SELECT * FROM ledger_entries WHERE customer_id=? ORDER BY created_at, id
  map rows -> LedgerEntry list
```

## Step 3 — Implement `BillingCycle.run`
File: `billing_engine/billing/cycle.py`

This is the most important workflow in the project. It pulls together:

1. Trial activation
2. Due-subscription discovery
3. Usage lookup
4. Invoice construction via `build_invoice(...)`
5. Invoice persistence and line-item persistence
6. Ledger DEBIT posting
7. Period advancement
8. Duplicate-period protection via `sqlite3.IntegrityError`

Start from this minimal working skeleton:

```python
def run(self, as_of: date) -> BillingResult:
    invoices_created = 0
    invoices_skipped = 0
    trials_activated = 0

    for sub in self.subscription_repo.list_all():
        if sub.status == SubscriptionStatus.TRIAL and sub.trial_end and sub.trial_end <= as_of:
            self.subscription_repo.update_status(sub.id, SubscriptionStatus.ACTIVE)
            trials_activated += 1

    due = self.subscription_repo.get_due_for_billing(as_of)
    for sub in due:
        ...

    return BillingResult(invoices_created, invoices_skipped, trials_activated)
```

Then fill the inner due-loop with this sample shape:

```python
for sub in due:
    plan = self.plan_repo.get(sub.plan_id)
    customer = self.customer_repo.get(sub.customer_id)
    strategy = self.strategy_factory(plan)
    discount = self.discount_factory(sub.discount_id)
    tax_calc, tax_context = self.tax_factory(customer)
    usage = self.usage_repo.sum_for_period(sub.id, "units", sub.current_period_start, sub.current_period_end)
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
```

**Pseudocode for `run`:**
```text
Phase 1: promote trial -> active
  for each subscription:
    if TRIAL and trial_end <= as_of: update_status(ACTIVE)

Phase 2: bill due active subscriptions
  due = get_due_for_billing(as_of)
  for each due sub:
    load plan + customer
    build strategy / discount / tax
    load usage + prior invoice count
    invoice = build_invoice(...)
    try:
      in one transaction:
        save invoice
        save each line item
        post ledger debit
        update subscription period
      invoices_created += 1
    except sqlite3.IntegrityError:
      invoices_skipped += 1

return BillingResult(created, skipped, trials_activated)
```

Run `pytest tests/test_billing_cycle.py -v` after each meaningful checkpoint.

## Step 4 — Check idempotency and transaction boundaries
Before moving on, make sure you understand why these details matter:

1. `invoices.UNIQUE(subscription_id, period_start)` in `schema.sql`
2. Catching `sqlite3.IntegrityError` in `BillingCycle.run`
3. Keeping invoice insert, line items, ledger DEBIT, and period advance in one transaction

## Step 5 — Implement payment groundwork
Before Day 4, implement the small pieces that dunning depends on:

1. `billing_engine/payments/gateway.py`
2. `billing_engine/db/repository.py::PaymentAttemptRepository`

For the gateways:

- `ScriptedGateway` should return pre-seeded results in order.
- `FakeRandomGateway` should use a seeded `random.Random` instance.

For `PaymentAttemptRepository`, implement:

1. `add(...)`
2. `list_for_invoice(...)`
3. `count_for_invoice(...)`

This keeps Day 4 focused on workflow logic rather than low-level plumbing.

**Code sample (`add`)**
```python
def add(self, invoice_id: int, attempt_no: int, status: str, failure_reason: Optional[str], next_retry_at: Optional[datetime]) -> int:
    with self.db.transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO payment_attempts
            (invoice_id, attempt_no, status, failure_reason, next_retry_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                invoice_id,
                attempt_no,
                status,
                failure_reason,
                next_retry_at.isoformat() if next_retry_at else None,
            ),
        )
        return int(cur.lastrowid)
```

**Pseudocode**
```text
ScriptedGateway:
  keep a list of pre-seeded results
  each charge() returns next result in order

FakeRandomGateway:
  use random.Random(seed)
  deterministic pass/fail based on random number

PaymentAttemptRepository:
  add -> INSERT one row
  list_for_invoice -> SELECT rows ORDER BY attempt_no
  count_for_invoice -> SELECT COUNT(*)
```

## Step 6 — Validate the full Day 3 slice
Run:

```bash
pytest tests/test_repositories.py tests/test_pipeline.py tests/test_billing_cycle.py -v
```

If you finish the gateway and attempt-repository groundwork too, Day 4 becomes much more manageable.

---

## End-of-Day Demo
In a REPL or a small script, run `BillingCycle.run(...)` twice on the same date and confirm the second run skips duplicates instead of creating another invoice for the same period.

---

## Done-for-the-day checklist
- [ ] `BillingCycle.run` produces invoices, posts ledger DEBITs, and advances periods
- [ ] Running `BillingCycle.run` twice on the same date does not create duplicate invoices
- [ ] Trial subscriptions transition to `ACTIVE` on `trial_end`
- [ ] `pytest tests/test_billing_cycle.py -v` is green
- [ ] `ScriptedGateway` and `FakeRandomGateway` are implemented
- [ ] `PaymentAttemptRepository` methods are implemented
- [ ] Code committed and pushed

## If you finish early
- Read [DAY4_TASKS.md](DAY4_TASKS.md) so you can start payments and dunning quickly tomorrow.

## If you fall behind
Skip in this order:

1. Skip trial activation first.
2. Ship the happy path first.
3. Add idempotency before the end of the day even if other edge cases remain.
4. Leave `FakeRandomGateway` for the end if needed, but finish `ScriptedGateway` first.
