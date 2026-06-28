# Day 1 — The Math: Money, Pricing, Discounts, Taxes

> **Goal by end of Day 1:** All tests in `test_money.py`, `test_pricing.py`, `test_discounts.py`, and `test_taxes.py` are green. You should be able to run `pytest tests/test_money.py tests/test_pricing.py tests/test_discounts.py tests/test_taxes.py -v` and see ALL passing.

Today is **pure Python with no database**. You will learn:
- Why `Decimal` matters for money
- The Strategy pattern using `abc.ABC` and `@abstractmethod`
- Composition (Freemium wraps another strategy)
- Reading and implementing against real `pytest` tests
- How a small, well-tested foundation makes everything else easier

You will NOT touch SQLite, files, or the network today.

---

## Step 1 — Setup
From the repository root, run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cd billing_engine_starter
pytest -v
```
You should see **20 passing tests** (all in `test_money.py`) and many failures elsewhere. That is expected — the failing tests are your TODO list.

## Step 2 — Read what you've been given
Read these files **in order**, top to bottom. Do not skim:

1. [../README.md](../README.md) — high level
2. [CONVENTIONS.md](CONVENTIONS.md) — the non-negotiable rules
3. `billing_engine/money.py` — fully implemented Money class
4. `tests/test_money.py` — the gold-standard test file. Use this to learn how to read test intent before you implement code.
5. `billing_engine/pricing/base.py` — the ABC you must implement
6. `billing_engine/discounts/base.py` — same
7. `billing_engine/taxes/base.py` — same

If you don't understand `Decimal`, stop and read the [official tutorial](https://docs.python.org/3/library/decimal.html) and try this in a REPL:
```python
>>> 0.1 + 0.2
0.30000000000000004
>>> from decimal import Decimal
>>> Decimal("0.1") + Decimal("0.2")
Decimal('0.3')
```
That single difference is why this whole project exists.

## Step 3 — Find every TODO
```bash
grep -rn "TODO Day 1" billing_engine/
```
That is your worklist for the day. There are ~10 TODOs.

---

## Step 4 — Pricing strategies

Files: `billing_engine/pricing/{flat,usage,tiered,freemium}.py`

**4a. `FlatRate` (10 min)**
- Validate that `amount` is a `Money` instance (use `isinstance(amount, Money)` — this is the one allowed `isinstance` check; see CONVENTIONS.md rule 2).
- Validate amount is not negative (`amount.is_negative()` is False).
- Store it on `self`.
- `calculate(quantity)`: ignore `quantity` and return `self.amount`.

**4b. `UsageBased` (10 min)**
- Validate `unit_price` is non-negative Money.
- `calculate(quantity)`: reject negative quantity with `ValueError`. Return `self.unit_price * quantity`.

**4c. `TieredPricing`** — this is the hardest of the four
- In `__init__`:
  - Reject empty tier list.
  - Walk through tiers: check `tiers[i+1].from_units == tiers[i].to_units` (contiguous).
  - Check that only the last tier has `to_units is None`.
  - Check every `unit_price` shares the same currency.
- In `calculate(quantity)`:
  - Reject negative quantity.
  - Use the currency of the first tier's unit_price.
  - Start total at `Money.zero(currency)`.
  - For each tier, figure out how many of `quantity` units fall inside that tier.
    - For the open-ended top tier (`to_units is None`), include everything from `from_units` onward.
    - For bounded tiers, count `min(quantity, to_units) - from_units` if `quantity > from_units`, else 0.
  - Multiply that count by the tier's `unit_price` and add to total.
- Run `pytest tests/test_pricing.py::TestTieredPricing -v` until all green.

**4d. `Freemium`**
- In `__init__`: validate `free_quota >= 0`, validate `overage_strategy` is a `PricingStrategy`, store both.
- In `calculate(quantity)`:
  - Get the inner currency by calling `self.overage_strategy.calculate(0).currency`.
  - If `quantity <= self.free_quota`: return `Money.zero(currency)`.
  - Else: return `self.overage_strategy.calculate(quantity - self.free_quota)`.

**Checkpoint:** `pytest tests/test_pricing.py -v` → all green.

## Step 5 — Discounts

Files: `billing_engine/discounts/{percentage,fixed,first_month_free}.py`

**5a. `PercentageDiscount`**
- `__init__(percentage: Decimal)`:
  - Reject `float` (use `isinstance(percentage, float)` → `TypeError`).
  - Require Decimal in `[0, 1]`.
- `apply(subtotal, context)`: return `subtotal * self.percentage`. (No need to cap — the result is naturally ≤ subtotal because percentage ≤ 1.)

**5b. `FixedAmountDiscount`**
- `__init__(amount: Money)`: validate Money, non-negative.
- `apply(subtotal, context)`: check `amount.currency == subtotal.currency` (else `ValueError`). Return `min(self.amount, subtotal)` — Money supports `<`, so this works.

**5c. `FirstMonthFree`**
- No `__init__` needed (no fields).
- `apply(subtotal, context)`: if `context.invoice_count_so_far == 0`, return `subtotal`. Else return `Money.zero(subtotal.currency)`.

**Checkpoint:** `pytest tests/test_discounts.py -v` → all green.

## Step 6 — Taxes

Files: `billing_engine/taxes/{no_tax,vat,gst}.py`

**6a. `NoTax`**
- `apply(taxable, context)`: return `TaxBreakdown(components=[], total=Money.zero(taxable.currency))`.

**6b. `VATCalculator`**
- `__init__(rate: Decimal)`: reject float, require Decimal in `[0, 1]`, store.
- `apply(taxable, context)`:
  - `vat = taxable * self.rate`
  - Format the rate: `pct = self.rate * 100`. `label = f"VAT {pct}%"` (use Decimal formatting; you can do `f"VAT {self.rate * 100}%"`).
  - Return `TaxBreakdown(components=[(label, vat)], total=vat)`.

**6c. `GSTCalculator`**
- `__init__`: each rate is Decimal in `[0, 1]`. `cgst + sgst == igst` (raise ValueError otherwise — sanity check on real GST setup).
- `apply(taxable, context)`:
  - `intra = bool(context.customer_state) and context.customer_state == context.seller_state`
  - If intra:
    ```python
    cgst_amt = taxable * self.cgst
    sgst_amt = taxable * self.sgst
    components = [(f"CGST {self.cgst*100}%", cgst_amt), (f"SGST {self.sgst*100}%", sgst_amt)]
    total = cgst_amt + sgst_amt
    ```
  - Else:
    ```python
    igst_amt = taxable * self.igst
    components = [(f"IGST {self.igst*100}%", igst_amt)]
    total = igst_amt
    ```
  - Return `TaxBreakdown(components, total)`.

**Checkpoint:** `pytest tests/test_taxes.py -v` → all green.

---

## End-of-Day Demo

In a Python REPL:
```python
from decimal import Decimal
from billing_engine.money import Money
from billing_engine.pricing import FlatRate, TieredPricing, Tier, UsageBased, Freemium
from billing_engine.discounts import PercentageDiscount, DiscountContext
from billing_engine.taxes import GSTCalculator, TaxContext

# Flat plan
flat = FlatRate(Money("999", "INR"))
print(flat.calculate(0))           # INR 999.00

# Tiered
tiers = TieredPricing([
    Tier(0, 1000, Money("2.00", "INR")),
    Tier(1000, None, Money("1.50", "INR")),
])
print(tiers.calculate(2000))        # INR 3500.00

# Discount + tax
base = flat.calculate(0)
disc = PercentageDiscount(Decimal("0.50")).apply(base, DiscountContext(0))
taxable = base - disc
gst = GSTCalculator(Decimal("0.09"), Decimal("0.09"), Decimal("0.18"))
ctx = TaxContext("IN", "MH", "MH")
print(gst.apply(taxable, ctx).total)  # INR 89.91
```

If those numbers match, you have shipped Day 1.

---

## Done-for-the-day checklist
- [ ] All 4 pricing strategies implemented
- [ ] All 3 discounts implemented
- [ ] All 3 tax calculators implemented
- [ ] `pytest tests/test_money.py tests/test_pricing.py tests/test_discounts.py tests/test_taxes.py -v` shows ≥ 60 passing tests, 0 failing
- [ ] You can explain *out loud* what `Decimal("0.1") + Decimal("0.2")` returns and why
- [ ] You can explain why `isinstance(strategy, FlatRate)` is forbidden
- [ ] Code committed and pushed

## If you finish early
- Read tomorrow's tasks ([DAY2_TASKS.md](DAY2_TASKS.md)).
- Skim `billing_engine/db/schema.sql` and try to draw the ER diagram on paper.
- Read the [SQLBolt](https://sqlbolt.com) lessons 1–9 if SQL feels rusty.

## If you fall behind
Skip in this order; do **not** skip the test suite:
1. Skip `Freemium` — it's the most complex pricing strategy. (Tests for it will fail; that's OK if you're behind.)
2. Skip `GSTCalculator` — keep `NoTax` and `VATCalculator`.

Shipping a complete `FlatRate` + `UsageBased` + all discounts + `NoTax` + `VATCalculator` with green tests is a **passing Day 1**.
