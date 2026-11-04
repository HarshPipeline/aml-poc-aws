"""Write matching packet files into each customer new_E folder. Does not delete old files."""

import csv
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from aml_poc.data import Dataset
from aml_poc.models import Transaction
from aml_poc.rules import DetectorEngine, total as sum_rows

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pdfs import check_png, invoice, letter_pdf, money

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT.parents[2] / "aml_demo_data_cleaned"
ONES = "zero one two three four five six seven eight nine".split()
TEENS = "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()

ISSUER_ADDR = {
    "Delta Fresh Produce Co.": ["SYNTH 18 Produce Row", "Salinas, CA 93900"],
    "Capitol City Meat and Seafood": ["SYNTH 40 Packing Ave", "Sacramento, CA 95800"],
    "Sierra Beverage Distributing": ["SYNTH 9 Warehouse Ct", "Oakland, CA 94600"],
    "Kestrel Health Partners": ["SYNTH 77 Medical Plaza", "Palo Alto, CA 94300"],
    "Alder and Finch Retail Co.": ["SYNTH 12 Market St", "San Jose, CA 95100"],
    "Northbeam Software Inc.": ["SYNTH 200 Innovation Way", "Mountain View, CA 94000"],
    "Brightwater Logistics Group": ["SYNTH 55 Harbor Blvd", "Oakland, CA 94600"],
    "Gyeonggi Display Systems Ltd.": ["SYNTH 88 Pangyo-ro", "Seongnam, Gyeonggi, Republic of Korea"],
    "Hsinchu Microlink Electronics Co.": ["SYNTH 12 Science Park Rd", "Hsinchu, Taiwan"],
    "Shenzhen Brightway Components Co. Ltd.": ["SYNTH 19 Huaqiang North", "Shenzhen, Guangdong, China"],
    "Kowloon Sunmark Trading Ltd.": ["SYNTH 8 Canton Rd", "Kowloon, Hong Kong"],
}

GOODS = {
    "Delta Fresh Produce Co.": "Produce, herbs, and kitchen vegetables",
    "Capitol City Meat and Seafood": "Protein and seafood for restaurant service",
    "Sierra Beverage Distributing": "Beverage and bar supply",
    "Kestrel Health Partners": "Implementation / professional services",
    "Alder and Finch Retail Co.": "Retail operations support",
    "Northbeam Software Inc.": "Software implementation support",
    "Brightwater Logistics Group": "Logistics consulting",
    "Gyeonggi Display Systems Ltd.": "Display panels and driver components",
    "Hsinchu Microlink Electronics Co.": "RF modules and board-level parts",
    "Shenzhen Brightway Components Co. Ltd.": "Power MOSFETs and PCB assemblies",
    "Kowloon Sunmark Trading Ltd.": "Electronic components, trading lot",
}


def words_int(n):
    n = int(n)
    if n < 10:
        return ONES[n]
    if n < 20:
        return TEENS[n - 10]
    if n < 100:
        tens, rem = divmod(n, 10)
        return TENS[tens - 2] + (f"-{ONES[rem]}" if rem else "")
    if n < 1000:
        hundreds, rem = divmod(n, 100)
        return ONES[hundreds] + " hundred" + (f" {words_int(rem)}" if rem else "")
    if n < 1_000_000:
        thousands, rem = divmod(n, 1000)
        return words_int(thousands) + " thousand" + (f" {words_int(rem)}" if rem else "")
    millions, rem = divmod(n, 1_000_000)
    return words_int(millions) + " million" + (f" {words_int(rem)}" if rem else "")


def words_usd(amount):
    cents = int((Decimal(str(amount)).quantize(Decimal("0.01")) * 100).to_integral_value())
    dollars, frac = divmod(cents, 100)
    body = words_int(dollars)
    return body[0].upper() + body[1:] + f" and {frac:02d}/100 dollars"


def pretty_date(ts):
    return ts.strftime("%d %b %Y")


def load_local():
    customers = json.loads((CLEAN / "customers.json").read_text())["customers"]
    accounts = json.loads((CLEAN / "accounts.json").read_text())["accounts"]
    counterparties = json.loads((CLEAN / "counterparties.json").read_text())["counterparties"]
    patterns = json.loads((CLEAN / "policy_patterns.json").read_text())["patterns"]
    with (CLEAN / "transactions.csv").open() as fh:
        rows = []
        for raw in csv.DictReader(fh):
            raw["cash_flag"] = raw["cash_flag"].lower() == "true"
            raw["is_round_amount"] = raw["is_round_amount"].lower() == "true"
            raw["amount"] = Decimal(raw["amount"])
            raw["txn_ts"] = datetime.fromisoformat(raw["txn_ts"])
            rows.append(Transaction.model_validate({k: v for k, v in raw.items() if v not in ("", None)}))
    return Dataset(customers, accounts, counterparties, patterns, rows)


def party(row, outgoing=True):
    if outgoing:
        return getattr(row, "beneficiary_name", "") or "Supplier"
    return getattr(row, "originator_name", "") or "Payer"


def write_amount_table(path, lines):
    path.write_text("\n".join(lines) + "\n")


def customer_invoice(folder, row, billed_to, billed_addr, extra_note=""):
    payee = party(row, outgoing=True)
    amt = float(row.amount)
    number = f"INV-{row.transaction_id[-6:]}"
    path = folder / f"INV-{payee.split()[0].upper()}-{row.transaction_id}-{int(amt)}.pdf"
    invoice(
        path,
        issuer=payee,
        issuer_addr=ISSUER_ADDR.get(payee, ["SYNTH address", "Demo jurisdiction"]),
        bill_to=billed_to,
        bill_addr=billed_addr,
        number=number,
        date=pretty_date(row.txn_ts),
        due=pretty_date(row.txn_ts),
        po=row.transaction_id,
        lines=[(GOODS.get(payee, "Commercial goods / services"), 1, amt, amt)],
        total=amt,
        notes=f"Paid on the case-file ledger as {row.transaction_id}. {extra_note}".strip(),
        payment=f"Amount USD {amt:,.2f}. Ledger {row.transaction_id}.",
    )
    return path, amt


def customer_check(folder, row, payer, payer_addr, sign):
    payee = party(row, outgoing=True)
    amt = float(row.amount)
    number = str(getattr(row, "check_number", "") or row.transaction_id[-4:])
    path = folder / f"CHK-{number}-{row.transaction_id}.png"
    check_png(
        path,
        payer=payer,
        payer_addr=payer_addr,
        number=number,
        date=pretty_date(row.txn_ts),
        payee=payee,
        amount=amt,
        words=words_usd(amt),
        memo=f"{row.transaction_id}  ·  {payee}",
        txn=row.transaction_id,
        sign=sign,
    )
    return path, amt


def build_c001(folder, alert, lookup):
    deposits = [lookup[i] for i in alert["transaction_ids"]]
    cash_total = float(sum_rows(deposits))
    listed = "; ".join(
        f"{r.transaction_id} {pretty_date(r.txn_ts)} {money(float(r.amount))}" for r in deposits
    )
    letter_pdf(
        folder / f"LTR-sof-{alert['alert_id']}.pdf",
        from_block=[
            "Sunnyvale Corner Quick Stop LLC",
            "SYNTH 100 Example St, Sunnyvale, CA 94000",
            "Marcus Delgado-Whitfield",
            "Managing Member",
        ],
        to_block=["Financial Crimes Investigations", "Demo Bank — BSA / AML Operations", f"Alert {alert['alert_id']}"],
        date="22 October 2025",
        subject=f"Source of funds for cash deposits totaling {money(cash_total)}",
        body=[
            f"This letter covers the five cash deposits on alert {alert['alert_id']} "
            f"({pretty_date(deposits[0].txn_ts)} through {pretty_date(deposits[-1].txn_ts)}). "
            f"The deposits total {money(cash_total)}.",
            f"Deposit list: {listed}. Each was made in person by me at branch SYNTH-BR-CA-001.",
            "The funds are register receipts from Sunnyvale Corner Quick Stop LLC. Card sales settle separately. "
            "I am the sole depositor and beneficial owner.",
        ],
        sign="Marcus Delgado-Whitfield<br/>Managing Member<br/>Sunnyvale Corner Quick Stop LLC",
    )
    return [
        f"Sunnyvale first cash week  {alert['alert_id']}",
        f"  Letter total  {money(cash_total)}  (matches alert cash_total {money(alert['metrics']['cash_total'])})",
        *[f"  {r.transaction_id}  {money(float(r.amount))}" for r in deposits],
        "  Later Sunnyvale cash weeks: left empty for Request documents.",
        "",
    ]


def build_c002(folder, alert, lookup, index):
    rows = [lookup[i] for i in alert["transaction_ids"]]
    cash = [r for r in rows if r.cash_flag and r.direction == "INCOMING"]
    checks = [r for r in rows if r.txn_type == "check"]
    wires = [r for r in rows if r.txn_type == "wire_out"]
    dest = folder / f"ep{index}-{alert['alert_id']}"
    dest.mkdir(parents=True, exist_ok=True)
    cash_total = float(sum_rows(cash))
    listed = "; ".join(
        f"{r.transaction_id} {pretty_date(r.txn_ts)} {r.branch_state} {money(float(r.amount))}" for r in cash
    )
    check_amt = wire_amt = 0.0
    for row in checks:
        _, amt = customer_check(
            dest,
            row,
            "Casa Brisa Kitchen Inc.",
            "SYNTH 200 Example Ave, San Jose, CA 95000  ·  ACC-C002-01",
            "E. Quintanilla-Hayes",
        )
        check_amt += amt
    for row in wires:
        _, amt = customer_invoice(
            dest,
            row,
            "Casa Brisa Kitchen Inc.",
            ["SYNTH 200 Example Ave", "San Jose, CA 95000"],
            extra_note="Restaurant supplier invoice supporting the outgoing payment.",
        )
        wire_amt += amt
    paid = check_amt + wire_amt
    letter_pdf(
        dest / f"LTR-cash-and-suppliers-{alert['alert_id']}.pdf",
        from_block=[
            "Casa Brisa Kitchen Inc.",
            "SYNTH 200 Example Ave, San Jose, CA 95000",
            "Elena Marisol Quintanilla-Hayes",
            "Owner",
        ],
        to_block=["Financial Crimes Investigations", "Demo Bank — BSA / AML Operations", f"Alert {alert['alert_id']}"],
        date=pretty_date(rows[-1].txn_ts),
        subject=f"Cash deposits {money(cash_total)} and supplier payments {money(paid)}",
        body=[
            f"This response covers alert {alert['alert_id']}. "
            f"{len(cash)} out-of-state cash deposits total {money(cash_total)} "
            f"({', '.join(alert['metrics']['states'])}): {listed}.",
            "Those deposits were collected by event contractors during a multi-state catering stretch. "
            "I am providing this letter plus the supplier checks and invoices for the payments that left the same account.",
            f"Enclosed checks total {money(check_amt)}. Enclosed supplier invoices for wires total {money(wire_amt)}. "
            f"Together they total {money(paid)} against cash of {money(cash_total)}.",
        ],
        sign="Elena Marisol Quintanilla-Hayes<br/>Owner<br/>Casa Brisa Kitchen Inc.",
    )
    return [
        f"Casa Brisa ep{index}  {alert['alert_id']}  alert amount {money(alert['amount'])}",
        f"  Cash letter  {money(cash_total)}  (metrics deposit_total {money(alert['metrics']['deposit_total'])})",
        f"  Checks       {money(check_amt)}  ({len(checks)} images)",
        f"  Wire invoices {money(wire_amt)}  ({len(wires)} PDFs)",
        f"  Payments     {money(paid)}",
        "",
    ]


def build_c003(folder, alert, lookup, index):
    rows = [lookup[i] for i in alert["transaction_ids"]]
    outgoing = [r for r in rows if r.direction == "OUTGOING"]
    dest = folder / f"ep{index}-{alert['alert_id']}"
    dest.mkdir(parents=True, exist_ok=True)
    paid = 0.0
    for row in outgoing:
        _, amt = customer_invoice(
            dest,
            row,
            "Priya Anand-Sorensen",
            ["Freelance consultant", "SYNTH 300 Example Ln", "Palo Alto, CA 94300"],
            extra_note="Invoice for the outgoing pass-through payment on this alert.",
        )
        paid += amt
    return [
        f"Priya ep{index}  {alert['alert_id']}  alert amount {money(alert['amount'])}",
        f"  Outgoing invoices {money(paid)}  (metrics outgoing_total {money(alert['metrics']['outgoing_total'])})",
        *[f"  {r.transaction_id}  {party(r)}  {money(float(r.amount))}" for r in outgoing],
        "",
    ]


def build_c004(folder, alert, lookup, index):
    rows = [lookup[i] for i in alert["transaction_ids"]]
    incoming = [r for r in rows if r.direction == "INCOMING"]
    outgoing = [r for r in rows if r.direction == "OUTGOING"]
    dest = folder / f"ep{index}-{alert['alert_id']}"
    dest.mkdir(parents=True, exist_ok=True)
    paid = 0.0
    for row in outgoing:
        _, amt = customer_invoice(
            dest,
            row,
            "Pacific Rim Circuitry Imports Inc.",
            ["SYNTH 400 Example Blvd", "Fremont, CA 94500"],
            extra_note="Commercial invoice for the international supplier wire.",
        )
        paid += amt
    in_total = float(sum_rows(incoming))
    in_list = "; ".join(
        f"{party(r, outgoing=False)} {r.transaction_id} {money(float(r.amount))} ({r.counterparty_country})"
        for r in incoming
    )
    letter_pdf(
        dest / f"LTR-third-party-{alert['alert_id']}.pdf",
        from_block=[
            "Pacific Rim Circuitry Imports Inc.",
            "SYNTH 400 Example Blvd, Fremont, CA 94500",
            "Wei-Lin Tran-Castellano",
            "President",
        ],
        to_block=["Financial Crimes Investigations", "Demo Bank — BSA / AML Operations", f"Alert {alert['alert_id']}"],
        date=pretty_date(rows[-1].txn_ts),
        subject=f"Third-party incoming wires {money(in_total)} and supplier invoices {money(paid)}",
        body=[
            f"This letter and the enclosed invoices respond to alert {alert['alert_id']}. "
            f"Incoming third-party wires total {money(in_total)}: {in_list}.",
            f"The enclosed supplier invoices total {money(paid)} and match the outgoing international wires on this alert. "
            f"Incoming {money(in_total)} plus outgoing {money(paid)} equals the alert amount {money(alert['amount'])}.",
            "The incoming payers are not manufacturers. They asked to prepay Asian supplier invoices that we then settled by wire. "
            "This letter does not certify that the activity is legitimate.",
        ],
        sign="Wei-Lin Tran-Castellano<br/>President<br/>Pacific Rim Circuitry Imports Inc.",
    )
    return [
        f"Pacific Rim ep{index}  {alert['alert_id']}  alert amount {money(alert['amount'])}",
        f"  Incoming letter {money(in_total)}",
        f"  Supplier invoices {money(paid)}  ({len(outgoing)} PDFs)",
        f"  Incoming + outgoing {money(in_total + paid)}",
        "",
    ]


def build():
    data = load_local()
    engine = DetectorEngine(data)
    as_of = data.transactions[-1].txn_ts
    lookup = {r.transaction_id: r for r in data.transactions}
    summary = [
        "New evidence in new_E only. Original files were not changed.",
        "C005 and later Sunnyvale cash weeks stay empty for Request documents.",
        "",
    ]
    builders = {
        "C001": ("TM-01", True, build_c001),
        "C002": ("TM-03", False, build_c002),
        "C003": ("TM-07", False, build_c003),
        "C004": ("TM-09", False, build_c004),
    }
    for cid, (family, first_only, fn) in builders.items():
        folder = ROOT / cid / "new_E"
        folder.mkdir(parents=True, exist_ok=True)
        rows = [r for r in data.transactions if r.customer_id == cid]
        alerts = [a for a in engine.detect(cid, rows, as_of) if a["family"] == family]
        alerts = sorted(alerts, key=lambda a: a["window_start"])
        chosen = alerts[:1] if first_only else alerts
        lines = [f"{cid}  {folder.relative_to(ROOT)}"]
        for index, alert in enumerate(chosen, 1):
            if first_only:
                lines += fn(folder, alert, lookup)
            else:
                lines += fn(folder, alert, lookup, index)
        write_amount_table(folder / "AMOUNTS.txt", lines)
        summary += lines
    write_amount_table(ROOT / "new_E_AMOUNTS.txt", summary)
    print("\n".join(summary))


if __name__ == "__main__":
    build()
