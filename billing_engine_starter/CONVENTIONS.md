# Coding Conventions — Read Before Writing Any Code

These rules are **non-negotiable**. Code review will reject violations.

---

## 1. Money is `Decimal`, never `float`

```python
# ❌ WRONG — will compound rounding errors
price = 0.1 + 0.2          # 0.30000000000000004
tax = price * 0.18

# ✅ RIGHT — use Money / Decimal
from billing_engine.money import Money
price = Money("0.10", "INR") + Money("0.20", "INR")
```

**Why:** Floating point cannot represent decimal fractions exactly. `0.1 + 0.2 != 0.3` in `float`. In billing, this becomes "the company lost ₹0.04 over 10 million invoices" — a real bug.

**Enforcement:** A test grep-checks for `float(` and bare `0.0`-style literals in `billing_engine/`. It will fail your build.

---

## 2. No `isinstance` checks on strategies, discounts, or taxes

```python
# ❌ WRONG — defeats the whole point of polymorphism
if isinstance(strategy, FlatRate):
    amount = strategy.fixed_price
elif isinstance(strategy, TieredPricing):
    amount = compute_tiered(strategy.tiers, usage)
```

```python
# ✅ RIGHT — let the object compute itself
amount = strategy.calculate(usage)
```

**Why:** If you ever add a new strategy, the `isinstance` chain breaks. Polymorphism = the caller doesn't know or care which subclass it has.

**Allowed exceptions:** `isinstance(x, Money)` in defensive type checks is fine. Never on a strategy/discount/tax subclass.

---

## 3. No SQL outside `billing_engine/db/repository.py`

```python
# ❌ WRONG — SQL leaking into business logic
def run_billing_cycle():
    conn = sqlite3.connect("billing.db")
    cursor = conn.execute("SELECT * FROM subscriptions WHERE ...")
```

```python
# ✅ RIGHT — repository hides storage
def run_billing_cycle(subscription_repo):
    due = subscription_repo.get_due_for_billing(today)
```

**Why:** Lets us swap SQLite for Postgres later. Makes business logic testable without a database.

---

## 4. The ledger is **append-only**. Never UPDATE, never DELETE.

```python
# ❌ WRONG — destroys audit trail
ledger_repo.update(entry_id, amount=new_amount)
```

```python
# ✅ RIGHT — corrections are new entries
ledger_repo.add(LedgerEntry(direction=CREDIT, amount=original, reason="REVERSAL"))
ledger_repo.add(LedgerEntry(direction=DEBIT, amount=corrected, reason="CORRECTION"))
```

**Why:** Accountants and auditors require an immutable record of what happened. Your ledger should be able to reconstruct the customer's balance at any point in history.

**Enforcement:** `LedgerRepository.update()` and `.delete()` must raise `NotImplementedError`.

---

## 5. Pricing, discount, tax, and proration functions are PURE

They take inputs and return values. **No database access. No file I/O. No `datetime.now()`.**

```python
# ❌ WRONG — pricing reaches into the DB
class TieredPricing:
    def calculate(self, quantity):
        tiers = repo.load_tiers(self.plan_id)   # NO

# ✅ RIGHT — tiers are passed in at construction
class TieredPricing:
    def __init__(self, tiers): self.tiers = tiers
    def calculate(self, quantity):
        # pure computation
```

**Why:** Pure functions are trivially testable. Impure functions are flaky.

---

## 6. Tests must be deterministic

```python
# ❌ WRONG — flaky, depends on real wall clock
def test_billing():
    cycle.run(datetime.now())

# ✅ RIGHT — pass a fixed date
def test_billing():
    cycle.run(date(2026, 1, 15))
```

**Why:** A test that passes today and fails tomorrow is worse than no test.

---

## 7. Round only at the boundary

Round when:
- Displaying to the user (PDF, CLI)
- Persisting to the database

Do NOT round in the middle of a multi-step calculation. Compounding rounding errors are real.

```python
# ❌ WRONG — rounds twice, drift
subtotal = (price * qty).round()
total = (subtotal * (1 + tax_rate)).round()

# ✅ RIGHT — single rounding at the end
total = (price * qty * (1 + tax_rate)).round()
```

---

## 8. One module, one job

If `BillingCycle` is also rendering PDFs, refactor. Each class should have one reason to change.

---

## 9. Naming

| Concept | Convention |
|---|---|
| ABC class | Singular noun: `PricingStrategy`, `Discount`, `TaxCalculator` |
| Concrete subclass | Specific name: `TieredPricing`, `PercentageDiscount`, `GSTCalculator` |
| Repository | `<Entity>Repository` |
| Test file | `test_<module>.py` |
| Test function | `test_<thing>_<expected_behavior>` — e.g. `test_tiered_pricing_at_tier_boundary` |

---

## 10. Git

- Branch per feature: `feat/pricing-tiered`, `feat/dunning-fsm`
- Commit message: imperative voice, < 72 chars: `Add TieredPricing.calculate`
- No `WIP` commits to `main`. Use `git commit --amend` or squash before merging.
- **Push at the end of every day**, no exceptions.
