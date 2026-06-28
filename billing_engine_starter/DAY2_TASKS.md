# Day 2 — Storage: SQLite, Repositories, and the Invoice Pipeline

> **Goal by end of Day 2:** The core repository tests and `test_pipeline.py` are green, and you understand what extra repository methods BillingCycle will need on Day 3.

Today you connect yesterday's pure math to a real SQLite database. You will learn:
- Designing repository classes that hide SQL from business logic
- Writing parameterized SQL queries
- Storing `Money` as TEXT, not REAL
- Storing dates as ISO strings
- Using database constraints to protect billing logic
- Building a pure-function invoice pipeline

---

## Step 1 — Reconnect
Run `pytest -v`. You should still see all of Day 1 passing. Today's focus is:

- `tests/test_repositories.py`
- `tests/test_pipeline.py`

## Step 2 — Understand the schema
Open `billing_engine/db/schema.sql` and read it slowly.

For each table, answer for yourself:

1. What does it represent in the business?
2. What are its foreign keys?
3. What CHECK constraints exist?
4. What UNIQUE constraints exist?

Pay special attention to:

- `invoices.UNIQUE(subscription_id, period_start)`
- `ledger_entries` being append-only by convention
- money values being stored as text, not floats

## Step 3 — Read the database helper
Open `billing_engine/db/database.py` and understand:

1. `self.connect()` returns a fresh connection with foreign keys enabled.
2. `with db.transaction() as conn:` groups related writes atomically.

## Step 4 — Implement repositories
File: `billing_engine/db/repository.py`

Implement only the Day 2 persistence spine, in this order: **Customer** → **Plan** → **PlanTier** → **Discount** → **Subscription** → **Usage** → **Invoice** → **InvoiceLineItem**.

Leave billing-cycle, ledger, payment, and PDF helpers for later days. Their method stubs stay in `repository.py` so you can see where the project is going, but they are not part of today's work.

**Important for this cohort:** raw SQL has been moved to `billing_engine/db/queries.py`.  
In Day 2, students should **call query helper functions** from repositories instead of writing SQL from scratch.

### Core Patterns (use everywhere)

**Transaction vs connection:**
```
with self.db.transaction() as conn:  # for INSERT/UPDATE/DELETE
  cur = conn.execute(...)

with self.db.connect() as conn:      # for SELECT
  rows = conn.execute(...).fetchall()
```

**Query helper pattern (new):**
```python
from billing_engine.db import queries as q
```
- In repository methods, call `q.some_function(conn, ...)`.
- Focus student effort on conversions and row-to-dataclass mapping.
- If a needed helper does not exist yet, add it in `queries.py` first.

**Conversions before storing:**
- Enums: `.value` (e.g., `status.value` → string)
- Dates: `.isoformat()` (e.g., `date(2026,1,15)` → `"2026-01-15"`)
- Money: `.to_storage()` (e.g., `Money("100","INR").to_storage()` → `"100.00"`)
- Nullable: check `if x is None` before calling `.isoformat()`, `.value`

**Conversions when reading:**
- Strings → Enums: `EnumClass(row["field"])`
- Strings → Dates: `date.fromisoformat(row["field"])`
- Strings → Money: `Money(row["amount"], row["currency"])`  ← **ALWAYS include currency**

---

### 4a. CustomerRepository
Methods: `add`, `get`, `find_by_email`, `list_all`

**Worked example — `find_by_email`:**
```python
def find_by_email(self, email: str) -> Optional[Customer]:
    with self.db.connect() as conn:
        row = q.select_customer_by_email(conn, email)
    if row is None:
        return None
    return Customer(id=row["id"], name=row["name"], email=row["email"], country_code=row["country_code"], state_code=row["state_code"])
```

Now implement `add` (INSERT), `get`, `list_all` using similar patterns.

---

### 4b. PlanRepository
Methods: `add`, `get`, `list_all`

**Challenge:** Plans have enums (`pricing_type`, `billing_period`).

**Pseudocode for `add`:**
```
Open transaction
    INSERT (name, pricing_type, billing_period, currency, config_json)
    REMEMBER: convert .pricing_type.value and .billing_period.value
    Get lastrowid
Return Plan with id populated
```

For `get` and `list_all`, reverse the process: convert enum strings back when reading.

---

### 4c. PlanTierRepository
Methods: `add`, `list_for_plan`

**Pseudocode for `add`:**
```
Open transaction
   INSERT (plan_id, from_units, to_units, unit_price)
   Store unit_price using .to_storage()
    Get lastrowid
Return the new tier id
```

**Pseudocode for `list_for_plan`:**
```
SELECT all tiers for plan_id, ordered by from_units
For each row:
    Reconstruct as (from_units, to_units, Money(amount, currency))
    NOTE: currency is passed in as a parameter (from the parent plan)
Return list
```

---

### 4d. DiscountRepository
Methods: `add`, `get_by_code`

Simple 1-to-1 mapping. Return raw dict (discount logic is complex, not a typed dataclass yet).

---

### 4e. SubscriptionRepository (most important!)
Methods today: `add`, `get`, `list_all`, `get_due_for_billing`

Leave `update_period` and `update_status` for Day 3. They are workflow helpers used by `BillingCycle.run`.

**Challenge:** Handle dates AND enums correctly.

**Create a helper method to avoid duplication:**
```python
def _row_to_subscription(self, row) -> Subscription:
    """Convert DB row to Subscription object."""
    return Subscription(
        id=row["id"],
        status=SubscriptionStatus(row["status"]),  # string → enum
        current_period_start=date.fromisoformat(row["current_period_start"]),  # string → date
        current_period_end=date.fromisoformat(row["current_period_end"]),
        trial_end=date.fromisoformat(row["trial_end"]) if row["trial_end"] else None,
        ...  # (map all other fields)
    )
```

Then use this helper in `get`, `list_all`, and `get_due_for_billing`.

**Critical: `get_due_for_billing` query:**
```
SELECT * FROM subscriptions
WHERE status = 'ACTIVE' AND current_period_end <= as_of.isoformat()
ORDER BY id
```
(This query is called by BillingCycle.run on Day 3 — get it exactly right.)

---

### 4f. UsageRecordRepository
Methods: `add`, `sum_for_period`

**Pseudocode for `sum_for_period`:**
```
SELECT COALESCE(SUM(quantity), 0) FROM usage_records
WHERE subscription_id = ? AND metric = ?
Return the sum (int)
NOTE: Do NOT filter by date range
```

---

### 4g. InvoiceRepository
Methods today: `add`, `get`

Leave `count_for_subscription` for Day 3 and `mark_paid` / `mark_failed` for Day 4 payment and dunning.

**Critical design:** Table has `UNIQUE(subscription_id, period_start)` for idempotency. Let `sqlite3.IntegrityError` raise naturally — caller (Day 3) catches it.

**Pseudocode for `add`:**
```
Open transaction
  INSERT all fields (convert Money via .to_storage(), dates via .isoformat(), status.value)
  Get lastrowid
Return Invoice with id populated
NOTE: Do NOT catch IntegrityError
```

**Pseudocode for `get`:**
```
SELECT * WHERE id = ?
If None, return None
Otherwise, reconstruct Money objects
REMEMBER: Money(row["subtotal"], row["currency"]) — currency is in row!
```

---

### 4h. InvoiceLineItemRepository
Methods: `add`, `list_for_invoice`

**Pseudocode for `add`:**
```
Open transaction
   INSERT (invoice_id, description, amount, kind)
  Convert amount.to_storage() and kind.value
  Get lastrowid
Return InvoiceLineItem with id populated
```

---

### 4i. LedgerRepository
Skip for Day 2.

Read the class docstring and the append-only `update` / `delete` stubs, but implement `add` and `list_for_customer` on Day 3 when BillingCycle starts posting accounting entries.

---

### 4j. PaymentAttemptRepository
Skip for now — implement on Day 3.

---

**Common Mistakes to Avoid:**

1. **Using f-strings in SQL:** Always use `?` placeholders.
   ```python
   # ❌ WRONG
   "SELECT * FROM customers WHERE id = {customer_id}"
   
   # ✅ RIGHT
   "SELECT * FROM customers WHERE id = ?", (customer_id,)
   ```

2. **Forgetting to convert enums:** Enums are Python objects; database stores strings.
   ```python
   # ❌ WRONG
   "INSERT INTO subscriptions (status) VALUES (?)", (subscription.status,)
   
   # ✅ RIGHT
   "INSERT INTO subscriptions (status) VALUES (?)", (subscription.status.value,)
   ```

3. **Forgetting to convert dates:** Dates must be ISO strings in the database.
   ```python
   # ❌ WRONG
   "INSERT INTO invoices (period_start) VALUES (?)", (invoice.period_start,)
   
   # ✅ RIGHT
   "INSERT INTO invoices (period_start) VALUES (?)", (invoice.period_start.isoformat(),)
   ```

4. **Storing Money as float:** Always use `.to_storage()` to get the string.
   ```python
   # ❌ WRONG
   "INSERT INTO invoices (subtotal) VALUES (?)", (invoice.subtotal.amount,)
   
   # ✅ RIGHT
   "INSERT INTO invoices (subtotal) VALUES (?)", (invoice.subtotal.to_storage(),)
   ```

5. **Forgetting currency when reconstructing Money:** Currency lives on the entity, not the Money storage.
   ```python
   # ❌ WRONG
   Money(row["subtotal"], "INR")  # Hardcoded currency
   
   # ✅ RIGHT
   currency = row["currency"]
   Money(row["subtotal"], currency)
   ```

6. **Not handling nullable fields:** Always check for None before calling `.isoformat()` or `.value`.
   ```python
   # ❌ WRONG
   subscription.trial_end.isoformat()
   
   # ✅ RIGHT
   subscription.trial_end.isoformat() if subscription.trial_end else None
   ```

---

**Checkpoint:** `pytest tests/test_repositories.py -v` should be green for the reduced Day 2 repository scope.

---

## Step 5 — Build the invoicing pipeline
File: `billing_engine/billing/pipeline.py`

Implement the **pure function** `build_invoice()`. No database access. No `datetime.now()`. All inputs passed in; all state returned.

**Pseudocode (YOU implement each step):**
```
1. Compute base charge from strategy
   base = strategy.calculate(usage_quantity)

2. Apply discount (if present)
   if discount is None:
       discount_amount = Money.zero(base.currency)
   else:
       Create a DiscountContext with invoice_count_so_far
       discount_amount = discount.apply(base, context)

3. Compute taxable
   taxable = base - discount_amount

4. Apply tax
   breakdown = tax_calc.apply(taxable, tax_context)

5. Compute total
   total = taxable + breakdown.total

6. Build line items list
   Start with BASE line item (the service charge)
   If discount_amount > 0, add DISCOUNT line (amount is NEGATIVE)
   For each tax component, add TAX line (amounts are POSITIVE)
   All amounts use the same currency

7. Return Invoice with status = DRAFT
   id=None (not yet persisted)
```

**Key hints:**
- Discount line items are **negative**: `amount = -discount_amount`
- Tax line items are **positive**: use values from `breakdown.components`
- Return `InvoiceStatus.DRAFT` (not ISSUED — BillingCycle.run promotes it)
- All amounts use the same currency throughout
- This function is testable in isolation

**One worked example — the BASE line item:**
```python
line_items = [
    InvoiceLineItem(
        id=None,
        invoice_id=None,
        description=f"{plan.name} ({period_start} to {period_end})",
        amount=base,
        kind=LineItemKind.BASE,
    )
]
```

Now add DISCOUNT and TAX lines following the same pattern, then return the Invoice.

Run `pytest tests/test_pipeline.py -v`.

## Step 6 — Preview: BillingCycle.run for tomorrow
File: `billing_engine/billing/cycle.py`

Read `BillingCycle.run` top to bottom. You do not implement it today, but you must understand the flow so you can implement it on Day 3.

**What happens in BillingCycle.run:**

1. **Trial promotion (loop all subscriptions):**
   ```python
   # For every TRIAL subscription where trial_end <= as_of:
   #   - Call subscription_repo.update_status(sub.id, SubscriptionStatus.ACTIVE)
   #   - Increment trials_activated counter
   ```

2. **Load due subscriptions:**
   ```python
   due = subscription_repo.get_due_for_billing(as_of)
   # Returns: subscriptions where status=ACTIVE and current_period_end <= as_of
   ```

3. **For each due subscription:**
   ```python
   # a) Look up the customer and plan
   # b) Get the pricing strategy from strategy_factory(plan)
   # c) Get the discount from discount_factory(sub.discount_id)
   # d) Get the tax calculator and context from tax_factory(customer)
   # e) Sum usage for the period via usage_repo.sum_for_period(...)
   # f) Count existing invoices via invoice_repo.count_for_subscription(sub.id)  [Day 3 helper]
   # g) Call build_invoice(...) [this is your Day 2 function]
   # h) Persist the invoice and its line items
   # i) Post a DEBIT ledger entry for the invoice
   # j) Advance the period: subscription_repo.update_period(sub.id, new_start, new_end)
   ```

4. **Idempotency via the UNIQUE constraint:**
   ```python
   try:
       saved = invoice_repo.add(invoice)
       # ... persist line items and ledger ...
       invoices_created += 1
   except sqlite3.IntegrityError:
       # A duplicate (subscription_id, period_start) was attempted
       # This means the subscription was already billed for this period
       # Skip it and count as "skipped"
       invoices_skipped_duplicate += 1
   ```

**Questions to ask yourself before Day 3:**

1. **Trial promotion:** Where do we update the subscription status to ACTIVE?
   - Answer: Inside the loop over `list_all()` subscriptions.

2. **Which subscriptions get billed?** How do we find them?
   - Answer: `get_due_for_billing(as_of)` returns subscriptions where `status='ACTIVE' AND current_period_end <= as_of`.

3. **Why do we call `build_invoice` inside the loop, not outside?**
   - Answer: Each subscription's invoice is custom (different plan, discount, usage, tax rules). We build one per subscription.

4. **Which writes must happen in one transaction?**
   - Answer: invoice insert, line item inserts, ledger post, and period advance must all succeed or all fail together. Use `db.transaction()` to group them atomically.

5. **Why do we treat duplicate invoice inserts as skips instead of errors?**
   - Answer: **Idempotency.** If `BillingCycle.run` is called twice on the same date, the second call should skip already-invoiced subscriptions instead of crashing. The UNIQUE constraint on (subscription_id, period_start) enforces this automatically.

**Structure to expect:**
```
BillingCycle.run(as_of):
    // Phase 1: Trial promotion
    for sub in subscription_repo.list_all():
        if sub.status == TRIAL and sub.trial_end <= as_of:
            update_status(sub.id, ACTIVE)

    // Phase 2: Billing
    due = subscription_repo.get_due_for_billing(as_of)
    for sub in due:
        plan = plan_repo.get(sub.plan_id)
        customer = customer_repo.get(sub.customer_id)
        strategy = strategy_factory(plan)
        discount = discount_factory(sub.discount_id)
        tax_calc, tax_context = tax_factory(customer)
        usage = usage_repo.sum_for_period(...)
        
        invoice = build_invoice(...)  // Your Day 2 function!
        
        try:
            invoice = invoice_repo.add(invoice)
            for li in invoice.line_items:
                line_item_repo.add(li)
            ledger_repo.add(DEBIT entry)                  // Day 3 helper
            subscription_repo.update_period(new_start, new_end)  // Day 3 helper
            invoices_created++
        except IntegrityError:  // Duplicate (subscription_id, period_start)
            invoices_skipped++
    
    return BillingResult(invoices_created, invoices_skipped, trials_activated)
```

**Leave this for Day 3.** Do not rush to implement it today. Start it fresh on Day 3 when you are ready.

Run `pytest tests/test_repositories.py tests/test_pipeline.py -v`.

---

## End-of-Day Demo
In a Python REPL, verify you can persist and read back core data:

```python
from billing_engine.db.database import Database
from billing_engine.db.repository import CustomerRepository, PlanRepository
from billing_engine.models import BillingPeriod, Customer, Plan, PricingType

db = Database("/tmp/demo.db")
db.init_schema()

customers = CustomerRepository(db)
plans = PlanRepository(db)

cust = customers.add(Customer(None, "Aarav", "a@x.com", "IN", "MH"))
plan = plans.add(Plan(None, "Pro", PricingType.FLAT, BillingPeriod.MONTHLY, "INR"))

print(customers.get(cust.id))
print(plans.get(plan.id))
```

---

## Done-for-the-day checklist
- [ ] Repository methods are implemented
- [ ] Later-day repository stubs are intentionally still TODO
- [ ] `build_invoice` works as a pure function
- [ ] `pytest tests/test_repositories.py tests/test_pipeline.py -v` is green
- [ ] You understand the `BillingCycle.run` control flow before Day 3
- [ ] Code committed and pushed

## If you finish early
- Read `billing/cycle.py` and `tests/test_billing_cycle.py` for tomorrow.
- Implement `LedgerRepository.add`, `LedgerRepository.list_for_customer`, `SubscriptionRepository.update_period`, `SubscriptionRepository.update_status`, and `InvoiceRepository.count_for_subscription` if you want a head start on Day 3.

## If you fall behind
Skip in this order:

1. Leave all Day 3/4 repository stubs untouched.
2. Finish Customer, Plan, Subscription, Invoice, and LineItem before polishing optional repos.
3. Do not rush `BillingCycle.run` tonight. Start it fresh on Day 3.
