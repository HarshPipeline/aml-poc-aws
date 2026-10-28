"""Customer document packets for the demo: seeded submissions and RFI asks.

Policy evidence_required is the BSA question. artifact_type is what the customer sends
(letter, invoice, or check). Seeded files are treated as already received from the customer.
"""

import hashlib
import re
from pathlib import Path

from .config import ROOT
from .documents import pdf_text
from .models import EvidenceDocument

EVIDENCE_ROOT = Path(__file__).resolve().parent / "fixtures" / "evidence"
TXN_IN_NAME = re.compile(r"(TXN-\d+)")
SEEDED_CUSTOMERS = ("C001", "C002", "C003", "C004")


def _file(relative, artifact_type, title, transcription=None):
    return {
        "relative": relative,
        "artifact_type": artifact_type,
        "title": title,
        "transcription": transcription,
    }


def _kind(path):
    name = path.name.upper()
    if name.startswith("CHK") or path.suffix.lower() == ".png":
        return "check"
    if name.startswith("LTR"):
        return "letter"
    return "invoice"


def _packet_files(customer_id, pattern):
    files = []
    for path in sorted((EVIDENCE_ROOT / customer_id).glob(pattern)):
        if path.suffix.lower() not in {".pdf", ".png"}:
            continue
        relative = path.relative_to(EVIDENCE_ROOT).as_posix()
        files.append(_file(relative, _kind(path), path.stem.replace("-", " ")))
    if not files:
        raise FileNotFoundError(f"Missing new_E packet files: {customer_id}/{pattern}")
    return files


SEEDED = (
    {
        "customer_id": "C001",
        "family": "TM-01",
        "slot": "first",
        "files": _packet_files("C001", "new_E/*.pdf"),
    },
    {
        "customer_id": "C002",
        "family": "TM-03",
        "slot": 1,
        "files": _packet_files("C002", "new_E/ep1-*/*"),
    },
    {
        "customer_id": "C002",
        "family": "TM-03",
        "slot": 2,
        "files": _packet_files("C002", "new_E/ep2-*/*"),
    },
    {
        "customer_id": "C003",
        "family": "TM-07",
        "slot": "first",
        "files": _packet_files("C003", "new_E/ep1-*/*"),
    },
    {
        "customer_id": "C004",
        "family": "TM-09",
        "slot": "first",
        "files": _packet_files("C004", "new_E/ep1-*/*"),
    },
)

DEFAULT_ASKS = {
    "TM-01": [
        {
            "artifact_type": "letter",
            "title": "Signed source-of-funds letter covering the cash deposits in this review period",
        }
    ],
    "TM-03": [
        {
            "artifact_type": "letter",
            "title": "Signed explanation covering the out-of-state cash deposits",
        },
        {
            "artifact_type": "check",
            "title": "Images of the outgoing checks for the rapid outflows",
        },
    ],
    "TM-07": [
        {
            "artifact_type": "invoice",
            "title": "Supplier invoice supporting the matched outgoing payment",
        }
    ],
    "TM-09": [
        {"artifact_type": "invoice", "title": "Commercial invoices for the international wires"},
        {"artifact_type": "letter", "title": "Written explanation of any third-party payer"},
    ],
}


def episode_view(alert, alerts, asks=None):
    """Queue/review labels. Safe to drop if the episode UI is reverted."""
    siblings = _active(alerts, alert["customer_id"], alert["family"])
    count = len(siblings) or 1
    index = next((i for i, row in enumerate(siblings, 1) if row["alert_id"] == alert["alert_id"]), 1)
    asks = asks or []
    if asks and all(item["status"] == "received" for item in asks):
        documents = "received"
    elif any(item["status"] == "requested" for item in asks):
        documents = "requested"
    else:
        documents = "missing"
    return {
        "episode_index": index,
        "episode_count": count,
        "episode_label": f"Episode {index} of {count}",
        "documents_status": documents,
    }


def _active(alerts, customer_id, family):
    rows = [
        a
        for a in alerts
        if a["customer_id"] == customer_id
        and a["family"] == family
        and a.get("signal_status") != "withdrawn"
    ]
    return sorted(rows, key=lambda a: (a.get("window_start") or "", a["alert_id"]))


def _slot_index(packet):
    slot = packet.get("slot")
    if slot in {"first", 1}:
        return 1
    if isinstance(slot, int):
        return slot
    return None


def packet_for_alert(alert, alerts):
    customer_id, family = alert["customer_id"], alert["family"]
    for packet in SEEDED:
        if packet["customer_id"] != customer_id or packet["family"] != family:
            continue
        siblings = _active(alerts, customer_id, family)
        index = _slot_index(packet)
        if index is not None:
            if 1 <= index <= len(siblings) and siblings[index - 1]["alert_id"] == alert["alert_id"]:
                return packet
            continue
        return packet
    return None


def asks_for_alert(alert, alerts):
    packet = packet_for_alert(alert, alerts)
    if packet:
        seen = []
        asks = []
        for item in packet["files"]:
            if item["artifact_type"] in seen:
                continue
            seen.append(item["artifact_type"])
            asks.append({"artifact_type": item["artifact_type"], "title": item["title"]})
        return asks
    return list(DEFAULT_ASKS.get(alert["family"], DEFAULT_ASKS.get(alert["pattern_ids"][0] if alert.get("pattern_ids") else "", [])))


def _docs_for_alert(store, alert):
    docs = store.documents(alert["customer_id"])
    wanted = set(alert.get("transaction_ids") or [])
    return [
        doc
        for doc in docs
        if not doc.get("transaction_ids") or set(doc["transaction_ids"]).intersection(wanted)
    ]


def customer_ask(alert, alerts, store):
    docs = _docs_for_alert(store, alert)
    received = {doc.get("artifact_type") for doc in docs if doc.get("artifact_type")}
    requested = bool(store.requests_for_alert(alert["alert_id"]))
    asks = []
    for item in asks_for_alert(alert, alerts):
        if item["artifact_type"] in received:
            status = "received"
        elif requested:
            status = "requested"
        else:
            status = "missing"
        asks.append({**item, "status": status})
    return asks


def _stable_id(relative):
    stem = Path(relative).stem.replace(".", "-")
    return "CUST-" + "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem)[:40]


def _wanted_ids():
    return {_stable_id(item["relative"]) for packet in SEEDED for item in packet["files"]}


def _txn_for_item(store, item):
    found = TXN_IN_NAME.search(Path(item["relative"]).name)
    return store.transaction(found.group(1)) if found else None


def _item_title(item, txn):
    name = Path(item["relative"]).name.upper()
    if name.startswith("LTR-SOF"):
        return "Source-of-funds letter covering the first cash-deposit week"
    if name.startswith("LTR-CASH"):
        return "Letter covering out-of-state cash deposits and supplier payments"
    if name.startswith("LTR-THIRD"):
        return "Letter — third-party payer Crescent Meridian FZE"
    if txn and item["artifact_type"] == "check":
        number = str(getattr(txn, "check_number", "") or txn.transaction_id[-4:])
        payee = getattr(txn, "beneficiary_name", None) or "Payee"
        return f"Check {number} — {payee} ${float(txn.amount):,.2f}"
    if txn and item["artifact_type"] == "invoice":
        payee = getattr(txn, "beneficiary_name", None) or "Supplier"
        return f"Invoice — {payee} ${float(txn.amount):,.2f}"
    return item["title"]


def _check_from_txn(txn):
    number = str(getattr(txn, "check_number", "") or txn.transaction_id[-4:])
    payee = getattr(txn, "beneficiary_name", None) or "Payee"
    amount = float(txn.amount)
    date = txn.txn_ts.strftime("%d %b %Y")
    text = (
        "CASA BRISA KITCHEN INC.\n"
        "SYNTH 200 Example Ave, San Jose, CA 95000  ·  ACC-C002-01\n"
        f"CHECK NUMBER {number}\n"
        f"DATE {date}\n"
        f"PAY TO THE ORDER OF {payee}\n"
        f"AMOUNT ${amount:,.2f}\n"
        f"MEMO {txn.transaction_id}  ·  {payee}\n"
        "SIGNED E. Quintanilla-Hayes\n"
    )
    fields = {
        "check_number": number,
        "payee": payee,
        "amount": f"{amount:.2f}",
        "payer": "Casa Brisa Kitchen Inc.",
    }
    return text, fields


def _read_packet_file(item, txn=None):
    path = EVIDENCE_ROOT / item["relative"]
    if not path.is_file():
        path = ROOT / "aml_poc" / "fixtures" / "evidence" / item["relative"]
    if not path.is_file():
        raise FileNotFoundError(f"Customer evidence fixture missing: {item['relative']}")
    content = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text, readable, confidence = pdf_text(content)
        origin = "pdf_text"
        fields = {}
    elif suffix == ".png":
        text = (item.get("transcription") or "").strip()
        fields = {}
        if not text:
            if txn is None:
                raise ValueError(f"PNG fixture {item['relative']} needs a transcription for seeding")
            text, fields = _check_from_txn(txn)
        readable, confidence, origin = True, 1.0, "customer_supplied"
    else:
        raise ValueError(f"Unsupported fixture type: {path.suffix}")
    return text, readable, confidence, origin, fields, hashlib.sha256(content).hexdigest()


def _drop_runtime_copy(document):
    from .files import RUNTIME, _suffix

    document_id = document.get("document_id", "")
    names = {document.get("file_name") or "", ""}
    suffixes = {_suffix(name) for name in names} | {".pdf", ".png", ".txt"}
    for suffix in suffixes:
        path = RUNTIME / f"{document_id}{suffix}"
        if path.is_file():
            path.unlink()


def clear_stale_customer_packets(store):
    """Remove previous customer packets from the case file. Originals stay on disk."""
    wanted = _wanted_ids()
    removed = []
    for customer_id in SEEDED_CUSTOMERS:
        for document in store.documents(customer_id):
            if document["document_id"] in wanted:
                continue
            store.delete_document(document["document_id"])
            _drop_runtime_copy(document)
            removed.append(document["document_id"])
    return removed


def seed_into_store(store):
    removed = clear_stale_customer_packets(store)
    alerts = [a for a in store.alerts() if a.get("signal_status") != "withdrawn"]
    attached = []
    for alert in alerts:
        packet = packet_for_alert(alert, alerts)
        if not packet:
            continue
        existing_ids = {doc["document_id"] for doc in store.documents(alert["customer_id"])}
        for item in packet["files"]:
            document_id = _stable_id(item["relative"])
            if document_id in existing_ids:
                continue
            txn = _txn_for_item(store, item)
            text, readable, confidence, origin, fields, digest = _read_packet_file(item, txn)
            if not readable:
                continue
            document = EvidenceDocument(
                document_id=document_id,
                customer_id=alert["customer_id"],
                title=_item_title(item, txn),
                content=(text or "Empty document")[:20000],
                evidence_types=list(alert["evidence_required"]),
                transaction_ids=list(alert["transaction_ids"]) if packet.get("slot") else [],
                readable=readable,
                extraction_confidence=confidence,
                origin="customer_supplied",
                artifact_type=item["artifact_type"],
                submitted_by="customer",
                file_name=Path(item["relative"]).name,
                media_type="image/png" if item["relative"].endswith(".png") else "application/pdf",
                source_relative=item["relative"],
                source_sha256=digest,
                extracted_fields=fields,
            )
            store.put_document(document.model_dump())
            existing_ids.add(document_id)
            attached.append(document.document_id)
    return {"removed": removed, "attached": attached}


def seed_customer_packets(service):
    return seed_into_store(service.store)["attached"]
