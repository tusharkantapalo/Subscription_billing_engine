# Instructor Guide — Subscription Billing Engine Capstone

A day-by-day script for how to introduce, monitor, and review the project with each intern.

**Audience:** You (the instructor / mentor).
**Project length:** 4 days (~6–7 working hours/day).
**Format:** Individual intern, TDD-driven. Skeleton + complete test suite is provided; the intern writes code to make the tests pass.

---

## Before Day 0 — Your prep checklist

- [ ] Verify the starter runs from the repository root: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" && cd billing_engine_starter && pytest -q`
  Expected: ~20 tests pass (Money), ~80+ tests fail with `NotImplementedError`. **This is the correct starting state.**
- [ ] Read [DAY1_TASKS.md](DAY1_TASKS.md), [DAY2_TASKS.md](DAY2_TASKS.md), [DAY3_TASKS.md](DAY3_TASKS.md), and [DAY4_TASKS.md](DAY4_TASKS.md) end-to-end yourself.
- [ ] Walk through `billing_engine/money.py` so you can answer questions about `Decimal` and banker's rounding.
- [ ] Open `db/schema.sql` and trace the FKs by hand — students will ask "why this table".
- [ ] Decide which BONUS items you'll mention (PDF rendering is the obvious one).

---

## Day 0 — Kickoff (30–45 minutes, the evening before Day 1)

### Why we picked this project (5 min)
> *"Every SaaS company has a billing system. It looks simple from outside ('charge once a month') but inside it's the messiest code in the company — money, dates, taxes, retries, idempotency, audit. If you can build one, you can build almost anything."*

### Demo what they'll build (10 min)
Run the end-to-end demo test (uncomment the skip):
```bash
pytest tests/test_demo_scenario.py -v
```
Then show: "By Day 4 evening, this test will pass. That's the deliverable."

### Show the structure (10 min)
- Open `billing_engine/` in the tree and walk top-down: `money` → `models` → `db` → `pricing/discounts/taxes` → `billing` → `payments` → `cli`.
- Emphasize: **"Read tests/ first every morning. The tests are the spec."**

### Set the ground rules (10 min)
1. **TDD loop:** read a test → run it (red) → write code → run it (green) → next.
2. **Never use `float` for money.** The `Money` class will refuse it at construction.
3. **Never use `datetime.now()` in tests.** Pass dates in.
4. **Commit at every green test.** `git commit -am "green: TestX::test_y"`.
5. **Stuck for >30 min?** Skip that test (`@pytest.mark.skip(reason="...")`) and move on. Come back later. See the "drop-order" section at the bottom of each day's file.

### Hand them the files (5 min)
- README.md
- DAY1_TASKS.md, DAY2_TASKS.md, DAY3_TASKS.md, DAY4_TASKS.md
- Mention BONUS sections briefly (PDF, advanced FSM)

### Vocabulary and diagrams to explain early (10 min)
Use these terms consistently from Day 0 so students do not get blocked by naming.

- **Freemium**: A pricing model where usage up to a free quota costs zero, and only overage is billed. In this project, `Freemium` wraps another strategy and delegates pricing for units above `free_quota`.
- **ER diagram (Entity-Relationship diagram)**: A picture of tables and their relationships. Emphasize that boxes are tables, fields like `customer_id` are foreign keys, and crow's-foot ends indicate one-to-many relationships.
- **E2E flow (end-to-end flow)**: A full business journey from input to final state. Here it means signup/trial, invoice generation, ledger posting, payment attempt, retries/failure handling, and plan upgrade/proration, all in one coherent scenario.

When you explain the ER diagram, anchor it to these three stories:
1. A customer owns subscriptions.
2. A subscription produces invoices.
3. An invoice produces ledger entries and payment attempts.

When you explain the E2E flow, anchor it to system boundaries:
1. Domain logic computes prices, discounts, and taxes.
2. Repositories persist invoices, line items, ledger entries, and attempts.
3. Workflow classes orchestrate retries and upgrades.

---

## Day 1 — Pure Python: money, pricing, discounts, taxes

### Morning standup script (10 min)
> *"Today is pure Python. No database, no HTTP, no PDFs. You will build the math engine — money arithmetic, pricing strategies, discounts, taxes. By end of day, you can compute the total of an invoice in your REPL."*

### Walkthrough (20 min)
Open these files in order with the student and READ them — do not write code yet:
1. `billing_engine/money.py` — point out `_quantize` (banker's rounding), float rejection, currency-mismatch errors.
2. `billing_engine/models/` — frozen dataclasses; show how `Plan` ties to `PricingType` enum.
3. `billing_engine/pricing/base.py` — the `PricingStrategy` ABC. Then open `flat.py`, `usage.py`, `tiered.py`, `freemium.py` skeletons.
4. `billing_engine/discounts/base.py` and `billing_engine/taxes/base.py`.
5. `tests/test_pricing.py` — show this is their spec for the day.

### What they implement (rest of Day 1)
~10 TODO bodies across:
- `pricing/flat.py`, `pricing/usage.py`, `pricing/tiered.py`, `pricing/freemium.py`
- `discounts/percentage.py`, `discounts/fixed.py`, `discounts/first_month_free.py`
- `taxes/no_tax.py`, `taxes/vat.py`, `taxes/gst.py`

### Check-ins
- **11:00** — "Has FlatRate gone green?"
- **14:00** — "Are all pricing tests green? If not, what's blocking?"
- **16:30** — "How many tests are red?" Run `pytest tests/test_pricing.py tests/test_discounts.py tests/test_taxes.py -q`.

### End-of-day demo (15 min)
Have them open `python` and type:
```python
from decimal import Decimal
from billing_engine.money import Money
from billing_engine.pricing import FlatRate
from billing_engine.discounts import PercentageDiscount
from billing_engine.taxes import GSTCalculator, TaxContext

price = FlatRate(Money("1000", "INR")).calculate(0)         # 1000
after_discount = PercentageDiscount(Decimal("0.10")).apply(price)  # 900
gst = GSTCalculator(Decimal("0.09"), Decimal("0.09"), Decimal("0.18"))
gst.apply(after_discount, TaxContext("IN", "MH", "MH")).total      # 162
```
This is the **"you built a calculator"** moment. Celebrate it.

### Common Day-1 mistakes to watch for
- Using `*` between a `Money` and a `float` — Money will raise. Tell them to use `Decimal("0.10")` not `0.10`.
- Trying to call `.amount` on the discount result and getting confused. Discount returns a `Money`.
- Returning a different currency from `TieredPricing.calculate(units)` than the tier prices were in. Currency must be threaded through.
- Forgetting to handle `units=0` in tiered.

### Drop-order if behind
1. Skip Freemium (one strategy).
2. Skip GST entirely (just VAT + NoTax). Mark `test_taxes.py::TestGSTCalculator` skipped.

---

## Day 2 — Persistence: SQLite, repositories, invoice pipeline

### Morning standup script (10 min)
> *"Yesterday you had numbers. Today you give them memory. We use raw SQLite — no ORM. By tonight, students should have working repositories and a pure invoice-building pipeline."*

### Walkthrough (30 min)
1. Open `db/schema.sql` in DBeaver / VS Code. Walk through every table. Highlight:
   - `invoices` has `UNIQUE(subscription_id, period_start)` — **this is what makes us idempotent**. Re-running the same billing cycle CANNOT create a duplicate invoice.
   - `ledger_entries` has no UPDATE/DELETE method by design — append-only audit log.
   - All `amount` columns are `TEXT` (we store Decimal strings, never floats).
2. Open `db/database.py` and explain `BEGIN IMMEDIATE` in `.transaction()`.
3. Open `db/repository.py` and pick ONE method (e.g. `CustomerRepository.add`) to do live together. Show how to convert dataclass→row and row→dataclass.
4. Open `billing/pipeline.py` and read `build_invoice` together. **This is a pure function.** No DB. They will write it.
5. Open `billing/cycle.py` and read the `run()` docstring. Tell them they will implement it tomorrow, not race through it today.

### What they implement
- All core repositories in `db/repository.py`; leave `PaymentAttemptRepository` for Day 3 unless they finish early.
- `billing/pipeline.py::build_invoice`.
- They read `billing/cycle.py::BillingCycle.run` and understand the flow for Day 3.

### Check-ins
- **10:00** — `CustomerRepository` green? They need this to debug anything else.
- **12:30** — "How many repositories green? At least 6 expected before lunch."
- **15:00** — `test_pipeline.py` — all green? If not, walk through ONE failing case with them.
- **17:00** — Ask them to explain `BillingCycle.run` and the idempotency constraint before they leave.

### Common Day-2 mistakes to watch for
- Forgetting `currency` when reading back amounts from DB rows. Money columns are TEXT — they need to pair `amount_str` + `plan.currency`.
- Catching `sqlite3.IntegrityError` too broadly — they should only treat it as "duplicate" when it's specifically the UNIQUE constraint.
- Writing the period advance OUTSIDE the transaction → if anything fails after, you end up with an invoice but no period advance, and the next run re-bills the same period.
- Using `+ timedelta(days=30)` for monthly rollover — wrong. Use `start.replace(month=...)` with year rollover.

### Drop-order if behind
1. Leave `PaymentAttemptRepository` for Day 3.
2. Skip `count_for_subscription` and the related test.
3. Leave `BillingCycle.run` untouched and start it fresh on Day 3.

---

## Day 3 — Billing-cycle integration and payment groundwork

### Morning standup script (10 min)
> *"You have the math and the storage. Today you connect them into the core recurring-billing loop, then you finish the payment groundwork so tomorrow can focus on workflows rather than plumbing."*

### Walkthrough (20 min)
1. `billing/cycle.py` — read `run()` top to bottom. Make them narrate each dependency.
2. `billing/pipeline.py` — remind them this part is pure and already tested.
3. `db/schema.sql` — point again to `UNIQUE(subscription_id, period_start)`.
4. `tests/test_billing_cycle.py` — this is the full spec for the day.

### What they implement
- `billing/cycle.py::BillingCycle.run`.
- Any small supporting repo methods still missing for the trial scan or period updates.
- The transaction-wrapped persistence flow for invoices, line items, ledger, and period advancement.
- `payments/gateway.py` concrete mocks.
- `PaymentAttemptRepository` methods.

### Check-ins
- **11:00** — Are trial promotions and due-subscription lookup working?
- **14:00** — Is `build_invoice(...)` being used correctly from `run()`?
- **16:00** — Does the second billing-cycle run skip duplicates instead of creating another invoice?
- **17:30** — `test_billing_cycle.py` should be green, and `ScriptedGateway` should be done.

### Bonus picks for fast students
- Finish all of the Day 3 payment groundwork.
- Add one extra integration script that runs two billing periods in a row.
- Start reading `test_dunning.py` before leaving.

### Common Day-3 mistakes to watch for
- Writing the period advance outside the transaction.
- Catching `sqlite3.IntegrityError` too broadly.
- Forgetting the ledger DEBIT when an invoice is created.
- Using `+ timedelta(days=30)` for monthly rollover instead of the provided helper.

### Drop-order if behind
1. Skip trial activation first.
2. Ship the happy path first.
3. Add idempotency before the end of the day even if other edge cases remain.

---

## Day 4 — Dunning, proration, and CLI demo

### Morning standup script (10 min)
> *"You now have a billing engine and the payment plumbing. Today you make it survive the real world: retries, failed payments, mid-cycle plan changes, and a CLI a human can use."*

### Walkthrough (20 min)
1. `billing/dunning.py` — the retry state machine.
2. `billing/proration.py` — the day-count formula for upgrades.
3. `billing/cycle.py::upgrade_subscription` — connect proration to persisted workflow.
4. `cli.py` — show the docstring listing the commands.

### What they implement
- `billing/dunning.py::DunningProcess.attempt` and `should_cancel`.
- `billing/proration.py::compute_proration`.
- `billing/cycle.py::upgrade_subscription`.
- `cli.py::format_invoice_text`, `main`, and `run_demo`.

### Check-ins
- **11:00** — Is `test_dunning.py::test_first_attempt_success` green?
- **14:00** — Are FSM tests green, especially retry scheduling and final failure?
- **16:00** — Does `billing demo` produce sensible output?
- **17:30** — Does `test_demo_scenario.py` pass? If yes, the capstone is complete.

### Common Day-4 mistakes to watch for
- ScriptedGateway not raising `IndexError` when exhausted.
- Confusing attempt number with list index.
- Forgetting to mark a subscription `PAST_DUE` after the final failure.
- Calling `datetime.now()` inside retry logic instead of using the passed-in `now`.
- Implementing CLI output without reading the expected demo flow first.

### Drop-order if behind
1. Skip proration entirely.
2. Skip dunning retry math and implement single-attempt payments.
3. Skip CLI subcommands beyond `init` and `demo`.
4. Leave the full demo test skipped if necessary.

---

## End-of-project review (45 min)

### Code walkthrough (intern leads, 20 min)
Ask them to open and walk you through, in this order:
1. `money.py` — "What problem does Money solve?"
2. `db/schema.sql` — "Why is `ledger_entries` append-only?"
3. `billing/pipeline.py` — "Why is this a pure function?"
4. `billing/cycle.py::run` — "Walk me through what happens when we bill a customer."
5. `billing/dunning.py` — "What state is a customer in after 2 failed retries?"

### Test the failure modes (10 min)
- Run `pytest -q`. Count green vs red.
- Pick one skipped test (if any) and ask them to explain WHY it's skipped.

### Reflection questions (15 min)
1. What was the hardest bug you fixed?
2. If you had one more iteration, what would you build first?
3. Pick one place where you'd refactor your code if this were going to production.
4. What's one thing about `Decimal` you didn't know before?
5. If your boss said "we need to add cryptocurrency support" — what changes?

### Grading rubric (out of 100)

| Category | Points | Criteria |
|---|---|---|
| Day-1 tests passing | 20 | All `test_pricing`, `test_discounts`, `test_taxes` green (minus allowed drops) |
| Day-2 tests passing | 20 | All `test_repositories` and `test_pipeline` green |
| Day-3 tests passing | 20 | `test_billing_cycle` green; idempotency is the critical one |
| Day-4 tests passing | 15 | `test_dunning`, `test_proration`, and `test_demo_scenario` green or reasonably scoped drops explained |
| Code quality | 10 | No floats anywhere; transactions used correctly; no `print` debugging left behind |
| Git hygiene | 5 | Commits at green tests; meaningful commit messages |
| Walkthrough | 10 | Can explain their code without reading it line-by-line |
| Bonus | +10 | PDF renderer, proration, or any other Bonus complete |

**Pass mark: 60.** Below 50 → recommend a 1-day follow-up focused on the weak area.

---

## Quick-reference: common student questions and your answers

> **Q: Why can't I just use float?**
> A: Try `0.1 + 0.2` in Python. You get `0.30000000000000004`. Now imagine that being a billing error across 10 million invoices.

> **Q: Why SQLite and not Postgres?**
> A: Same SQL, zero setup. Real systems use Postgres; the patterns transfer.

> **Q: Why no ORM?**
> A: ORMs hide SQL. You can't debug what you can't see. Once you've written raw SQL, ORMs feel like a convenience — start them on the opposite side.

> **Q: Why is the ledger append-only?**
> A: Auditability. If you can DELETE a ledger row, you have no audit trail. This is a real banking rule (and it makes regulators happy).

> **Q: My idempotency test fails — the DB lets duplicates through?**
> A: Check `schema.sql`. Did you forget the `UNIQUE(subscription_id, period_start)` constraint? Re-init the DB after fixing.

> **Q: My month-end test fails on Feb 28?**
> A: You're probably using `+ timedelta(days=30)`. Use `start.replace(month=next_month)` with year rollover. See `_next_period_end` example in DAY2_TASKS.md.

> **Q: Should I implement the PDF?**
> A: Only if everything else is green. It's a learning bonus, not a deliverable.
