"""Three-customer investigator demo.

Until Start finishes, Investigations and Customers stay empty.
Start streams ~100 demo transactions (Sunnyvale structuring, Casa funnel
history + open episode, Priya pass-through history + open episode, plus
benign filler). When the stream completes, the story reveals: reviewed
history and open cases on hold. Reset clears the streamed demo rows and
hides the story again. Later historical episodes stay out of the app.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from .models import Transaction
from .store import now

DEMO_CUSTOMERS = ("C001", "C002", "C003")
LIVE_PREFIX = "TXN-LIVE-"
STORY_FLAG = "demo_story_active"
AUDITOR = "Morgan Ellison"
EXPECTED_LIVE_COUNT = 10  # Casa 6 + Priya 4 open-episode payments inside the stream
EXPECTED_STREAM_COUNT = 100

LIVE_CASA_SPECS = (
    {
        "suffix": "01",
        "txn_type": "cash_deposit",
        "direction": "INCOMING",
        "amount": Decimal("4200.00"),
        "cash_flag": True,
        "branch_state": "TX",
        "branch_id": "SYNTH-BR-TX-053",
        "counterparty_id": "",
        "depositor_id": "DEP-LIVE-01",
    },
    {
        "suffix": "02",
        "txn_type": "cash_deposit",
        "direction": "INCOMING",
        "amount": Decimal("3800.00"),
        "cash_flag": True,
        "branch_state": "NV",
        "branch_id": "SYNTH-BR-NV-011",
        "counterparty_id": "",
        "depositor_id": "DEP-LIVE-02",
    },
    {
        "suffix": "03",
        "txn_type": "cash_deposit",
        "direction": "INCOMING",
        "amount": Decimal("3500.00"),
        "cash_flag": True,
        "branch_state": "TX",
        "branch_id": "SYNTH-BR-TX-053",
        "counterparty_id": "",
        "depositor_id": "DEP-LIVE-03",
    },
    {
        "suffix": "04",
        "txn_type": "check",
        "direction": "OUTGOING",
        "amount": Decimal("4000.00"),
        "cash_flag": False,
        "branch_state": "",
        "branch_id": "",
        "counterparty_id": "CP-C002-002",
        "depositor_id": "",
        "beneficiary_name": "Capitol City Meat and Seafood",
        "invoice_id": "INV-C002-LIVE-01",
        "check_number": "3991",
    },
    {
        "suffix": "05",
        "txn_type": "wire_out",
        "direction": "OUTGOING",
        "amount": Decimal("3800.00"),
        "cash_flag": False,
        "branch_state": "",
        "branch_id": "",
        "counterparty_id": "CP-C002-002",
        "depositor_id": "",
        "beneficiary_name": "Capitol City Meat and Seafood",
    },
    {
        "suffix": "06",
        "txn_type": "check",
        "direction": "OUTGOING",
        "amount": Decimal("2900.00"),
        "cash_flag": False,
        "branch_state": "",
        "branch_id": "",
        "counterparty_id": "CP-C002-001",
        "depositor_id": "",
        "beneficiary_name": "Delta Fresh Produce Co.",
        "invoice_id": "INV-C002-LIVE-02",
        "check_number": "3992",
    },
)

LIVE_PRIYA_SPECS = (
    {
        "suffix": "01",
        "txn_type": "wire_in",
        "direction": "INCOMING",
        "amount": Decimal("12500.00"),
        "counterparty_id": "CP-C003-002",
        "beneficiary_name": "",
        "originator_name": "Kestrel Health Partners",
    },
    {
        "suffix": "02",
        "txn_type": "wire_out",
        "direction": "OUTGOING",
        "amount": Decimal("12400.00"),
        "counterparty_id": "CP-C003-001",
        "beneficiary_name": "Brightwater Logistics Group",
        "originator_name": "Priya Anand-Sorensen",
    },
    {
        "suffix": "03",
        "txn_type": "wire_in",
        "direction": "INCOMING",
        "amount": Decimal("9800.00"),
        "counterparty_id": "CP-C003-003",
        "beneficiary_name": "",
        "originator_name": "Alder and Finch Retail Co.",
    },
    {
        "suffix": "04",
        "txn_type": "check",
        "direction": "OUTGOING",
        "amount": Decimal("9750.00"),
        "counterparty_id": "CP-C003-002",
        "beneficiary_name": "Kestrel Health Partners",
        "originator_name": "Priya Anand-Sorensen",
        "check_number": "4419",
        "invoice_id": "INV-C003-LIVE-01",
    },
)

REVIEWS = {
    # C001 structuring is first-look: open case, request documents, on hold (not pre-reviewed).
    ("C002", "TM-03", 1): {
        "action": "clear",
        "reason": (
            "Out-of-state cash and same-week supplier checks matched catering invoices "
            "and the owner's letter. Activity was consistent with a restaurant receiving "
            "event deposits. Closed as explained."
        ),
        "summary": (
            "Casa Brisa episode 1 looked like an out-of-region funnel. Invoices and the "
            "cash-and-suppliers letter explained the deposits. Closed."
        ),
    },
    ("C002", "TM-03", 2): {
        "action": "clear",
        "reason": (
            "Second similar cluster. Customer again provided supplier checks and invoices. "
            "Amounts were in line with catering. Closed with a note to watch for a repeat."
        ),
        "summary": (
            "Casa Brisa episode 2 was the same funnel shape. Documents were provided and "
            "the auditor closed it as explained, with a watch-for-repeat note."
        ),
    },
    ("C003", "TM-07", 1): {
        "action": "clear",
        "reason": (
            "Matched inbound wires and near-equal outbound payments aligned with supplier "
            "invoices on file. Activity was consistent with pass-through commercial settlement. "
            "Closed as explained."
        ),
        "summary": (
            "Priya Anand-Sorensen episode 1 was a pass-through pattern. Invoices supported "
            "the matched payments. Closed."
        ),
    },
}

# How many historical episodes to keep in the app before the live packet.
KEEP_HISTORY = {
    ("C001", "TM-01"): 1,
    ("C002", "TM-03"): 2,
    ("C003", "TM-07"): 1,
}


def is_live_id(transaction_id):
    return str(transaction_id).startswith(LIVE_PREFIX)


def live_casa_transactions(dataset, base_ts=None):
    """Six Casa Brisa payments that form the next funnel episode."""
    base = next(r for r in dataset.transactions if r.customer_id == "C002" and r.cash_flag)
    origin = base_ts or (
        max(r.txn_ts for r in dataset.transactions if r.customer_id == "C002") + timedelta(days=20)
    )
    rows = []
    for index, spec in enumerate(LIVE_CASA_SPECS, 1):
        payload = base.model_dump(mode="json")
        payload.update(
            {
                "transaction_id": f"{LIVE_PREFIX}C002-{spec['suffix']}",
                "account_id": "ACC-C002-01",
                "customer_id": "C002",
                "txn_ts": (origin + timedelta(minutes=index)).isoformat(),
                "txn_type": spec["txn_type"],
                "direction": spec["direction"],
                "amount": spec["amount"],
                "currency": "USD",
                "cash_flag": spec["cash_flag"],
                "branch_state": spec.get("branch_state", ""),
                "branch_id": spec.get("branch_id", ""),
                "counterparty_id": spec.get("counterparty_id", ""),
                "counterparty_country": "US" if spec.get("counterparty_id") else "",
                "depositor_id": spec.get("depositor_id", ""),
                "purpose_field": "Supplier payment" if spec["direction"] == "OUTGOING" else "",
                "invoice_id": spec.get("invoice_id", ""),
                "check_number": spec.get("check_number", ""),
                "beneficiary_name": spec.get("beneficiary_name", ""),
                "originator_name": "Casa Brisa Kitchen Inc." if spec["direction"] == "OUTGOING" else "",
                "originator_country": "US" if spec["direction"] == "OUTGOING" else "",
                "description": "Cash deposit" if spec["cash_flag"] else "Supplier payment",
            }
        )
        rows.append(Transaction.model_validate(payload))
    return rows


def live_priya_transactions(dataset, base_ts=None):
    """Four Priya payments that form the next pass-through episode."""
    base = next(
        r
        for r in dataset.transactions
        if r.customer_id == "C003" and r.direction == "INCOMING" and r.amount >= 5000
    )
    origin = base_ts or (
        max(r.txn_ts for r in dataset.transactions if r.customer_id == "C003") + timedelta(days=20)
    )
    rows = []
    for index, spec in enumerate(LIVE_PRIYA_SPECS, 1):
        payload = base.model_dump(mode="json")
        payload.update(
            {
                "transaction_id": f"{LIVE_PREFIX}C003-{spec['suffix']}",
                "account_id": "ACC-C003-01",
                "customer_id": "C003",
                "txn_ts": (origin + timedelta(hours=index)).isoformat(),
                "txn_type": spec["txn_type"],
                "direction": spec["direction"],
                "amount": spec["amount"],
                "currency": "USD",
                "cash_flag": False,
                "branch_state": "",
                "branch_id": "",
                "counterparty_id": spec["counterparty_id"],
                "counterparty_country": "US",
                "depositor_id": "",
                "purpose_field": "Commercial settlement",
                "invoice_id": spec.get("invoice_id", ""),
                "check_number": spec.get("check_number", ""),
                "beneficiary_name": spec.get("beneficiary_name", ""),
                "originator_name": spec.get("originator_name", ""),
                "originator_country": "US",
                "description": "Matched pass-through payment",
            }
        )
        rows.append(Transaction.model_validate(payload))
    return rows


def live_demo_transactions(dataset, base_ts=None):
    """Casa live packet followed by Priya live packet (10 payments)."""
    origin = base_ts or (
        max((r.txn_ts for r in dataset.transactions if r.customer_id in {"C002", "C003"}), default=datetime(2026, 1, 1))
        + timedelta(days=20)
    )
    casa = live_casa_transactions(dataset, origin)
    priya_origin = max(r.txn_ts for r in casa) + timedelta(minutes=30)
    return casa + live_priya_transactions(dataset, priya_origin)


def kept_episode_transaction_ids(dataset, engine):
    """Transaction IDs that belong to the historical episodes we keep on the queue."""
    hidden = hidden_transaction_ids(dataset, engine)
    must = set()
    for customer_id, family in KEEP_HISTORY:
        rows = [r for r in dataset.transactions if r.customer_id == customer_id and r.transaction_id not in hidden]
        as_of = max((r.txn_ts for r in rows), default=datetime(2099, 1, 1))
        alerts = sorted(
            (a for a in engine.detect(customer_id, rows, as_of) if a["family"] == family),
            key=lambda a: (a.get("window_start") or "", a["alert_id"]),
        )
        historical = [
            a
            for a in alerts
            if not any(str(i).startswith(LIVE_PREFIX) for i in a.get("transaction_ids") or [])
        ]
        for alert in historical[: KEEP_HISTORY[(customer_id, family)]]:
            must.update(alert.get("transaction_ids") or [])
    return must


def build_demo_stream_packet(dataset, engine, target=EXPECTED_STREAM_COUNT):
    """~100 transactions: kept alert clusters + open Casa/Priya live + benign filler."""
    hidden = hidden_transaction_ids(dataset, engine)
    by_id = {
        r.transaction_id: r
        for r in dataset.transactions
        if r.customer_id in DEMO_CUSTOMERS and r.transaction_id not in hidden
    }
    must_ids = kept_episode_transaction_ids(dataset, engine)
    must = [by_id[tid] for tid in must_ids if tid in by_id]
    live = live_demo_transactions(dataset)
    chosen_ids = {r.transaction_id for r in must} | {r.transaction_id for r in live}
    filler_pool = [r for r in by_id.values() if r.transaction_id not in chosen_ids]
    filler_pool.sort(key=lambda r: r.txn_ts)
    need = max(0, target - len(must) - len(live))
    # Prefer filler near the case windows so Monitoring looks like one monitoring slice.
    if must:
        anchors = {r.customer_id: r.txn_ts for r in must}
        filler_pool.sort(
            key=lambda r: (
                abs((r.txn_ts - anchors.get(r.customer_id, r.txn_ts)).total_seconds()),
                r.txn_ts,
            )
        )
    filler = filler_pool[:need]
    packet = must + filler + live
    packet.sort(key=lambda r: (r.txn_ts, r.transaction_id))
    return packet


def hidden_transaction_ids(data, engine):
    """Ledger rows that must not enter the investigator app (later historical episodes)."""
    hidden = set()
    for (customer_id, family), keep in KEEP_HISTORY.items():
        rows = [r for r in data.transactions if r.customer_id == customer_id]
        as_of = max((r.txn_ts for r in rows), default=datetime(2099, 1, 1))
        alerts = sorted(
            (a for a in engine.detect(customer_id, rows, as_of) if a["family"] == family),
            key=lambda a: (a.get("window_start") or "", a["alert_id"]),
        )
        for alert in alerts[keep:]:
            hidden.update(alert["transaction_ids"])
    return hidden


def demo_family_alerts(alerts, customer_id, family):
    """Only the historical episodes we keep for the demo, plus any live episode."""
    siblings = sorted(
        (
            a
            for a in alerts
            if a.get("customer_id") == customer_id
            and a.get("family") == family
            and a.get("signal_status") != "withdrawn"
        ),
        key=lambda a: (a.get("window_start") or "", a["alert_id"]),
    )
    keep = KEEP_HISTORY.get((customer_id, family))
    if keep is None:
        return siblings
    historical = [
        a
        for a in siblings
        if not any(is_live_id(i) for i in a.get("transaction_ids") or [])
    ]
    live = [a for a in siblings if any(is_live_id(i) for i in a.get("transaction_ids") or [])]
    return historical[:keep] + live


def select_demo_queue_alerts(alerts):
    """Raw alerts that belong on the investigator queue (no enrichment)."""
    chosen = []
    seen = set()
    for customer_id, family in KEEP_HISTORY:
        for alert in demo_family_alerts(alerts, customer_id, family):
            alert_id = alert["alert_id"]
            if alert_id in seen:
                continue
            seen.add(alert_id)
            chosen.append(alert)
    return chosen


def demo_episode_fields(alert, alerts, asks=None):
    """Episode index/label among demo-visible siblings only (so Priya live is Episode 2)."""
    siblings = demo_family_alerts(alerts, alert["customer_id"], alert["family"])
    count = len(siblings) or 1
    index = next((i for i, row in enumerate(siblings, 1) if row["alert_id"] == alert["alert_id"]), 1)
    asks = asks or []
    # Sunnyvale first-look: never treat leftover seeded files as "documents received".
    if alert.get("customer_id") == "C001" and alert.get("family") == "TM-01":
        if any(item.get("status") == "requested" for item in asks):
            documents = "requested"
        else:
            documents = "missing"
    elif asks and all(item["status"] == "received" for item in asks):
        documents = "received"
    elif any(item["status"] == "requested" for item in asks):
        documents = "requested"
    else:
        documents = "missing"
    return {
        "episode_index": index,
        "episode_count": count,
        "episode_label": f"Episode {index}",
        "documents_status": documents,
    }


def prior_episode_notes(alert, alerts, cases):
    """Closed earlier demo-visible episodes of the same customer and family."""
    family = demo_family_alerts(alerts, alert["customer_id"], alert["family"])
    notes = []
    for index, sibling in enumerate(family, 1):
        if sibling["alert_id"] == alert["alert_id"]:
            break
        case = cases.get(sibling["alert_id"]) or {}
        decision = case.get("decision") or {}
        if not decision:
            continue
        notes.append(
            {
                "alert_id": sibling["alert_id"],
                "episode_label": f"Episode {index}",
                "window_start": sibling.get("window_start"),
                "window_end": sibling.get("window_end"),
                "investigator": decision.get("investigator") or AUDITOR,
                "action": decision.get("action"),
                "reason": decision.get("reason") or "",
                "summary": case.get("summary") or "",
            }
        )
    return notes


def prune_extra_history(service):
    """Remove later historical txs/alerts that should stay out of the demo app."""
    from .data import by_customer

    hidden = getattr(service, "_hidden_ids", None)
    if hidden is None:
        hidden = hidden_transaction_ids(service.data, service.engine)
        service._hidden_ids = hidden
    changed = False
    for transaction_id in list(hidden):
        if service.store.transaction(transaction_id):
            service.store.drop_transaction(transaction_id)
            changed = True
    if changed:
        service.rows = [r for r in service.store.all_transactions()]
        service.groups = by_customer(service.rows)
    keep_ids = {a["alert_id"] for a in select_demo_queue_alerts(service.store.alerts())}
    for alert in list(service.store.alerts()):
        if alert.get("customer_id") not in DEMO_CUSTOMERS:
            continue
        if alert["alert_id"] in keep_ids:
            continue
        if any(is_live_id(i) for i in alert.get("transaction_ids") or []):
            continue
        service.store.drop_alert(alert["alert_id"])
        changed = True
    if changed:
        for customer_id in DEMO_CUSTOMERS:
            service.reconcile(customer_id)
    return changed


def story_active(service):
    return bool(service.store.metadata(STORY_FLAG))


def reveal_story(service):
    """Show demo customers and seed closed reviews. Safe to call twice."""
    from .packets import seed_customer_packets

    prune_extra_history(service)
    seed_customer_packets(service)
    prepare_sunnyvale_first_look(service)
    seed_closed_reviews(service)
    set_hold(service, "C001", True)
    service.store.set_metadata(STORY_FLAG, True)


def clear_sunnyvale_seeded_docs(service):
    """Structuring is first-look: no pre-attached documents (Request documents)."""
    from .packets import _drop_runtime_copy

    for document in list(service.store.documents("C001")):
        if not str(document.get("document_id", "")).startswith("CUST-"):
            continue
        service.store.delete_document(document["document_id"])
        _drop_runtime_copy(document)


def prepare_sunnyvale_first_look(service):
    """Open structuring case: request documents, on hold, no seeded decision/report."""
    clear_sunnyvale_seeded_docs(service)
    for alert in list(service.store.alerts()):
        if alert.get("customer_id") != "C001":
            continue
        service.store.drop_cases_for_alert(alert["alert_id"])
    set_hold(service, "C001", True)


def hide_story(service):
    """Empty Investigations/Customers again; live episode clear is handled separately."""
    service.store.set_metadata(STORY_FLAG, False)
    for customer_id in DEMO_CUSTOMERS:
        set_hold(service, customer_id, False)


def seed_closed_reviews(service):
    """Write deterministic reviewed cases for visible demo customers. Safe to call twice."""
    from .packets import customer_ask, episode_view

    siblings = service.store.alerts()
    seeded = []
    for alert in siblings:
        if alert.get("customer_id") not in DEMO_CUSTOMERS:
            continue
        if alert.get("signal_status") == "withdrawn":
            continue
        view = episode_view(alert, siblings, customer_ask(alert, siblings, service.store))
        spec = REVIEWS.get((alert["customer_id"], alert["family"], view["episode_index"]))
        if not spec:
            continue
        if service.store.latest_case(alert["alert_id"]):
            continue
        case_id = f"CASE-SEED-{alert['alert_id']}"
        created = now()
        case = {
            "case_id": case_id,
            "alert": alert,
            "as_of": service.clock.isoformat(),
            "mode": service.mode,
            "created_at": created,
            "status": "reviewed",
            "active_agent": "human_review",
            "failure": "none",
            "evidence": [],
            "missing": [],
            "errors": [],
            "steps": [],
            "completeness": "complete",
            "summary": spec["summary"],
            "observed": spec["reason"],
            "next_step": "No further action on this closed episode.",
            "findings": [{"text": spec["reason"], "evidence_ids": ["SEED"]}],
            "innocent_explanation": spec["reason"],
            "recommendation": spec["action"],
            "decision": {
                "action": spec["action"],
                "reason": spec["reason"],
                "investigator": AUDITOR,
                "case_id": case_id,
                "recorded_at": created,
            },
            "document_version": service.document_version(alert["customer_id"]),
        }
        service.store.put_case(case)
        service.store.audit(AUDITOR, "human_decision", case["decision"], case_id)
        seeded.append(case_id)
        if spec["action"] == "escalate":
            set_hold(service, alert["customer_id"], True)
    service.store.set_metadata("demo_reviews_seeded", True)
    return seeded


def visible_on_queue(row, active=True):
    """Investigator queue: empty until Start finishes; then the three demo stories."""
    if not active:
        return False
    if row.get("signal_status") == "withdrawn":
        return False
    if row.get("customer_id") not in DEMO_CUSTOMERS:
        return False
    # Rows passed through select_demo_queue_alerts are already the kept + live set.
    family = row.get("family")
    if row.get("customer_id") == "C001" and family == "TM-01":
        return True
    if row.get("customer_id") == "C002" and family == "TM-03":
        return True
    if row.get("customer_id") == "C003" and family == "TM-07":
        return True
    return False


def set_hold(service, customer_id, held):
    holds = dict(service.store.metadata("account_holds") or {})
    holds[customer_id] = bool(held)
    service.store.set_metadata("account_holds", holds)


def is_held(service, customer_id):
    holds = service.store.metadata("account_holds") or {}
    return bool(holds.get(customer_id))
