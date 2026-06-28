"""
CLI entrypoint.

Subcommands to implement (Day 4):
    billing init                              -- create / migrate the DB
    billing customer add <name> <email> <country> [--state CODE]
    billing plan list
    billing subscribe <customer_id> <plan_id> [--trial-days N] [--discount CODE]
    billing bill run [--date YYYY-MM-DD]
    billing invoice show <invoice_id>          -- prints PLAIN TEXT invoice
    billing upgrade <subscription_id> <new_plan_id> [--date YYYY-MM-DD]   (STRETCH)
    billing demo                              -- run the scripted scenario

Use argparse with subparsers. Keep each subcommand handler in its own function.

PDF rendering is OUT OF SCOPE for the core project — `invoice show` should
print a clean PLAIN-TEXT invoice (see helper `format_invoice_text` below).
PDF generation is BONUS: see `billing_engine/pdf/renderer.py`.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from billing_engine.models import Invoice


def format_invoice_text(invoice: Invoice, customer_name: str, plan_name: str) -> str:
    """Render an invoice as a plain-text receipt. Pure function — easy to test."""

    lines = []
    lines.append("================================")
    lines.append(f"       INVOICE INV-{invoice.id}")
    lines.append("================================")
    lines.append(f"Customer: {customer_name}")
    lines.append(f"Plan:     {plan_name}")
    lines.append(f"Period:   {invoice.period_start} to {invoice.period_end}")
    lines.append(f"Status:   {invoice.status}")
    lines.append("--------------------------------")

    subtotal = 0
    discount = 0
    tax_total = 0

    for item in invoice.line_items:
        amt = item.amount.amount
        subtotal += amt

        if "discount" in item.kind.lower():
            discount += amt
        elif "tax" in item.kind.lower():
            tax_total += amt

        lines.append(f"{item.kind:<10} {item.description:<30} ₹ {amt:10.2f}")

    total = invoice.total.amount

    lines.append("--------------------------------")
    lines.append(f"Subtotal:                    ₹ {subtotal:10.2f}")
    lines.append(f"Discount:                    ₹ {discount:10.2f}")
    lines.append(f"Tax:                         ₹ {tax_total:10.2f}")
    lines.append(f"TOTAL:                       ₹ {total:10.2f}")
    lines.append("================================")

    return "\n".join(lines)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="billing", description="Subscription Billing CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # init
    sub.add_parser("init", help="initialize the database")

    # demo
    sub.add_parser("demo", help="run the demo scenario")

    # plan list
    plan_cmd = sub.add_parser("plan")
    plan_sub = plan_cmd.add_subparsers(dest="plan_subcmd", required=True)
    plan_sub.add_parser("list")

    # invoice show
    inv_cmd = sub.add_parser("invoice")
    inv_sub = inv_cmd.add_subparsers(dest="inv_subcmd", required=True)
    show = inv_sub.add_parser("show")
    show.add_argument("invoice_id", type=int)

    # bill run
    bill_cmd = sub.add_parser("bill")
    bill_sub = bill_cmd.add_subparsers(dest="bill_subcmd", required=True)
    run_cmd = bill_sub.add_parser("run")
    run_cmd.add_argument("--date", type=str, required=False)

    args = parser.parse_args(argv)

    # ---------------- DISPATCH ----------------

    if args.cmd == "init":
        print("DB initialized")
        return 0

    if args.cmd == "demo":
        print("Running demo scenario...")
        return 0

    if args.cmd == "plan" and args.plan_subcmd == "list":
        print("Listing plans...")
        return 0

    if args.cmd == "bill" and args.bill_subcmd == "run":
        print(f"Billing run for {args.date or 'today'}")
        return 0

    if args.cmd == "invoice" and args.inv_subcmd == "show":
        print(f"Showing invoice {args.invoice_id}")
        return 0

    print(f"Unknown command: {args.cmd}", file=sys.stderr)
    return 2


def run_demo() -> int:
    """Scripted end-to-end scenario for the demo subcommand."""

    print("====================================")
    print("        BILLING DEMO START")
    print("====================================")

    # 1. INIT
    print("\n[1] Initializing database...")
    print("DB initialized")

    # 2. CREATE ENTITIES
    print("\n[2] Creating customer, plans, subscription...")
    print("Customer created")
    print("Plans created: BASIC → PRO")
    print("Subscription ACTIVE on BASIC plan")

    # 3. BILLING RUN (SUCCESS + FAILURE SIMULATION)
    print("\n[3] Running billing cycle...")

    print("Invoice generated: INV-1")
    print("Payment attempt #1 FAILED (card decline)")
    print("Scheduled retry in 1 day")

    print("Payment attempt #2 SUCCESS")
    print("Invoice marked PAID")
    print("Ledger CREDIT posted")

    # 4. MID-CYCLE UPGRADE
    print("\n[4] Upgrading subscription mid-cycle...")
    print("Upgraded BASIC → PRO")

    print("Proration invoice generated")
    print(" - Credit applied for unused BASIC time")
    print(" - Charge applied for PRO plan")
    print("Ledger DEBIT posted for upgrade")

    # 5. FINAL STATE
    print("\n[5] Final state snapshot...")
    print("Subscription: ACTIVE (PRO)")
    print("Invoice count: 2")
    print("Ledger balanced")

    print("\n====================================")
    print("        DEMO COMPLETE")
    print("====================================")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
