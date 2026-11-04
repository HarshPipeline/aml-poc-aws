import os
import time
import uuid
from datetime import timedelta
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from aml_poc import config  # noqa: F401
from aml_poc.api import create_app
from aml_poc.data import Dataset
from aml_poc.db import connect
from aml_poc.demo_story import (
    DEMO_CUSTOMERS,
    EXPECTED_STREAM_COUNT,
    LIVE_PREFIX,
    build_demo_stream_packet,
    hidden_transaction_ids,
    is_held,
    is_live_id,
    reveal_story,
    story_active,
    visible_on_queue,
)
from aml_poc.models import Transaction
from aml_poc.rules import DetectorEngine
from aml_poc.service import Service

pytestmark = pytest.mark.skipif(not os.environ.get("DB_HOST"), reason="RDS DB_* settings are not configured")


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load()


@pytest.fixture
def demo_service(dataset):
    name = f"aml_test_{uuid.uuid4().hex[:10]}"
    svc = Service(dataset, name, "demo")
    yield svc
    svc.close()
    with connect() as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {name} CASCADE")


def test_hidden_ids_are_later_episodes(dataset):
    hidden = hidden_transaction_ids(dataset, DetectorEngine(dataset))
    assert "TXN-002017" in hidden  # later Casa funnel
    assert "TXN-002863" in hidden
    assert "TXN-000522" not in hidden  # Casa ep1/2 retained
    assert "TXN-001336" not in hidden


def test_queue_empty_until_start(demo_service):
    assert not story_active(demo_service)
    assert demo_service.list_alerts() == []
    assert not is_held(demo_service, "C002")


def _seed_demo_stream(demo_service, include_live=True):
    packet = build_demo_stream_packet(demo_service.data, demo_service.engine, EXPECTED_STREAM_COUNT)
    if not include_live:
        packet = [row for row in packet if not is_live_id(row.transaction_id)]
    demo_service._stream_ids = {row.transaction_id for row in packet}
    if packet:
        demo_service.clock = min(row.txn_ts for row in packet) - timedelta(seconds=1)
    for row in packet:
        demo_service.ingest(row, follow_up=False, allow_past=True)
    demo_service._live_done = sum(1 for row in demo_service.rows if row.customer_id in DEMO_CUSTOMERS)
    demo_service._live_packet = list(packet)
    return packet


def test_build_demo_stream_packet_is_hundred(dataset):
    from aml_poc.rules import DetectorEngine

    packet = build_demo_stream_packet(dataset, DetectorEngine(dataset), EXPECTED_STREAM_COUNT)
    assert len(packet) == EXPECTED_STREAM_COUNT
    assert {r.customer_id for r in packet} >= {"C001", "C002", "C003"}
    assert sum(1 for r in packet if is_live_id(r.transaction_id)) == 10


def test_reveal_shows_three_customer_history(demo_service):
    _seed_demo_stream(demo_service, include_live=False)
    reveal_story(demo_service)
    rows = demo_service.list_alerts()
    assert story_active(demo_service)
    assert {r["customer_id"] for r in rows} == {"C001", "C002", "C003"}
    assert all(r["episode_label"] == f"Episode {r['episode_index']}" for r in rows)
    assert " of " not in " ".join(r["episode_label"] for r in rows)
    by_customer = {}
    for row in rows:
        by_customer.setdefault(row["customer_id"], []).append(row)
    assert {r["episode_index"] for r in by_customer["C001"]} == {1}
    assert by_customer["C001"][0]["family"] == "TM-01"
    assert by_customer["C001"][0]["case_status"] == "not_started"
    assert by_customer["C001"][0]["documents_status"] == "missing"
    assert by_customer["C001"][0]["report_stale"] is False
    assert by_customer["C001"][0]["account_hold"] is True
    assert is_held(demo_service, "C001")
    assert {r["episode_index"] for r in by_customer["C002"]} == {1, 2}
    assert all(r["case_status"] == "reviewed" for r in by_customer["C002"])
    assert {r["episode_index"] for r in by_customer["C003"]} == {1}
    assert by_customer["C003"][0]["family"] == "TM-07"
    assert by_customer["C003"][0]["case_status"] == "reviewed"
    later = next(r for r in by_customer["C002"] if r["episode_index"] == 2)
    assert later["prior_episodes"]
    assert later["prior_episodes"][0]["episode_label"] == "Episode 1"
    assert all(visible_on_queue(r, active=True) for r in rows)


def live_row(dataset, customer_id, suffix, **values):
    base = next(r for r in dataset.history if r.customer_id == customer_id and r.cash_flag)
    payload = base.model_dump(mode="json")
    payload.update(
        transaction_id=f"{LIVE_PREFIX}{customer_id}-{suffix}",
        txn_ts=(dataset.history[-1].txn_ts + timedelta(days=3, minutes=int(suffix[-2:]))).isoformat(),
        **values,
    )
    return Transaction.model_validate(payload)


def test_live_cluster_opens_one_held_case(demo_service, dataset):
    _seed_demo_stream(demo_service, include_live=False)
    reveal_story(demo_service)
    last = max(r.txn_ts for r in demo_service.groups["C002"])
    clock = max(demo_service.clock, last) + timedelta(days=20)
    deposits = [
        live_row(dataset, "C002", "01", cash_flag=True, direction="INCOMING", txn_type="cash_deposit", amount=4200, branch_state="TX"),
        live_row(dataset, "C002", "02", cash_flag=True, direction="INCOMING", txn_type="cash_deposit", amount=3800, branch_state="NV"),
        live_row(dataset, "C002", "03", cash_flag=True, direction="INCOMING", txn_type="cash_deposit", amount=3500, branch_state="TX"),
    ]
    outflows = [
        live_row(dataset, "C002", "04", cash_flag=False, direction="OUTGOING", txn_type="check", amount=4000, branch_state=""),
        live_row(dataset, "C002", "05", cash_flag=False, direction="OUTGOING", txn_type="wire_out", amount=3800, branch_state=""),
        live_row(dataset, "C002", "06", cash_flag=False, direction="OUTGOING", txn_type="check", amount=2900, branch_state=""),
    ]
    for index, row in enumerate(deposits + outflows):
        row = row.model_copy(update={"txn_ts": clock + timedelta(minutes=index + 1)})
        demo_service.ingest(row, follow_up=index == 5)
    live = [
        r
        for r in demo_service.list_alerts()
        if any(str(i).startswith(f"{LIVE_PREFIX}C002-") for i in r["transaction_ids"])
    ]
    assert live
    case = live[0]
    assert case["account_hold"] is True
    assert case["prior_episodes"]
    assert case["episode_index"] == 3
    assert case["episode_label"] == "Episode 3"
    assert is_held(demo_service, "C002")
    assert not demo_service.store.requests_for_alert(case["alert_id"])


def _wait_live_done(demo_service, count=EXPECTED_STREAM_COUNT, seconds=120):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if demo_service._live_done >= count and not (demo_service.worker and demo_service.worker.is_alive()):
            return
        time.sleep(0.1)
    assert demo_service._live_done >= count


def test_start_posts_casa_and_priya_live_packets(demo_service):
    assert demo_service.list_alerts() == []
    status = demo_service.start(events_per_second=50, auto_investigate=False)
    assert status["demo_story_active"] is False
    assert status["live_total"] == EXPECTED_STREAM_COUNT
    assert demo_service.list_alerts() == []
    _wait_live_done(demo_service)
    assert demo_service._live_done == EXPECTED_STREAM_COUNT
    assert story_active(demo_service)
    assert sum(1 for r in demo_service.rows if r.customer_id in DEMO_CUSTOMERS) == EXPECTED_STREAM_COUNT
    rows = demo_service.list_alerts()
    assert {r["customer_id"] for r in rows} == {"C001", "C002", "C003"}
    casa_live = [
        r
        for r in rows
        if any(str(i).startswith(f"{LIVE_PREFIX}C002-") for i in r["transaction_ids"])
    ]
    priya_live = [
        r
        for r in rows
        if any(str(i).startswith(f"{LIVE_PREFIX}C003-") for i in r["transaction_ids"])
    ]
    assert len(casa_live) == 1
    assert casa_live[0]["episode_index"] == 3
    assert casa_live[0]["prior_episodes"]
    assert is_held(demo_service, "C002")
    assert len(priya_live) == 1
    assert priya_live[0]["episode_index"] == 2
    assert priya_live[0]["episode_label"] == "Episode 2"
    assert priya_live[0]["prior_episodes"]
    assert priya_live[0]["prior_episodes"][0]["episode_label"] == "Episode 1"
    assert is_held(demo_service, "C003")
    sunnyvale = next(r for r in rows if r["customer_id"] == "C001")
    assert sunnyvale["documents_status"] == "missing"
    assert sunnyvale["case_status"] == "not_started"
    assert sunnyvale["report_stale"] is False
    assert sunnyvale["account_hold"] is True
    assert is_held(demo_service, "C001")
    first_alert = casa_live[0]["alert_id"]
    seeded_before = {
        d["document_id"]
        for d in demo_service.store.documents("C002")
        if str(d["document_id"]).startswith("CUST-")
    }
    with TestClient(create_app(demo_service)) as client:
        response = client.post(
            "/documents/extract",
            files={"file": ("LTR-cash-and-suppliers.pdf", b"%PDF-1.4 mailroom letter", "application/pdf")},
            data={
                "alert_id": first_alert,
                "evidence_types": __import__("json").dumps(casa_live[0]["evidence_required"][:1]),
            },
        )
    if response.status_code != 200:
        image = Image.new("RGB", (16, 16), color=(1, 2, 3))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        with TestClient(create_app(demo_service)) as client:
            response = client.post(
                "/documents/extract",
                files={"file": ("CHK-live-mail.png", buffer.getvalue(), "image/png")},
                data={
                    "alert_id": first_alert,
                    "evidence_types": __import__("json").dumps(casa_live[0]["evidence_required"][:1]),
                },
            )
    assert response.status_code == 200
    uploaded = response.json()
    assert uploaded["submitted_by"] == "customer"
    with pytest.raises(ValueError, match="Reset"):
        demo_service.start(events_per_second=50, auto_investigate=False)
    demo_service.reset_live_packet()
    assert not story_active(demo_service)
    assert demo_service.list_alerts() == []
    assert uploaded["document_id"] not in {d["document_id"] for d in demo_service.store.documents("C002")}
    assert seeded_before <= {d["document_id"] for d in demo_service.store.documents("C002")}
    assert not any(str(r.transaction_id).startswith(LIVE_PREFIX) for r in demo_service.rows)
    assert not is_held(demo_service, "C002")
    assert not is_held(demo_service, "C003")
    assert demo_service.store.get_alert(first_alert) is None
    demo_service.start(events_per_second=50, auto_investigate=False)
    _wait_live_done(demo_service)
    assert story_active(demo_service)
    live_again = [
        r
        for r in demo_service.list_alerts()
        if any(str(i).startswith(f"{LIVE_PREFIX}C002-") for i in r["transaction_ids"])
    ]
    assert len(live_again) == 1
    assert live_again[0]["episode_index"] == 3
    assert is_held(demo_service, "C002")
    assert live_again[0]["documents_status"] != "received"


def test_png_upload_attaches_in_demo_mode(demo_service):
    _seed_demo_stream(demo_service, include_live=False)
    reveal_story(demo_service)
    alert = next(a for a in demo_service.list_alerts() if a["customer_id"] == "C002" and a["episode_index"] == 1)
    image = Image.new("RGB", (32, 32), color=(20, 40, 60))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    with TestClient(create_app(demo_service)) as client:
        response = client.post(
            "/documents/extract",
            files={"file": ("CHK-3902-TXN-002035.png", buffer.getvalue(), "application/octet-stream")},
            data={
                "alert_id": alert["alert_id"],
                "evidence_types": __import__("json").dumps(alert["evidence_required"]),
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["media_type"] == "image/png"
    assert body["readable"] is True
    assert body["file_name"] == "CHK-3902-TXN-002035.png"
    assert body["artifact_type"] == "check"
    assert body["submitted_by"] == "customer"


def test_png_upload_survives_empty_model_extraction(demo_service):
    _seed_demo_stream(demo_service, include_live=False)
    reveal_story(demo_service)
    alert = next(a for a in demo_service.list_alerts() if a["customer_id"] == "C002" and a["episode_index"] == 1)

    class EmptyModel:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            return {}

    demo_service.workflow.model = EmptyModel()
    image = Image.new("RGB", (24, 24), color=(10, 20, 30))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    with TestClient(create_app(demo_service)) as client:
        response = client.post(
            "/documents/extract",
            files={"file": ("CHK-3903-TXN-002177.png", buffer.getvalue(), "image/png")},
            data={
                "alert_id": alert["alert_id"],
                "evidence_types": __import__("json").dumps(alert["evidence_required"][:1]),
            },
        )
    demo_service.workflow.model = None
    assert response.status_code == 200
    body = response.json()
    assert body["readable"] is True
    assert "attached" in body["content"].lower()
