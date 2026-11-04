import copy
import hashlib
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta

from .config import agent_mode, app_schema
from .data import Dataset, by_customer
from .demo_story import (
    DEMO_CUSTOMERS,
    EXPECTED_LIVE_COUNT,
    EXPECTED_STREAM_COUNT,
    LIVE_PREFIX,
    build_demo_stream_packet,
    demo_episode_fields,
    hide_story,
    hidden_transaction_ids,
    is_held,
    is_live_id,
    prior_episode_notes,
    prune_extra_history,
    reveal_story,
    select_demo_queue_alerts,
    set_hold,
    story_active,
    visible_on_queue,
)
from .models import EvidenceDocument, ReviewDecision, Transaction
from .rules import DetectorEngine
from .store import Store, dump, now
from .workflow import Workflow


class Service:
    def __init__(self, data=None, schema=None, mode=None):
        self.lock = threading.RLock()
        self.graph_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.packet_stop = threading.Event()
        self.worker = None
        self.error = None
        self.data = data or Dataset.load()
        self.schema = schema or app_schema()
        self.store = Store(self.schema, lock=self.lock)
        self.mode = mode or agent_mode()
        known_hash = self.store.metadata("policy_hash")
        if known_hash and known_hash != self.data.policy_hash:
            self.store.close()
            raise ValueError(
                "RDS policy_patterns changed. Set a new AML_APP_SCHEMA to preserve the existing policy-versioned audit run."
            )
        self.store.set_metadata("policy_hash", self.data.policy_hash)
        # The split is fixed on first start so rows inserted into RDS later only extend the stream.
        if self.store.metadata("stream_start", False) is False:
            start = self.data.stream_start
            self.store.set_metadata("stream_start", start.isoformat() if start else None)
        saved = self.store.metadata("stream_start")
        self.data.split(datetime.fromisoformat(saved) if saved else None)
        self.engine = DetectorEngine(self.data)
        self._hidden_ids = hidden_transaction_ids(self.data, self.engine)
        if not self.store.metadata("history_loaded", False):
            # Demo customers are streamed by Monitoring Start, not preloaded.
            history = [
                r
                for r in self.data.history
                if r.transaction_id not in self._hidden_ids and r.customer_id not in DEMO_CUSTOMERS
            ]
            self.store.add_events(history, "history")
            self.store.set_metadata("history_loaded", True)
        self.rows = self.store.all_transactions()
        self.groups = by_customer(self.rows)
        self.clock = max(
            max((r.txn_ts for r in self.rows), default=datetime(2000, 1, 1)),
            datetime.fromisoformat(self.store.metadata("clock", "2000-01-01T00:00:00")),
        )
        self.workflow = Workflow(self.data, self.store, self.schema, self.mode)
        self._running = set()
        self._watch = None
        self._live_packet = []
        self._stream_ids = set()
        self._saw_remote_live = False
        # Clear demo customers before reconcile so boot does not detect/delete thousands of rows.
        self._evacuate_demo_customers_locked()
        hide_story(self)
        self._live_done = 0
        self.reconcile()
        from .packets import seed_customer_packets

        seed_customer_packets(self)
        prune_extra_history(self)
        # Closed reviews are seeded on Start (reveal_story), not at boot.
        for case in self.store.all_cases():
            if case["status"] == "investigating":
                self._close_interrupted(
                    case, "Investigation interrupted before it finished. Run again to continue."
                )
                continue
            if (
                case["status"] == "awaiting_review"
                and self.store.latest_case(case["alert"]["alert_id"])["case_id"] != case["case_id"]
            ):
                case["status"] = "superseded"
                self.store.put_case(case)
                continue
            if case["status"] != "reviewed":
                state = self.workflow.graph.get_state({"configurable": {"thread_id": case["case_id"]}})
                if state.values and state.values["case"].get("decision"):
                    self._save_review(state.values["case"])
        self.stream = self.data.stream
        self.stream_ids = {r.transaction_id for r in self.stream}
        self.stream_done = len(self.stream_ids.intersection(r.transaction_id for r in self.rows))
        self._start_live_watch()

    def reconcile(self, customer=None):
        for cid in [customer] if customer else list(self.groups):
            active = self.engine.detect(cid, self.groups[cid], self.clock)
            active_ids = {a["alert_id"] for a in active}
            for payload in active:
                self.store.put_alert(payload)
            # A provisional burst can be invalidated by continued wire activity.
            for old in self.store.alerts():
                if (
                    old["customer_id"] == cid
                    and old["alert_id"] not in active_ids
                    and old["signal_status"] != "withdrawn"
                ):
                    self.store.put_alert(
                        {
                            **{k: v for k, v in old.items() if k not in {"revision", "updated_at"}},
                            "signal_status": "withdrawn",
                            "priority": "low",
                        }
                    )

    def ingest(self, row, follow_up=True, allow_past=False):
        row = Transaction.model_validate(row) if not isinstance(row, Transaction) else row
        self.data.validate_transaction(row)
        created = []
        with self.lock:
            old = self.store.transaction(row.transaction_id)
            if old:
                if old.model_dump(mode="json") != row.model_dump(mode="json"):
                    raise ValueError("Transaction ID reused with different contents")
                return {"inserted": False, "transaction_id": row.transaction_id}
            in_packet = row.transaction_id in self._stream_ids
            if row.txn_ts < self.clock and not is_live_id(row.transaction_id) and not allow_past and not in_packet:
                raise ValueError(
                    "Late event rejected: event time precedes the watermark; replay in order or start a new run"
                )
            if is_live_id(row.transaction_id):
                row = self._place_live_row(row)
            self.store.add_events([row], "stream" if row.transaction_id in self.stream_ids else "external")
            self.rows.append(row)
            self.groups[row.customer_id].append(row)
            self.clock = max(self.clock, row.txn_ts)
            self.reconcile(row.customer_id)
            # Timer-driven rules progress even if the next event belongs to another customer.
            for cid in self.groups:
                if cid != row.customer_id and any(
                    a["customer_id"] == cid and a["family"] == "TM-08" and a["signal_status"] == "provisional"
                    for a in self.store.alerts()
                ):
                    self.reconcile(cid)
            self.stream_done = len(self.stream_ids.intersection(r.transaction_id for r in self.rows))
            created = [
                a
                for a in self.store.alerts()
                if a["customer_id"] == row.customer_id
                and a.get("signal_status") == "confirmed"
                and any(is_live_id(i) for i in a.get("transaction_ids") or [])
            ]
            for alert in created:
                set_hold(self, alert["customer_id"], True)
            result = {"inserted": True, "transaction_id": row.transaction_id}
        if follow_up:
            self._follow_up_live(created)
        return result

    def advance_clock(self, target):
        stamp = datetime.fromisoformat(target)
        with self.lock:
            if stamp < self.clock:
                raise ValueError("Event clock cannot move backwards")
            self.clock = stamp
            self.store.set_metadata("clock", target)
            self.reconcile()
            self.store.audit("replay_clock", "clock_advanced", {"as_of": target})
        return self.status()

    def list_alerts(self, scope="all"):
        with self.lock:
            if not story_active(self):
                return []
            siblings = self.store.alerts()
            cases = self.store.latest_cases()
            versions = {}
            output = []
            for alert in select_demo_queue_alerts(siblings):
                is_stream = any(i in self.stream_ids for i in alert["transaction_ids"])
                if scope == "stream" and not is_stream or scope == "history" and is_stream:
                    continue
                row = self._enrich_alert(alert, siblings, cases, versions)
                if visible_on_queue(row, active=True):
                    output.append(row)
            return sorted(output, key=lambda a: a["detected_at"], reverse=True)

    def get_alert_view(self, alert_id):
        """Single enriched alert for the investigation page (avoids loading the full queue)."""
        with self.lock:
            alert = self.store.get_alert(alert_id)
            if not alert:
                return None
            siblings = self.store.alerts()
            cases = self.store.latest_cases()
            return self._enrich_alert(alert, siblings, cases, {})

    def _enrich_alert(self, alert, siblings, cases, versions):
        from .packets import customer_ask

        case = cases.get(alert["alert_id"])
        customer_id = alert["customer_id"]
        if customer_id not in versions:
            versions[customer_id] = self.document_version(customer_id)
        profile = self.data.customers[customer_id]
        asks = customer_ask(alert, siblings, self.store)
        is_stream = any(i in self.stream_ids for i in alert["transaction_ids"])
        return {
            **alert,
            "customer_name": profile.get("business_name") or profile["fake_name"],
            "source": "stream" if is_stream else "history",
            "case_id": case["case_id"] if case else None,
            "case_status": case["status"] if case else "not_started",
            "recommendation": case.get("recommendation") if case else None,
            "customer_ask": asks,
            **demo_episode_fields(alert, siblings, asks),
            "account_hold": is_held(self, customer_id),
            "prior_episodes": prior_episode_notes(alert, siblings, cases),
            "report_stale": bool(
                case
                and (
                    case["alert"]["revision"] != alert["revision"]
                    or case.get("document_version") != versions[customer_id]
                )
            ),
        }

    def investigate(self, alert_id, failure="none", force=False):
        case = self._begin_investigation(alert_id, failure, force)
        if case.get("status") != "investigating":
            return case
        return self._finish_investigation(case)

    def start_investigation(self, alert_id, failure="none", force=False):
        case = self._begin_investigation(alert_id, failure, force)
        if case.get("status") == "investigating" and case["case_id"] not in self._running:
            self._running.add(case["case_id"])
            threading.Thread(
                target=self._run_background,
                args=(case,),
                daemon=True,
                name=f"investigate-{case['case_id']}",
            ).start()
        return case

    def _begin_investigation(self, alert_id, failure="none", force=False):
        with self.lock:
            alert = self.store.get_alert(alert_id)
            if not alert:
                raise ValueError("Unknown alert")
            previous = self.store.latest_case(alert_id)
            if previous and previous["status"] == "investigating":
                return previous
            if (
                previous
                and not force
                and failure == "none"
                and previous["alert"]["revision"] == alert["revision"]
                and previous["mode"] == self.mode
                and previous["document_version"] == self.document_version(alert["customer_id"])
                and previous["status"] in {"reviewed", "awaiting_review"}
            ):
                return previous
            case_id = f"CASE-{alert_id[4:]}-R{alert['revision']}-{uuid.uuid4().hex[:6]}"
            if previous and previous["status"] == "awaiting_review":
                previous["status"] = "superseded"
                self.store.put_case(previous)
            case = {
                "case_id": case_id,
                "alert": copy.deepcopy(alert),
                "as_of": self.clock.isoformat(),
                "mode": self.mode,
                "created_at": now(),
                "status": "investigating",
                "active_agent": "orchestrator",
                "failure": failure,
                "evidence": [],
                "missing": [],
                "errors": [],
                "steps": [],
                "decision": None,
                "recommendation": None,
                "prior_episodes": prior_episode_notes(alert, self.store.alerts(), self.store.latest_cases()),
                "document_version": self.document_version(alert["customer_id"]),
            }
            self.store.put_case(case)
            self.store.audit(
                "orchestrator",
                "investigation_started",
                {"alert_revision": alert["revision"], "mode": self.mode, "failure_simulation": failure},
                case_id,
            )
            return case

    def _finish_investigation(self, case):
        with self.graph_lock:
            try:
                result = self.workflow.run(case)
                self.store.put_case(result)
                return result
            except Exception as error:
                logging.getLogger(__name__).exception("Investigation interrupted")
                try:
                    return self._close_interrupted(
                        case,
                        f"Investigation interrupted ({type(error).__name__}). Run again to continue.",
                        agent=case.get("active_agent") or "orchestrator",
                        error_type=type(error).__name__,
                    )
                except Exception:
                    logging.getLogger(__name__).exception("Could not persist interrupted investigation")
                    case["status"] = "awaiting_review"
                    case["completeness"] = "incomplete"
                    return case

    def _close_interrupted(self, case, detail, agent="orchestrator", error_type="Interrupted"):
        case["status"] = "awaiting_review"
        case["completeness"] = "incomplete"
        case["recommendation"] = None
        case["active_agent"] = "human_review"
        case["missing"] = list(dict.fromkeys([*(case.get("missing") or []), detail]))
        case["errors"] = [
            *(case.get("errors") or []),
            {"agent": agent, "type": error_type},
        ]
        self.store.put_case(case)
        return case

    def document_version(self, customer_id):
        return hashlib.sha256(dump(self.store.documents(customer_id)).encode()).hexdigest()

    def add_document(self, document):
        doc = EvidenceDocument.model_validate(document).model_dump()
        if doc["customer_id"] not in self.data.customers:
            raise ValueError("Unknown customer")
        with self.lock:
            for transaction_id in doc["transaction_ids"]:
                row = self.store.transaction(transaction_id)
                if not row or row.customer_id != doc["customer_id"]:
                    raise ValueError("Document references an unknown or different customer's transaction")
            self.store.put_document(doc)
        return doc

    def document_file(self, document_id):
        from .files import locate, media_type

        with self.lock:
            document = self.store.get_document(document_id)
        if not document:
            return None
        path = locate(document)
        if path is None:
            return None
        filename = document.get("file_name") or path.name
        return path, document.get("media_type") or media_type(filename), filename

    def request_customer_documents(self, alert_id):
        from .mail import send_rfi
        from .packets import customer_ask, episode_view
        from .store import now as stamp

        with self.lock:
            alert = self.store.get_alert(alert_id)
            if not alert:
                raise ValueError("Unknown alert")
            existing = self.store.requests_for_alert(alert_id)
            if existing:
                return existing[0]
            siblings = self.store.alerts()
            asks = customer_ask(alert, siblings, self.store)
            outstanding = [item for item in asks if item["status"] != "received"]
            if not outstanding:
                raise ValueError("The customer has already submitted the requested documents")
            profile = self.data.customers[alert["customer_id"]]
            customer_name = profile.get("business_name") or profile.get("fake_name") or alert["customer_id"]
            episode = episode_view(alert, siblings, asks).get("episode_label") or ""
            account_id = profile.get("account_id") or ""
        mail = send_rfi(
            customer_name,
            alert["customer_id"],
            alert_id,
            outstanding,
            alert=alert,
            account_id=account_id,
            episode_label=episode,
        )
        with self.lock:
            return self.store.put_request(
                {
                    "request_id": "RFI-" + alert_id,
                    "alert_id": alert_id,
                    "customer_id": alert["customer_id"],
                    "status": "sent",
                    "channel": "email" if mail["sent"] else "case_file",
                    "created_at": stamp(),
                    "artifacts": outstanding,
                    "email": mail,
                    "note": mail["detail"],
                }
            )

    def add_demo_packet(self, alert_id, complete=True, resolution="unresolved"):
        with self.lock:
            alert = self.store.get_alert(alert_id)
            if not alert:
                raise ValueError("Unknown alert")
            required = alert["evidence_required"]
            doc = {
                "document_id": f"DEMO-{alert_id}-R{alert['revision']}-{'FULL' if complete else 'PART'}-{resolution}",
                "customer_id": alert["customer_id"],
                "title": "Synthetic supporting evidence packet",
                "content": "SYNTHETIC FIXTURE: source-of-funds explanation, counterparty relationships and business-purpose records supplied for demonstrating the review workflow. This packet is not independent verification and must never support a real filing.",
                "evidence_types": required if complete else required[:1],
                "transaction_ids": alert["transaction_ids"],
                "readable": True,
                "extraction_confidence": 1.0,
                "origin": "synthetic_fixture",
                "demonstration_resolution": resolution,
            }
            self.add_document(doc)
            return doc

    def _save_review(self, case):
        prior = self.store.get_case(case["case_id"])
        self.store.put_case(case)
        if not prior or prior["status"] != "reviewed":
            self.store.audit(
                case["decision"]["investigator"], "human_decision", case["decision"], case["case_id"]
            )

    def review(self, alert_id, decision):
        decision = ReviewDecision.model_validate(decision).model_dump()
        if len(decision["reason"].strip()) < 5:
            raise ValueError("A reason of at least five characters is required")
        with self.graph_lock, self.lock:
            case = self.store.get_case(decision["case_id"])
            alert = self.store.get_alert(alert_id)
            if not case or not alert or case["alert"]["alert_id"] != alert_id:
                raise ValueError("Case does not belong to this alert")
            if case["status"] != "awaiting_review":
                raise ValueError("Case is not waiting for review")
            if self.store.latest_case(alert_id)["case_id"] != case["case_id"]:
                raise ValueError("A newer report exists. Review the latest case version.")
            if case["alert"]["revision"] != alert["revision"] or case[
                "document_version"
            ] != self.document_version(alert["customer_id"]):
                raise ValueError("Evidence changed. Generate a fresh report before recording a decision.")
            result = self.workflow.resume(case["case_id"], decision)
            self._save_review(result)
            if decision["action"] == "clear":
                set_hold(self, alert["customer_id"], False)
            elif decision["action"] == "escalate":
                set_hold(self, alert["customer_id"], True)
            return result

    def status(self):
        with self.lock:
            active = story_active(self)
            # Lightweight counts — do not run full alert enrichment on the poll path.
            if active:
                queue = select_demo_queue_alerts(self.store.alerts())
                cases = self.store.latest_cases()
                awaiting = 0
                reviewed = 0
                stream_alerts = 0
                for alert in queue:
                    case = cases.get(alert["alert_id"])
                    status = case["status"] if case else "not_started"
                    if status == "reviewed":
                        reviewed += 1
                    else:
                        awaiting += 1
                    if any(i in self.stream_ids for i in alert.get("transaction_ids") or []) or any(
                        is_live_id(i) for i in alert.get("transaction_ids") or []
                    ):
                        stream_alerts += 1
                alert_count = len(queue)
            else:
                alert_count = awaiting = reviewed = stream_alerts = 0
            return {
                "mode": self.mode,
                "model": self.workflow.model_name,
                "event_clock": self.clock.isoformat(),
                "history_rows": len(self.data.history),
                "transactions": len(self.rows),
                "stream_total": len(self.stream),
                "stream_processed": self.stream_done,
                "live_total": len(self._live_packet) or EXPECTED_STREAM_COUNT,
                "live_processed": self._live_done,
                "transactions_processed": self._live_done,
                "running": bool(self.worker and self.worker.is_alive() and not self.packet_stop.is_set()),
                "alerts": alert_count,
                "stream_alerts": stream_alerts,
                "awaiting_review": awaiting,
                "reviewed": reviewed,
                "error": self.error,
                "policy_hash": self.data.policy_hash,
                "stream_start": self.data.stream_start.isoformat() if self.data.stream_start else None,
                "data_source": "rds",
                "app_schema": self.schema,
                "audit_integrity": self.store.verify_audit(full=False),
                "tracing": os.environ.get("LANGSMITH_TRACING", "false").lower() == "true",
                "demo_story_active": active,
            }

    def start(self, events_per_second=50, auto_investigate=False):
        """Stream ~100 demo transactions. Investigations/Customers stay empty until finished."""
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError("Stream worker is already running")
            if any(r.customer_id in DEMO_CUSTOMERS for r in self.rows):
                raise ValueError("Reset the demo stream before Start")
            packet = build_demo_stream_packet(self.data, self.engine, EXPECTED_STREAM_COUNT)
            self._evacuate_demo_customers_locked()
            self._live_packet = packet
            self._stream_ids = {r.transaction_id for r in packet}
            self._live_done = 0
            if packet:
                self.clock = min(r.txn_ts for r in packet) - timedelta(seconds=1)
            self.packet_stop.clear()
            self.error = None
            self.store.audit(
                "live_packet",
                "stream_started",
                {
                    "events_per_second": events_per_second,
                    "auto_investigate": False,
                    "packet_size": len(packet),
                    "customers": list(DEMO_CUSTOMERS),
                },
            )
            self.worker = threading.Thread(
                target=self._play_live_packet,
                args=(events_per_second,),
                daemon=True,
                name="demo-stream-packet",
            )
            self.worker.start()
        return self.status()

    def _play_live_packet(self, rate):
        finished = False
        try:
            for transaction in list(self._live_packet):
                if self.packet_stop.is_set() or self.stop_event.is_set():
                    break
                with self.lock:
                    exists = self.store.transaction(transaction.transaction_id)
                if exists:
                    with self.lock:
                        self._live_done = sum(
                            1 for r in self.rows if r.transaction_id in self._stream_ids
                        )
                    continue
                self.ingest(transaction, follow_up=True, allow_past=True)
                with self.lock:
                    self._live_done = sum(1 for r in self.rows if r.transaction_id in self._stream_ids)
                if self.packet_stop.wait(1 / max(rate, 0.1)) or self.stop_event.is_set():
                    break
            else:
                finished = True
        except Exception as error:  # noqa: BLE001 - worker failures are surfaced in status and audit
            self.error = f"{type(error).__name__}: {error}"
        finally:
            with self.lock:
                if finished and not self.error:
                    reveal_story(self)
                self.store.audit(
                    "live_packet",
                    "stream_paused" if self.packet_stop.is_set() else "stream_finished",
                    {
                        "processed": self._live_done,
                        "error": self.error,
                        "demo_story_active": story_active(self),
                    },
                )

    def reset_live_packet(self):
        """Same rewind as the start of every Start press (AWS reset equivalent)."""
        with self.lock:
            if self.worker and self.worker.is_alive():
                self.packet_stop.set()
                worker = self.worker
            else:
                worker = None
        if worker:
            worker.join(timeout=5)
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError("Stream is still stopping; pause and try Reset again")
            self._evacuate_demo_customers_locked()
            hide_story(self)
            self.store.audit("live_packet", "stream_reset", {"customers": list(DEMO_CUSTOMERS)})
        return self.status()

    def _evacuate_demo_customers_locked(self):
        """Remove demo customers in bulk so Monitoring Start can replay ~100 rows quickly."""
        self.store.drop_customers(DEMO_CUSTOMERS)
        self.rows = [r for r in self.rows if r.customer_id not in DEMO_CUSTOMERS]
        self.groups = by_customer(self.rows)
        for customer_id in DEMO_CUSTOMERS:
            self.groups[customer_id] = []
            set_hold(self, customer_id, False)
        self._clear_remote_live_rows()
        self._saw_remote_live = False
        self._live_packet = []
        self._stream_ids = set()
        self._live_done = 0
        self.packet_stop.clear()
        if self.rows:
            self.clock = max(r.txn_ts for r in self.rows)
        else:
            self.clock = datetime(2000, 1, 1)

    def _clear_live_episode_evidence_locked(self):
        """Drop live-episode uploads/RFIs so Start again does not keep Documents received."""
        from .packets import _drop_runtime_copy

        live_ids = {r.transaction_id for r in self.rows if is_live_id(r.transaction_id)}
        for alert in self.store.alerts():
            ids = alert.get("transaction_ids") or []
            if any(is_live_id(i) for i in ids):
                live_ids.update(ids)
        if not live_ids:
            return
        for customer_id in ("C002", "C003"):
            for document in list(self.store.documents(customer_id)):
                if str(document.get("document_id", "")).startswith("CUST-"):
                    continue
                doc_txns = set(document.get("transaction_ids") or [])
                if not doc_txns.intersection(live_ids):
                    continue
                self.store.delete_document(document["document_id"])
                _drop_runtime_copy(document)

    def _clear_remote_live_rows(self):
        """Drop backup RDS live rows so the next Start is a clean demo, like the AWS reset SQL."""
        try:
            from .db import connect

            with connect() as conn:
                conn.execute("DELETE FROM transactions WHERE transaction_id LIKE %s", (LIVE_PREFIX + "%",))
        except Exception:
            logging.getLogger(__name__).exception("Could not clear RDS live demo rows")

    def pause(self):
        self.packet_stop.set()
        return self.status()

    def recent(self, limit=30):
        with self.lock:
            return [r.model_dump(mode="json") for r in self.rows[-limit:]][::-1]

    def monitoring_transactions(self, limit=100):
        """Monitoring table mirrors the Start stream (demo customers only), newest first."""
        with self.lock:
            rows = [r for r in self.rows if r.customer_id in DEMO_CUSTOMERS]
            rows.sort(key=lambda r: (r.txn_ts, r.transaction_id), reverse=True)
            return [r.model_dump(mode="json") for r in rows[:limit]]

    def _place_live_row(self, row):
        """Keep live payments after that customer's history so they form a new episode."""
        last_history = max(
            (
                r.txn_ts
                for r in self.rows
                if r.customer_id == row.customer_id and not is_live_id(r.transaction_id)
            ),
            default=self.clock,
        )
        floor = last_history + timedelta(days=20)
        last_live = max(
            (
                r.txn_ts
                for r in self.rows
                if r.customer_id == row.customer_id and is_live_id(r.transaction_id)
            ),
            default=None,
        )
        if last_live is not None and last_live >= floor:
            floor = last_live + timedelta(minutes=1)
        if row.txn_ts >= floor and (last_live is None or row.txn_ts > last_live):
            return row
        return row.model_copy(update={"txn_ts": floor})

    def _follow_up_live(self, alerts):
        """Hold the account when a live cluster confirms. Document asks stay human-only."""
        seen = set()
        for alert in alerts or []:
            alert_id = alert["alert_id"]
            if alert_id in seen:
                continue
            seen.add(alert_id)
            if not any(is_live_id(i) for i in alert.get("transaction_ids") or []):
                continue
            set_hold(self, alert["customer_id"], True)

    def _run_background(self, case):
        try:
            self._finish_investigation(case)
        finally:
            self._running.discard(case["case_id"])

    def _start_live_watch(self):
        if self.schema.startswith("aml_test_"):
            return
        if os.environ.get("AML_LIVE_WATCH", "1").lower() in {"0", "false", "off", "no"}:
            return
        if self._watch and self._watch.is_alive():
            return
        self._watch = threading.Thread(target=self._watch_live, name="live-rds-watch", daemon=True)
        self._watch.start()

    def _watch_live(self):
        while not self.stop_event.wait(2):
            try:
                self.sync_live_packet()
            except Exception:
                logging.getLogger(__name__).exception("Live RDS watch failed")

    def sync_live_packet(self):
        from .db import connect

        with connect(read_only=True) as conn:
            remote = {
                r["transaction_id"]: r
                for r in conn.execute(
                    "SELECT * FROM transactions WHERE transaction_id LIKE %s ORDER BY txn_ts, transaction_id",
                    (LIVE_PREFIX + "%",),
                )
            }
        # Backup path: pull RDS inserts. Start-created local rows are reset only via Reset.
        pending = []
        with self.lock:
            if remote:
                self._saw_remote_live = True
            elif self._saw_remote_live:
                for transaction_id in [r.transaction_id for r in self.rows if is_live_id(r.transaction_id)]:
                    self._forget_live_row(transaction_id)
                self._saw_remote_live = False
                self._live_done = 0
                hide_story(self)
                return
            for transaction_id, payload in remote.items():
                if self.store.transaction(transaction_id):
                    continue
                pending.append(Transaction.model_validate(payload))
        created = []
        for row in pending:
            inserted = self.ingest(row, follow_up=False)
            if inserted.get("inserted"):
                created.extend(
                    a
                    for a in self.store.alerts()
                    if a.get("signal_status") == "confirmed"
                    and any(is_live_id(i) for i in a.get("transaction_ids") or [])
                )
        if pending:
            with self.lock:
                self._live_done = sum(1 for r in self.rows if is_live_id(r.transaction_id))
                # Reveal only once the full live packet is present (same as Start finishing).
                if self._live_done >= EXPECTED_LIVE_COUNT:
                    reveal_story(self)
            self._follow_up_live(created)

    def _forget_live_row(self, transaction_id):
        row = next((r for r in self.rows if r.transaction_id == transaction_id), None)
        customer_id = row.customer_id if row else None
        self.store.drop_transaction(transaction_id)
        self.rows = [r for r in self.rows if r.transaction_id != transaction_id]
        for rows in self.groups.values():
            rows[:] = [r for r in rows if r.transaction_id != transaction_id]
        for alert in list(self.store.alerts()):
            ids = alert.get("transaction_ids") or []
            if transaction_id in ids and all(is_live_id(i) for i in ids):
                self.store.drop_alert(alert["alert_id"])
        if self.rows:
            self.clock = max(r.txn_ts for r in self.rows)
        for cid in {customer_id} if customer_id else {"C002", "C003"}:
            still_live = any(
                a.get("customer_id") == cid
                and a.get("signal_status") != "withdrawn"
                and any(is_live_id(i) for i in a.get("transaction_ids") or [])
                for a in self.store.alerts()
            )
            if not still_live:
                set_hold(self, cid, False)
            self.reconcile(cid)

    def close(self):
        self.stop_event.set()
        if self.worker:
            self.worker.join(timeout=180)
            if self.worker.is_alive():
                raise RuntimeError("Worker did not stop; database left open to avoid corrupting active work")
        if self._watch:
            self._watch.join(timeout=5)
        deadline = time.time() + 30
        while self._running and time.time() < deadline:
            time.sleep(0.1)
        self.workflow.close()
        self.store.close()
