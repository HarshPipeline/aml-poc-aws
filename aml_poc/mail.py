"""Optional Gmail RFI. Missing SMTP_PASSWORD records the request without sending."""

import os
import smtplib
from email.message import EmailMessage

MONTHS = "January February March April May June July August September October November December".split()
REVIEW = {
    "TM-01": (
        "Cash Structuring",
        "Several cash deposits posted in a short period, each below typical currency-transaction reporting thresholds.",
    ),
    "TM-03": (
        "Rapid movement of funds",
        "Out-of-state cash was credited to the account and funds left the same account shortly afterward by check and wire.",
    ),
    "TM-07": (
        "Pass-through activity",
        "Incoming credits were followed by matched outgoing payments in a short period.",
    ),
    "TM-08": (
        "Unusual wire activity",
        "An unusual burst of international wires posted to this account.",
    ),
    "TM-09": (
        "International wires",
        "International wires posted to this account, including activity that may involve a third-party payer.",
    ),
}
ASK_POINTS = {
    ("TM-01", "letter"): [
        "who made each deposit and their relationship to the business",
        "the business source of the cash (for example register receipts versus other sources)",
        "why the funds were deposited in cash over these dates",
    ],
    ("TM-03", "letter"): [
        "the source of the out-of-state cash deposits",
        "who collected or deposited the cash and their relationship to the business",
        "how the cash relates to the supplier payments that left the account in the same period",
    ],
    ("TM-03", "check"): [
        "clear images of the outgoing checks covering payments in this period (front, or front and back)",
        "payee, date, amount and memo as they appear on each check",
    ],
    ("TM-07", "invoice"): [
        "the supplier invoice that supports each outgoing payment in this period",
        "invoice number, date, amount and the goods or services billed",
    ],
    ("TM-09", "invoice"): [
        "commercial invoices supporting the international wires in this period",
        "invoice number, date, amount and the goods billed",
    ],
    ("TM-09", "letter"): [
        "who paid, if anyone other than the named customer paid",
        "the commercial relationship that explains a third-party payer",
    ],
}


def smtp_ready():
    return bool(os.environ.get("SMTP_PASSWORD", "").strip())


def format_window(start, end):
    def parts(iso):
        year, month, day = iso[:10].split("-")
        return int(year), int(month), int(day)

    if not start or not end:
        return ""
    try:
        start_year, start_month, start_day = parts(start)
        end_year, end_month, end_day = parts(end)
    except (TypeError, ValueError):
        return ""
    if (start_year, start_month) == (end_year, end_month):
        return f"{start_day}–{end_day} {MONTHS[start_month - 1]} {start_year}"
    return (
        f"{start_day} {MONTHS[start_month - 1]} {start_year} – "
        f"{end_day} {MONTHS[end_month - 1]} {end_year}"
    )


def money(amount):
    try:
        return f"${float(amount):,.2f}"
    except (TypeError, ValueError):
        return ""


def rfi_text(customer_name, customer_id, alert_id, artifacts, alert=None, account_id="", episode_label=""):
    alert = alert or {}
    family = alert.get("family") or ""
    topic, reason = REVIEW.get(family, ("account activity", "Activity on this account is under BSA/AML review."))
    window = format_window(alert.get("window_start"), alert.get("window_end"))
    amount = money(alert.get("amount"))
    account = account_id or customer_id
    greeting = customer_name or "customer"
    period = f"the period {window}" if window else "the review period"
    subject = "Document request — " + (f"{greeting} — {window}" if window else f"{greeting} — {alert_id}")
    lines = [
        f"Dear {greeting},",
        "",
        f"We are reviewing {topic.lower()} on account {account} for {period}.",
        reason,
    ]
    if amount:
        lines.append(f"The activity in this period totals {amount}.")
    if episode_label and window:
        lines.append(f"Case reference: {episode_label}, alert {alert_id}.")
    else:
        lines.append(f"Case reference: alert {alert_id}.")
    lines += ["", "Please provide the following by reply to this message, with the files attached:", ""]
    for index, item in enumerate(artifacts or [], 1):
        kind = item.get("artifact_type") or ""
        title = item.get("title") or "Supporting document"
        lines.append(f"{index}. {title}")
        for point in ASK_POINTS.get((family, kind), []):
            lines.append(f"   - {point}")
    lines += [
        "",
        "A response covering a different period does not satisfy this request. Please reply with documents for these dates only.",
        "",
        "Financial Crimes Investigations",
        "BSA / AML Operations",
    ]
    return subject, "\n".join(lines)


def send_rfi(customer_name, customer_id, alert_id, artifacts, alert=None, account_id="", episode_label=""):
    subject, body = rfi_text(
        customer_name, customer_id, alert_id, artifacts, alert, account_id, episode_label
    )
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    if not password:
        return {
            "sent": False,
            "detail": "SMTP_PASSWORD is not set; the request is on the case only.",
            "subject": subject,
            "body": body,
        }
    user = os.environ.get("SMTP_USER", "jkanuku0305@gmail.com")
    sender = os.environ.get("SMTP_FROM", user)
    to = os.environ.get("SMTP_TO", user)
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to
    message.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(message)
    except Exception as error:  # noqa: BLE001 - RFI must still land on the case
        return {
            "sent": False,
            "detail": f"Email was not delivered ({type(error).__name__}). The request remains on the case.",
            "subject": subject,
            "body": body,
        }
    return {"sent": True, "detail": f"Email sent to {to}.", "subject": subject, "body": body}
