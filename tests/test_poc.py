import copy
import os
import threading
import time
import uuid
from datetime import datetime, timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from aml_poc import config  # noqa: F401 - loads .env
from aml_poc.api import create_app
from aml_poc.data import Dataset, by_customer
from aml_poc.db import connect
from aml_poc.models import ReviewDecision, Transaction
from aml_poc.rules import DetectorEngine
from aml_poc.service import Service
from aml_poc.workflow import citation_defects

pytestmark = pytest.mark.skipif(not os.environ.get("DB_HOST"), reason="RDS DB_* settings are not configured")


@pytest.fixture(scope="module")
def schemas():
    created = []

    def make():
        created.append(f"aml_test_{uuid.uuid4().hex[:10]}")
        return created[-1]

    yield make
    with connect() as conn:
        for name in created:
            conn.execute(f"DROP SCHEMA IF EXISTS {name} CASCADE")


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load()


@pytest.fixture(scope="module")
def service(dataset, schemas):
    svc = Service(dataset, schemas(), "demo")
    yield svc
    svc.close()


def tx(dataset, customer="C001", **values):
    original = next(r for r in dataset.history if r.customer_id == customer)
    row = original.model_dump(mode="json")
    row.update(values)
    return Transaction.model_validate(row)


def test_inputs_come_from_rds(dataset):
    with connect(read_only=True) as conn:
        counts = conn.execute(
            "SELECT (SELECT count(*) FROM customers) AS customers, (SELECT count(*) FROM accounts) AS accounts,"
            " (SELECT count(*) FROM transactions) AS transactions,"
            " (SELECT count(*) FROM policy_patterns) AS patterns"
        ).fetchone()
    assert len(dataset.customers) == counts["customers"]
    assert len(dataset.accounts) == counts["accounts"]
    assert len(dataset.patterns) == counts["patterns"]
    assert len(dataset.history) + len(dataset.stream) == len(dataset.transactions) == counts["transactions"]
    assert max(r.txn_ts for r in dataset.history) < min(r.txn_ts for r in dataset.stream)
    assert all("kyc_profile" in c and "assigned_pattern_ids" not in c for c in dataset.customers.values())
    assert Dataset.load().policy_hash == dataset.policy_hash


def test_stream_start_is_fixed_per_schema(dataset, schemas):
    name = schemas()
    svc = Service(dataset, name, "demo")
    original = svc.data.stream_start
    svc.close()
    os.environ["AML_STREAM_EVENTS"] = "5"
    try:
        svc = Service(Dataset.load(), name, "demo")
        assert svc.data.stream_start == original
        svc.close()
    finally:
        del os.environ["AML_STREAM_EVENTS"]
        dataset.split(original)


def test_stream_pause_restart_and_event_idempotency(service, dataset):
    row = service.stream[0]
    assert service.ingest(row)["inserted"]
    assert not service.ingest(row)["inserted"]
    changed = row.model_copy(update={"amount": row.amount + 1})
    with pytest.raises(ValueError, match="different contents"):
        service.ingest(changed)
    late = row.model_copy(update={"transaction_id": "LATE", "txn_ts": row.txn_ts - timedelta(days=2)})
    with pytest.raises(ValueError, match="Late event"):
        service.ingest(late)
    assert service.status()["stream_processed"] == 1


def test_unknown_customer_and_wrong_account_rejected(service, dataset):
    row = dataset.history[-1].model_dump(mode="json")
    row["customer_id"] = "UNKNOWN"
    with pytest.raises(ValueError, match="Customer profile missing"):
        service.ingest(row)
    row["customer_id"] = "C001"
    row["account_id"] = "ACC-C005-01"
    with pytest.raises(ValueError, match="Account does not belong"):
        service.ingest(row)


def test_no_lookahead_before_threshold(dataset):
    engine = DetectorEngine(dataset)
    start = dataset.start + timedelta(days=3)
    rows = [
        tx(
            dataset,
            transaction_id=f"TEST-{i}",
            txn_type="cash_deposit",
            cash_flag=True,
            direction="INCOMING",
            amount="9000.00",
            txn_ts=(start + timedelta(days=i)).isoformat(),
        )
        for i in range(3)
    ]
    assert not engine.detect("C001", rows, rows[1].txn_ts)
    found = engine.detect("C001", rows, rows[2].txn_ts)
    assert len(found) == 1 and found[0]["detected_at"] == rows[2].txn_ts.isoformat()


def test_funnel_allocations_never_reuse_dollars(dataset):
    rows = dataset.transactions
    groups = by_customer(rows)
    amounts = {r.transaction_id: float(r.amount) for r in rows}
    engine = DetectorEngine(dataset)
    alerts = [a for cid in groups for a in engine.detect(cid, groups[cid], rows[-1].txn_ts)]
    assert any(a["family"] == "TM-03" for a in alerts)
    for alert in alerts:
        if alert["family"] != "TM-03":
            continue
        assert 0 <= alert["metrics"]["outflow_ratio"] <= 1
        for field in ["deposit_id", "outflow_id"]:
            for key in {r[field] for r in alert["metrics"]["allocations"]}:
                assert (
                    sum(r["amount"] for r in alert["metrics"]["allocations"] if r[field] == key)
                    <= amounts[key] + 0.01
                )


def test_wire_burst_provisional_and_timer_confirmation(dataset):
    engine = DetectorEngine(dataset)
    groups = by_customer(dataset.transactions)
    end = dataset.transactions[-1].txn_ts
    cid, burst = next(
        (cid, a) for cid in groups for a in engine.detect(cid, groups[cid], end) if a["family"] == "TM-08"
    )
    at_burst_end = datetime.fromisoformat(burst["window_end"])
    provisional = next(
        a for a in engine.detect(cid, groups[cid], at_burst_end) if a["alert_id"] == burst["alert_id"]
    )
    assert provisional["signal_status"] == "provisional"
    due = datetime.fromisoformat(provisional["metrics"]["confirmation_due"])
    confirmed = next(a for a in engine.detect(cid, groups[cid], due) if a["alert_id"] == burst["alert_id"])
    assert confirmed["signal_status"] == "confirmed"


def test_report_finishes_before_human_gate(service):
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    case = service.investigate(alert["alert_id"], force=True)
    assert case["status"] == "awaiting_review"
    assert case["report"] and case["decision"] is None
    assert case["missing"] and case["recommendation"] is None
    state = service.workflow.graph.get_state({"configurable": {"thread_id": case["case_id"]}})
    assert state.next == ("human_review",)
    assert len({s["agent"] for s in case["steps"]}) == 8
    assert "assigned_pattern_ids" not in case["profile"]


def test_complete_report_review_and_sar_edit(service):
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    service.add_demo_packet(alert["alert_id"])
    case = service.investigate(alert["alert_id"], force=True)
    assert not case["missing"]
    assert case["recommendation"] == "escalate"
    assert case["critic"]["passed"]
    assert case["sar_draft"] and not citation_defects(case)
    result = service.review(
        alert["alert_id"],
        {
            "case_id": case["case_id"],
            "investigator": "Test Investigator",
            "reason": "Reviewed the synthetic evidence and approved escalation.",
            "action": "escalate",
            "sar_narrative": "Investigator edited draft. Synthetic test only.",
        },
    )
    assert result["status"] == "reviewed"
    assert result["sar_narrative"] == "Investigator edited draft. Synthetic test only."
    assert "Human reviewed SAR narrative" in result["report"]
    assert "Investigator edited draft. Synthetic test only." in result["report"]
    assert result["decision"]["agrees_with_agents"]
    with pytest.raises(ValueError, match="not waiting"):
        service.review(alert["alert_id"], result["decision"])


def test_human_override_clear_retains_no_final_sar(service):
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    case = service.investigate(alert["alert_id"], force=True)
    result = service.review(
        alert["alert_id"],
        {
            "case_id": case["case_id"],
            "investigator": "Analyst",
            "reason": "Documented source explains these transactions.",
            "action": "clear",
        },
    )
    assert result["sar_narrative"] is None
    assert "No SAR narrative retained" in result["report"]
    assert not result["decision"]["agrees_with_agents"]


def test_new_evidence_blocks_stale_decision(service):
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    case = service.investigate(alert["alert_id"], force=True)
    service.add_document(
        {
            "document_id": "TEST-NEW-EVIDENCE",
            "customer_id": alert["customer_id"],
            "title": "New explanation",
            "content": "Additional synthetic source information.",
            "evidence_types": [alert["evidence_required"][0]],
        }
    )
    with pytest.raises(ValueError, match="Evidence changed"):
        service.review(
            alert["alert_id"],
            {
                "case_id": case["case_id"],
                "investigator": "Analyst",
                "reason": "Reviewed this evidence",
                "action": "clear",
            },
        )


@pytest.mark.parametrize(
    "failure",
    [
        "missing_profile",
        "transaction_unavailable",
        "missing_document",
        "unreadable_document",
        "policy_conflict",
    ],
)
def test_failure_paths_end_with_incomplete_human_report(service, failure):
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    case = service.investigate(alert["alert_id"], force=True, failure=failure)
    assert case["status"] == "awaiting_review"
    assert case["recommendation"] is None
    assert case["completeness"] == "incomplete" and case["missing"]
    assert case["report"]


def test_citation_and_numeric_guards():
    case = {
        "evidence": [{"id": "E1", "value": {"amount": 100}}],
        "findings": [{"text": "Amount is 200", "evidence_ids": ["E1"]}],
    }
    assert "number absent" in citation_defects(case)[0]
    case["findings"][0]["evidence_ids"] = ["MISSING"]
    assert "unknown evidence" in citation_defects(case)[0]


def test_decision_reason_cannot_be_whitespace():
    with pytest.raises(ValidationError):
        ReviewDecision(action="clear", reason="     ", investigator="Analyst", case_id="case")


def test_audit_is_append_only_and_verified(service):
    assert service.store.verify_audit()
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        service.store.db.execute("DELETE FROM audit")
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        service.store.db.execute("TRUNCATE audit")


def test_document_upload_text_and_blank_pdf(service):
    from io import BytesIO

    from pypdf import PdfWriter

    alert = next(
        a
        for a in service.list_alerts()
        if a["evidence_required"]
        and not any(item.get("status") == "received" for item in a.get("customer_ask") or [])
    )
    with TestClient(create_app(service)) as client:
        response = client.post(
            "/documents/extract",
            files={
                "file": (
                    "explanation.txt",
                    b"Synthetic supplier contract and payment explanation.",
                    "text/plain",
                )
            },
            data={
                "alert_id": alert["alert_id"],
                "evidence_types": __import__("json").dumps(alert["evidence_required"]),
            },
        )
        assert response.status_code == 200
        assert response.json()["source_sha256"]
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buffer = BytesIO()
        writer.write(buffer)
        response = client.post(
            "/documents/extract",
            files={"file": ("unreadable.pdf", buffer.getvalue(), "application/pdf")},
            data={
                "alert_id": alert["alert_id"],
                "evidence_types": __import__("json").dumps(alert["evidence_required"]),
            },
        )
        assert response.status_code == 200
        assert not response.json()["readable"]
        case = service.investigate(alert["alert_id"], force=True)
        assert case["recommendation"] is None
        assert any("Unreadable" in item for item in case["missing"])


def test_model_exception_fails_closed(service):
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    service.add_demo_packet(alert["alert_id"])

    class UnavailableModel:
        def with_structured_output(self, schema):
            raise RuntimeError("Synthetic provider outage")

    service.workflow.model = UnavailableModel()
    try:
        case = service.investigate(alert["alert_id"], force=True)
        assert case["status"] == "awaiting_review"
        assert case["recommendation"] is None
        assert case["errors"]
        assert not case["critic"]["passed"]
    finally:
        service.workflow.model = None


def test_start_investigation_returns_before_model_finishes(service):
    started, release = threading.Event(), threading.Event()
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    original = service.workflow.run

    def slow(case):
        started.set()
        release.wait(10)
        return original(case)

    service.workflow.run = slow
    try:
        begin = time.monotonic()
        case = service.start_investigation(alert["alert_id"], force=True)
        assert time.monotonic() - begin < 1
        assert case["status"] == "investigating"
        assert started.wait(5)
        assert service.store.latest_case(alert["alert_id"])["status"] == "investigating"
    finally:
        release.set()
        for _ in range(50):
            if service.store.latest_case(alert["alert_id"])["status"] != "investigating":
                break
            time.sleep(0.1)
        service.workflow.run = original
    assert service.store.latest_case(alert["alert_id"])["status"] == "awaiting_review"


def test_investigate_failure_does_not_leave_case_running(service, monkeypatch):
    alert = next(a for a in service.list_alerts("all") if a["family"] == "TM-01")

    def boom(case):
        raise RuntimeError("simulated disconnect")

    monkeypatch.setattr(service.workflow, "run", boom)
    result = service.investigate(alert["alert_id"], force=True)
    assert result["status"] == "awaiting_review"
    assert result["status"] != "investigating"
    assert any("interrupted" in item.lower() for item in result["missing"])
    loaded = service.store.latest_case(alert["alert_id"])
    assert loaded["status"] == "awaiting_review"


def test_unsupported_model_claims_retry_then_reach_human(service):
    from aml_poc.models import Assessment
    from aml_poc.workflow import Critique, Narrative

    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    service.add_demo_packet(alert["alert_id"])

    class UngroundedModel:
        def with_structured_output(self, schema):
            self.schema = schema
            return self

        def invoke(self, messages):
            if self.schema is Assessment:
                return Assessment(
                    summary="Assessment of the case file",
                    summary_evidence_ids=["E1"],
                    findings=[{"text": "Amount is 99999999999999", "evidence_ids": ["E1"]}],
                    innocent_explanation="A documented sale may explain the activity.",
                    observed="The cited amount is not in the case file.",
                    next_step="Escalate for supervisor review.",
                    recommendation="escalate",
                )
            if self.schema is Narrative:
                return Narrative(sentences=[{"text": "Amount is 99999999999999", "evidence_ids": ["E1"]}])
            return Critique(defects=[])

    service.workflow.model = UngroundedModel()
    try:
        case = service.investigate(alert["alert_id"], force=True)
        assert case["critique_attempts"] == 2
        assert case["recommendation"] is None
        assert case["status"] == "awaiting_review"
        assert not case["critic"]["passed"]
        assert case["findings"]
        assert case["findings"][0]["evidence_ids"] == ["E1"]
    finally:
        service.workflow.model = None


def test_retry_timeout_keeps_findings_and_verdict(service):
    from aml_poc.models import Assessment
    from aml_poc.workflow import Critique, Narrative

    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    service.add_demo_packet(alert["alert_id"])

    class RetryThenTimeout:
        def __init__(self):
            self.assessments = 0

        def with_structured_output(self, schema):
            self.schema = schema
            return self

        def invoke(self, messages):
            if self.schema is Assessment:
                self.assessments += 1
                if self.assessments > 1:
                    raise TimeoutError("synthetic timeout")
                return Assessment(
                    summary="Assessment of the case file",
                    summary_evidence_ids=["E1"],
                    findings=[{"text": "Amount is 99999999999999", "evidence_ids": ["E1"]}],
                    innocent_explanation="A documented sale may explain the activity.",
                    observed="The cited amount is not in the case file.",
                    next_step="Escalate for supervisor review.",
                    recommendation="escalate",
                )
            if self.schema is Narrative:
                return Narrative(sentences=[{"text": "Amount is 99999999999999", "evidence_ids": ["E1"]}])
            return Critique(defects=[])

    service.workflow.model = RetryThenTimeout()
    try:
        case = service.investigate(alert["alert_id"], force=True)
        assert case["findings"]
        assert case["findings"][0]["evidence_ids"] == ["E1"]
        assert case["recommendation"] == "escalate"
        assert case["observed"]
        assert not any("failed" in item.lower() for item in case["missing"])
        assert case["status"] == "awaiting_review"
    finally:
        service.workflow.model = None


def test_monitoring_reads_stay_responsive_during_model_calls(service):
    import threading
    import time

    started, release = threading.Event(), threading.Event()
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    service.add_demo_packet(alert["alert_id"])

    class WaitingModel:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            started.set()
            release.wait(10)
            raise RuntimeError("Synthetic provider failure after wait")

    service.workflow.model = WaitingModel()
    thread = threading.Thread(target=service.investigate, args=(alert["alert_id"],), kwargs={"force": True})
    try:
        thread.start()
        assert started.wait(5)
        begin = time.monotonic()
        assert service.status()["transactions"] > 0
        assert time.monotonic() - begin < 1
    finally:
        release.set()
        thread.join(15)
        service.workflow.model = None
    assert not thread.is_alive()


def test_api_validation_and_reports(service):
    with TestClient(create_app(service)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/health").json() == {"ok": 1}
        customers = client.get("/api/customers").json()
        assert {c["customer_id"] for c in customers} == set(service.data.customers)
        assert client.get("/metrics").status_code == 404
        assert client.post("/replay/start", json={"events_per_second": -1}).status_code == 422
        assert client.get("/alerts/unknown").status_code == 404
        alert = client.get("/alerts").json()[0]
        response = client.post(
            f"/alerts/{alert['alert_id']}/investigate",
            json={"failure": "transaction_unavailable", "force": True},
        )
        assert response.status_code == 200
        case = response.json()
        for _ in range(50):
            if case.get("status") != "investigating":
                break
            time.sleep(0.1)
            case = client.get(f"/alerts/{alert['alert_id']}/case").json()
        assert case["status"] == "awaiting_review"
        assert client.get(f"/cases/{case['case_id']}/report").status_code == 200


def test_entire_stream_and_durable_restart(dataset, schemas):
    name = schemas()
    svc = Service(dataset, name, "demo")
    for row in svc.stream:
        svc.ingest(row)
    status = svc.status()
    stream_alerts = svc.list_alerts("stream")
    assert status["stream_processed"] == status["stream_total"] == len(dataset.stream)
    assert stream_alerts
    alert = stream_alerts[0]
    svc.add_demo_packet(alert["alert_id"])
    case = svc.investigate(alert["alert_id"], force=True)
    assert case["status"] == "awaiting_review"
    before = copy.deepcopy(status)
    svc.close()
    svc = Service(dataset, name, "demo")
    assert svc.status()["transactions"] == before["transactions"]
    assert svc.status()["stream_processed"] == before["stream_processed"]
    loaded = svc.store.get_case(case["case_id"])
    assert loaded["report"] == case["report"]
    result = svc.review(
        alert["alert_id"],
        {
            "case_id": case["case_id"],
            "investigator": "Restart Analyst",
            "reason": "Requesting supporting contracts before a decision.",
            "action": "request_info",
        },
    )
    assert result["status"] == "reviewed"
    provisional = [a for a in svc.store.alerts() if a["signal_status"] == "provisional"]
    svc.advance_clock("2099-01-01T00:00:00")
    assert all(svc.store.get_alert(a["alert_id"])["signal_status"] == "confirmed" for a in provisional)
    assert svc.store.verify_audit()
    svc.close()
    svc = Service(dataset, name, "demo")
    assert svc.status()["event_clock"] == "2099-01-01T00:00:00"
    svc.close()


def _first_then_later(alerts, customer_id, family):
    rows = sorted(
        [a for a in alerts if a["customer_id"] == customer_id and a["family"] == family],
        key=lambda a: a["window_start"],
    )
    assert rows
    assert rows[0]["episode_index"] == 1
    assert any(item["status"] == "received" for item in rows[0]["customer_ask"])
    for later in rows[1:]:
        assert all(item["status"] != "received" for item in later["customer_ask"])
    return rows


def test_customer_packets_seed_and_request_remaining(service, monkeypatch):
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    alerts = service.list_alerts("all")
    casa = sorted(
        [a for a in alerts if a["customer_id"] == "C002" and a["family"] == "TM-03"],
        key=lambda a: a["window_start"],
    )
    assert len(casa) >= 2
    assert any(item["status"] == "received" and item["artifact_type"] == "check" for item in casa[0]["customer_ask"])
    assert any(item["status"] == "received" and item["artifact_type"] == "check" for item in casa[1]["customer_ask"])
    for later in casa[2:]:
        assert all(item["status"] != "received" for item in later["customer_ask"])
    docs = [d for d in service.store.documents("C002") if d.get("submitted_by") == "customer"]
    assert docs and all(d["origin"] == "customer_supplied" for d in docs)
    assert any("3871" in d["content"] or "TXN-000532" in d["content"] for d in docs)
    assert any("3886" in d["content"] or "TXN-001406" in d["content"] for d in docs)
    assert all("new_E" in (d.get("source_relative") or "") for d in docs)
    assert any("ep2-" in (d.get("source_relative") or "") for d in docs)
    original = service.document_file(docs[0]["document_id"])
    assert original and original[0].is_file()
    sunnyvale = _first_then_later(alerts, "C001", "TM-01")
    assert sunnyvale[0]["episode_label"] == f"Episode 1 of {len(sunnyvale)}"
    _first_then_later(alerts, "C003", "TM-07")
    _first_then_later(alerts, "C004", "TM-09")
    if len(sunnyvale) > 1:
        later = sunnyvale[1]
        recorded = service.request_customer_documents(later["alert_id"])
        assert recorded["status"] == "sent"
        assert recorded["email"]["sent"] is False
        again = next(a for a in service.list_alerts("all") if a["alert_id"] == later["alert_id"])
        assert all(item["status"] in {"requested", "received"} for item in again["customer_ask"])
