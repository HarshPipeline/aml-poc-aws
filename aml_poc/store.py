import hashlib
import json
import threading
from datetime import UTC, datetime
from functools import wraps

import psycopg
from psycopg import sql

from .db import checked_schema, connect
from .models import Transaction


def now():
    return datetime.now(UTC).isoformat()


def dump(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def synchronized(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)

    return guarded


SCHEMA = (
    """CREATE TABLE IF NOT EXISTS events (
  transaction_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, txn_ts TIMESTAMP NOT NULL,
  direction TEXT NOT NULL, amount NUMERIC(18,2) NOT NULL, payload JSONB NOT NULL, source TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS events_customer_ts ON events (customer_id, txn_ts)",
    """CREATE TABLE IF NOT EXISTS alerts (
  seq BIGINT GENERATED ALWAYS AS IDENTITY, id TEXT PRIMARY KEY, payload JSONB NOT NULL, revision INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS cases (
  seq BIGINT GENERATED ALWAYS AS IDENTITY, id TEXT PRIMARY KEY, alert_id TEXT NOT NULL,
  revision INTEGER NOT NULL, status TEXT NOT NULL, payload JSONB NOT NULL, created_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS cases_alert ON cases (alert_id, created_at DESC, seq DESC)",
    """CREATE TABLE IF NOT EXISTS audit (
  seq BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, ts TEXT NOT NULL, case_id TEXT, actor TEXT NOT NULL,
  event TEXT NOT NULL, payload TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL)""",
    "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS documents (
  seq BIGINT GENERATED ALWAYS AS IDENTITY, id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, payload JSONB NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS evidence_requests (
  id TEXT PRIMARY KEY, alert_id TEXT NOT NULL, payload JSONB NOT NULL)""",
    """CREATE OR REPLACE FUNCTION audit_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Audit records are append-only'; END $$""",
    """CREATE OR REPLACE TRIGGER audit_no_update BEFORE UPDATE OR DELETE ON audit
  FOR EACH ROW EXECUTE FUNCTION audit_append_only()""",
    """CREATE OR REPLACE TRIGGER audit_no_truncate BEFORE TRUNCATE ON audit
  FOR EACH STATEMENT EXECUTE FUNCTION audit_append_only()""",
)


class Store:
    """Application state in an RDS schema. Owned by one API process; the service serializes access."""

    def __init__(self, schema, lock=None):
        self.lock = lock or threading.RLock()
        self.schema = checked_schema(schema)
        self.db = connect()
        ident = sql.Identifier(self.schema)
        with self.db.transaction():
            self.db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (self.schema,))
            self.db.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(ident))
            self.db.execute(sql.SQL("SET search_path TO {}").format(ident))
            for statement in SCHEMA:
                self.db.execute(statement)
        self.db.execute(sql.SQL("SET search_path TO {}").format(ident))
        # Alerts and committed events are read on every streamed event; RDS round trips stay off that path.
        self._alerts = {
            r["id"]: r["payload"] for r in self.db.execute("SELECT id, payload FROM alerts ORDER BY seq")
        }
        self._events = {
            r["transaction_id"]: Transaction.model_validate(r["payload"])
            for r in self.db.execute(
                'SELECT transaction_id, payload FROM events ORDER BY txn_ts, transaction_id COLLATE "C"'
            )
        }
        self._verified = (0, "0" * 64)
        self._head = None

    def _conn(self):
        if self.db.closed or self.db.broken:
            self.db = connect(schema=self.schema)
        return self.db

    def _query(self, statement, params=()):
        try:
            return self._conn().execute(statement, params)
        except psycopg.OperationalError:
            if not self.db.closed:
                self.db.close()
            self.db = connect(schema=self.schema)
            return self._conn().execute(statement, params)

    @synchronized
    def close(self):
        self.db.close()

    @synchronized
    def add_events(self, rows, source):
        values = [
            (r.transaction_id, r.customer_id, r.txn_ts, r.direction, r.amount, r.model_dump_json(), source)
            for r in rows
            if r.transaction_id not in self._events
        ]
        statement = "INSERT INTO events VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s) ON CONFLICT DO NOTHING"
        if len(values) == 1:
            self._query(statement, values[0])
        elif values:
            db = self._conn()
            with db.transaction(), db.cursor() as cursor:
                cursor.executemany(statement, values)
        for row in rows:
            self._events.setdefault(row.transaction_id, row)

    @synchronized
    def transaction(self, transaction_id):
        return self._events.get(transaction_id)

    @synchronized
    def all_transactions(self):
        return sorted(self._events.values(), key=lambda r: (r.txn_ts, r.transaction_id))

    @synchronized
    def baseline(self, customer_id, as_of):
        rows = self._query(
            """SELECT direction, count(*) AS count, sum(amount)::float8 AS amount
          FROM events WHERE customer_id=%s AND txn_ts<=%s::timestamp GROUP BY direction""",
            (customer_id, as_of),
        ).fetchall()
        return {r["direction"]: {"count": r["count"], "amount": r["amount"]} for r in rows}

    @synchronized
    def put_alert(self, payload):
        old = self.get_alert(payload["alert_id"])
        clean = json.loads(dump(payload))

        # A ticking clock is not new evidence until the provisional signal changes state.
        def signature(value):
            value = json.loads(dump(value))
            value.pop("revision", None)
            value.pop("updated_at", None)
            value.get("metrics", {}).pop("quiet_days_after", None)
            return dump(value)

        if old and signature(old) == signature(clean):
            return old, False
        revision = (old["revision"] if old else 0) + 1
        clean.update(revision=revision, updated_at=now())
        self._query(
            "INSERT INTO alerts (id, payload, revision) VALUES (%s, %s::jsonb, %s)"
            " ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, revision=excluded.revision",
            (clean["alert_id"], dump(clean), revision),
        )
        self._alerts[clean["alert_id"]] = clean
        self.audit(
            "rule_engine",
            "alert_updated" if old else "alert_created",
            {"alert_id": clean["alert_id"], "revision": revision, "patterns": clean["pattern_ids"]},
        )
        return clean, True

    @synchronized
    def get_alert(self, alert_id):
        alert = self._alerts.get(alert_id)
        return json.loads(dump(alert)) if alert else None

    @synchronized
    def alerts(self):
        return [json.loads(dump(a)) for a in self._alerts.values()]

    @synchronized
    def put_case(self, case):
        self._query(
            "INSERT INTO cases (id, alert_id, revision, status, payload, created_at)"
            " VALUES (%s, %s, %s, %s, %s::jsonb, %s)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload=excluded.payload",
            (
                case["case_id"],
                case["alert"]["alert_id"],
                case["alert"]["revision"],
                case["status"],
                dump(case),
                case["created_at"],
            ),
        )

    @synchronized
    def get_case(self, case_id):
        row = self._query("SELECT payload FROM cases WHERE id=%s", (case_id,)).fetchone()
        return row["payload"] if row else None

    @synchronized
    def latest_case(self, alert_id):
        row = self._query(
            "SELECT payload FROM cases WHERE alert_id=%s ORDER BY created_at DESC, seq DESC LIMIT 1",
            (alert_id,),
        ).fetchone()
        return row["payload"] if row else None

    @synchronized
    def latest_cases(self):
        rows = self._query(
            "SELECT DISTINCT ON (alert_id) alert_id, payload FROM cases"
            " ORDER BY alert_id, created_at DESC, seq DESC"
        )
        return {r["alert_id"]: r["payload"] for r in rows}

    @synchronized
    def all_cases(self):
        return [r["payload"] for r in self._query("SELECT payload FROM cases ORDER BY created_at DESC")]

    @synchronized
    def case_counts(self):
        rows = self._query("SELECT status, count(*) AS count FROM cases GROUP BY status")
        return {r["status"]: r["count"] for r in rows}

    @synchronized
    def metadata(self, key, default=None):
        row = self._query("SELECT value FROM metadata WHERE key=%s", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    @synchronized
    def set_metadata(self, key, value):
        self._query(
            "INSERT INTO metadata VALUES (%s, %s) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, dump(value)),
        )

    @synchronized
    def documents(self, customer_id):
        rows = self._query("SELECT payload FROM documents WHERE customer_id=%s ORDER BY seq", (customer_id,))
        return [r["payload"] for r in rows]

    @synchronized
    def get_document(self, document_id):
        row = self._query("SELECT payload FROM documents WHERE id=%s", (document_id,)).fetchone()
        return row["payload"] if row else None

    @synchronized
    def put_document(self, document):
        # Evidence is immutable; a correction must have a new document ID.
        old = self._query("SELECT payload FROM documents WHERE id=%s", (document["document_id"],)).fetchone()
        if old:
            if old["payload"] != json.loads(dump(document)):
                raise ValueError("Document ID exists; use a new ID for a correction")
            return False
        self._query(
            "INSERT INTO documents (id, customer_id, payload) VALUES (%s, %s, %s::jsonb)",
            (document["document_id"], document["customer_id"], dump(document)),
        )
        self.audit(
            "document_intake",
            "document_added",
            {"document_id": document["document_id"], "customer_id": document["customer_id"]},
        )
        return True

    @synchronized
    def delete_document(self, document_id):
        old = self._query("SELECT payload FROM documents WHERE id=%s", (document_id,)).fetchone()
        if not old:
            return False
        self._query("DELETE FROM documents WHERE id=%s", (document_id,))
        self.audit(
            "document_intake",
            "document_removed",
            {
                "document_id": document_id,
                "customer_id": old["payload"].get("customer_id"),
                "source_relative": old["payload"].get("source_relative"),
            },
        )
        return True

    @synchronized
    def put_request(self, request):
        existing = self._query(
            "SELECT payload FROM evidence_requests WHERE id=%s", (request["request_id"],)
        ).fetchone()
        if existing:
            return existing["payload"]
        self._query(
            "INSERT INTO evidence_requests (id, alert_id, payload) VALUES (%s, %s, %s::jsonb)",
            (request["request_id"], request["alert_id"], dump(request)),
        )
        self.audit(
            "investigator",
            "evidence_requested",
            {"request_id": request["request_id"], "alert_id": request["alert_id"]},
        )
        return request

    @synchronized
    def requests_for_alert(self, alert_id):
        rows = self._query("SELECT payload FROM evidence_requests WHERE alert_id=%s", (alert_id,))
        return [r["payload"] for r in rows]

    @synchronized
    def audit(self, actor, event, payload, case_id=None):
        ts = now()
        serialized = dump(payload)

        def digest(previous):
            return hashlib.sha256(dump([ts, case_id, actor, event, serialized, previous]).encode()).hexdigest()

        columns = "INSERT INTO audit(ts, case_id, actor, event, payload, previous_hash, hash)"
        if self._head:
            # Appends only if the chain head is still the one this process last wrote.
            previous = self._head
            inserted = self._query(
                columns + " SELECT %s, %s, %s, %s, %s, %s, %s"
                " WHERE (SELECT hash FROM audit ORDER BY seq DESC LIMIT 1) = %s",
                (ts, case_id, actor, event, serialized, previous, digest(previous), previous),
            ).rowcount
            if inserted:
                self._head = digest(previous)
                return
        db = self._conn()
        with db.transaction():
            db.execute("LOCK TABLE audit IN SHARE ROW EXCLUSIVE MODE")
            prior = db.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
            previous = prior["hash"] if prior else "0" * 64
            db.execute(
                columns + " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (ts, case_id, actor, event, serialized, previous, digest(previous)),
            )
        self._head = digest(previous)

    @synchronized
    def audit_rows(self, case_id=None):
        query = "SELECT * FROM audit" + (" WHERE case_id=%s" if case_id else "") + " ORDER BY seq"
        rows = self._query(query, (case_id,) if case_id else ()).fetchall()
        return [{**r, "payload": json.loads(r["payload"])} for r in rows]

    @synchronized
    def verify_audit(self, full=True):
        """Full verification rereads the chain; incremental checks only rows added since the last pass."""
        seq, previous = (0, "0" * 64) if full else self._verified
        rows = self._query("SELECT * FROM audit WHERE seq > %s ORDER BY seq", (seq,))
        for r in rows:
            expected = hashlib.sha256(
                dump([r["ts"], r["case_id"], r["actor"], r["event"], r["payload"], previous]).encode()
            ).hexdigest()
            if r["previous_hash"] != previous or r["hash"] != expected:
                return False
            seq, previous = r["seq"], r["hash"]
        self._verified = (seq, previous)
        return True
