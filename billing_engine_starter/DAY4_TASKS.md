# Day 4 — Dunning, Proration, and the CLI Demo

> **Goal by end of Day 4:** A scripted end-to-end demo runs through trial → invoice → failed payments → retry → success → mid-cycle upgrade with correct proration. All tests in `test_dunning.py`, `test_proration.py`, and `test_demo_scenario.py` are green.

Today is about workflows: the retry state machine, the proration algorithm, and gluing everything together in a CLI.

**PDF generation is OUT of scope.** Invoices print as plain text. If you finish early, there are bonus ideas at the bottom.

You will learn:
- Implementing a finite state machine for retries
- Date math for mid-cycle plan changes
- Wrapping multi-step operations in a transaction
- Building a human-usable CLI with `argparse`

---

## Step 1 — Reconnect
`pytest -v` should show Day 1, Day 2, and Day 3 tests passing. Today's targets are:

- `tests/test_dunning.py`
- `tests/test_proration.py`
- `tests/test_demo_scenario.py`

## Step 2 — Implement `DunningProcess`
File: `billing_engine/billing/dunning.py`

Implement the retry state machine in `attempt(...)` and the helper `should_cancel(...)`.

The gateway and attempt-repository pieces should already be available from Day 3.

Start with this concrete code sample:

```python
def attempt(self, invoice: Invoice, customer_id: int, now: datetime) -> DunningOutcome:
    attempt_no = self.attempt_repo.count_for_invoice(invoice.id) + 1
    result = self.gateway.charge(invoice)

    if result.success:
        self.invoice_repo.mark_paid(invoice.id)
        self.ledger_repo.add(LedgerEntry(
            id=None, invoice_id=invoice.id, customer_id=customer_id,
            amount=invoice.total, direction=LedgerDirection.CREDIT,
            reason=f"Payment for invoice {invoice.id}",
        ))
        self.attempt_repo.add(invoice.id, attempt_no, "SUCCESS", None, None)
        return DunningOutcome(DunningState.SUCCEEDED, attempt_no, None)

    if attempt_no >= MAX_ATTEMPTS:
        self.invoice_repo.mark_failed(invoice.id)
        self.subscription_repo.update_status(
            invoice.subscription_id, SubscriptionStatus.PAST_DUE,
            past_due_since=now.date(),
        )
        self.attempt_repo.add(invoice.id, attempt_no, "FAILED", result.failure_reason, None)
        return DunningOutcome(DunningState.FAILED_FINAL, attempt_no, None)

    delay = RETRY_DELAYS_DAYS[attempt_no]
    next_retry = now + timedelta(days=delay)
    self.attempt_repo.add(invoice.id, attempt_no, "FAILED", result.failure_reason, next_retry)
    return DunningOutcome(DunningState.RETRYING, attempt_no, next_retry)
```

And the helper sample:

```python
@staticmethod
def should_cancel(past_due_since: date, today: date, grace_days: int = 7) -> bool:
    return (today - past_due_since).days >= grace_days
```

**Pseudocode**
```text
attempt():
  attempt_no = prior_attempts + 1
  result = gateway.charge(invoice)

  if success:
    mark invoice PAID
    post ledger CREDIT
    save SUCCESS payment_attempt
    return SUCCEEDED

  if failed and this was final attempt:
    mark invoice FAILED
    mark subscription PAST_DUE with date
    save FAILED payment_attempt (no retry time)
    return FAILED_FINAL

  otherwise:
    compute next retry time from retry-delay table
    save FAILED payment_attempt (with next_retry_at)
    return RETRYING

should_cancel():
  return (today - past_due_since).days >= grace_days
```

Run `pytest tests/test_dunning.py -v`.

## Step 3 — Implement `compute_proration`
File: `billing_engine/billing/proration.py`

This is the headline algorithm of the capstone.

Use this code sample as the exact order of operations:

```python
def compute_proration(
    old_plan_price: Money,
    new_plan_price: Money,
    period_start: date,
    period_end: date,
    switch_date: date,
    tax_calc: TaxCalculator,
    tax_context: TaxContext,
) -> ProrationResult:
    if not (period_start <= switch_date <= period_end):
        raise ValueError(f"switch_date {switch_date} outside period [{period_start}, {period_end}]")
    if old_plan_price.currency != new_plan_price.currency:
        raise ValueError("Cannot prorate across currencies")

    total_days = (period_end - period_start).days
    if total_days <= 0:
        raise ValueError("Period must be positive")

    remaining_days = (period_end - switch_date).days
    ratio = Decimal(remaining_days) / Decimal(total_days)

    credit_amount = old_plan_price * ratio
    charge_amount = new_plan_price * ratio

    credit_tax = tax_calc.apply(credit_amount, tax_context).total
    charge_tax = tax_calc.apply(charge_amount, tax_context).total

    return ProrationResult(credit_amount, charge_amount, credit_tax, charge_tax)
```

**Pseudocode**
```text
validate inputs:
  switch_date inside billing period
  currencies match
  period length > 0

compute ratio:
  total_days = period_end - period_start
  remaining_days = period_end - switch_date
  ratio = remaining_days / total_days

compute amounts:
  credit = old_plan_price * ratio
  charge = new_plan_price * ratio
  credit_tax = tax(credit)
  charge_tax = tax(charge)

return ProrationResult(credit, charge, credit_tax, charge_tax)
```

Run `pytest tests/test_proration.py -v`.

## Step 4 — Wire `upgrade_subscription`
File: `billing_engine/billing/cycle.py`

Implement the mid-cycle upgrade flow:

1. Load subscription, old plan, new plan, and customer.
2. Compute old and new plan prices.
3. Call `compute_proration(...)`.
4. Create a proration invoice with credit and charge line items.
5. Post the matching ledger DEBIT.
6. Switch the subscription's `plan_id`.

You will likely need `SubscriptionRepository.update_plan(...)`.

**Code sample (shape only):**
```python
with self.db.transaction() as conn:
    pr = compute_proration(...)
    invoice = self.invoice_repo.add(Invoice(...))
    self.line_item_repo.add(InvoiceLineItem(..., kind=LineItemKind.PRORATION_CREDIT))
    self.line_item_repo.add(InvoiceLineItem(..., kind=LineItemKind.PRORATION_CHARGE))
    self.ledger_repo.add(LedgerEntry(..., direction=LedgerDirection.DEBIT, ...))
    self.subscription_repo.update_plan(subscription_id, new_plan_id)
```

**Pseudocode**
```text
load subscription + old plan + new plan + customer
calculate old/new plan prices
call compute_proration()
create proration invoice
add credit and charge line items
post matching ledger debit
switch subscription to new plan
```

## Step 5 — Build the CLI
File: `billing_engine/cli.py`

Implement these subcommands:

```text
billing init
billing customer add NAME EMAIL COUNTRY [--state CODE]
billing plan list
billing subscribe CUSTOMER_ID PLAN_ID [--trial-days N] [--discount CODE]
billing bill run [--date YYYY-MM-DD]
billing invoice show INVOICE_ID
billing upgrade SUBSCRIPTION_ID NEW_PLAN_ID [--date YYYY-MM-DD]
billing demo
```

**Code sample (`argparse` skeleton):**
```python
parser = argparse.ArgumentParser(prog="billing")
sub = parser.add_subparsers(dest="cmd", required=True)

sub.add_parser("init")
plan_cmd = sub.add_parser("plan")
plan_sub = plan_cmd.add_subparsers(dest="plan_subcmd", required=True)
plan_sub.add_parser("list")
```

**Pseudocode**
```text
parse args
dispatch by subcommand
  init -> create db + schema
  customer add -> insert customer
  subscribe -> insert subscription
  bill run -> BillingCycle.run(date)
  invoice show -> print invoice + line items
  upgrade -> run upgrade flow
  demo -> run scripted scenario
```

For `billing invoice show`, print a plain-text invoice like this:

```text
================================
       INVOICE INV-{id}
================================
Customer: {name} ({email})
Period:   {period_start} → {period_end}
Status:   {status}
--------------------------------
{kind: BASE / USAGE / ...}
  {description}              {amount}
--------------------------------
Subtotal:                    {subtotal}
Discount:                    {discount_total}
Tax:                         {tax_total}
TOTAL:                       {total}
================================
```

## Step 6 — End-to-end scenario
Read `tests/test_demo_scenario.py::test_full_lifecycle` and implement `run_demo()` to perform the same sequence with human-readable output.

**Pseudocode**
```text
init db
create customer + plans + subscription
run billing cycle
simulate failed then successful payment attempts
upgrade mid-cycle
show proration invoice and final ledger snapshot
```

Run:

```bash
pytest tests/test_demo_scenario.py -v
```

---

## End-of-Day Demo

```bash
billing init
billing demo
```

Expected: a play-by-play of customer creation, trial, invoicing, failed-then-successful payment attempts, mid-cycle upgrade, proration invoice, and final ledger state.

---

## Done-for-the-day checklist
- [ ] `DunningProcess` correctly handles success / retry / final-failure paths
- [ ] `compute_proration` is correct for day-1, last-day, downgrade, and tax-on-both-legs
- [ ] `upgrade_subscription` creates a proration invoice and switches the plan
- [ ] CLI subcommands work
- [ ] `billing demo` runs end-to-end with no errors
- [ ] `pytest --cov=billing_engine` shows strong coverage
- [ ] Code committed and pushed

## Bonus
1. Implement PDF invoice rendering with `reportlab`.
2. Build a small Streamlit dashboard for customer ledger and MRR.
3. Emit invoice webhooks on `PAID` / `FAILED` transitions.

## If you fall behind
Skip in this order:

1. Skip proration entirely.
2. Skip dunning retry math and implement only single-attempt payments.
3. Skip CLI subcommands beyond `init` and `demo`.

Shipping Day 1 + Day 2 + Day 3 + basic dunning with green tests is still a solid outcome.