"""Load operational data from RDS. Evaluation labels are deliberately absent from this module."""

import hashlib
import json
import os
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from .db import connect
from .models import Transaction


def plain(value):
    """Convert database types to the JSON-native values the rules and agents consume."""
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def nest_range(row, prefix, target, min_suffix="_min", max_suffix="_max"):
    row[target] = {"min": row.pop(prefix + min_suffix), "max": row.pop(prefix + max_suffix)}


def load_records():
    with connect(read_only=True) as conn:
        customers = conn.execute("SELECT * FROM customers ORDER BY customer_id").fetchall()
        kyc = {
            r["customer_id"]: r for r in conn.execute("SELECT * FROM kyc_profiles ORDER BY customer_id")
        }
        owners = conn.execute(
            "SELECT customer_id, name, ownership_percent, date_of_birth, id_document_type, id_verified"
            " FROM beneficial_owners ORDER BY customer_id, ownership_percent DESC"
        ).fetchall()
        accounts = conn.execute("SELECT * FROM accounts ORDER BY account_id").fetchall()
        counterparties = conn.execute("SELECT * FROM counterparties ORDER BY counterparty_id").fetchall()
        links = conn.execute("SELECT customer_id, counterparty_id FROM customer_counterparties").fetchall()
        patterns = conn.execute("SELECT * FROM policy_patterns ORDER BY pattern_id").fetchall()
        transactions = conn.execute(
            'SELECT * FROM transactions ORDER BY txn_ts, transaction_id COLLATE "C"'
        ).fetchall()
    owners_by_customer = defaultdict(list)
    for owner in owners:
        owners_by_customer[owner.pop("customer_id")].append(plain(owner))
    accounts_by_customer = defaultdict(list)
    for account in accounts:
        accounts_by_customer[account["customer_id"]].append(account["account_id"])
    links_by_counterparty = defaultdict(list)
    for link in links:
        links_by_counterparty[link["counterparty_id"]].append(link["customer_id"])

    customer_rows = []
    for row in map(plain, customers):
        nest_range(row, "expected_monthly_txn_count", "expected_monthly_transaction_count")
        nest_range(row, "expected_monthly_volume_usd", "expected_monthly_transaction_volume_usd")
        profile = plain(kyc.get(row["customer_id"]) or {})
        profile.pop("customer_id", None)
        row["kyc_profile"] = {**profile, "beneficial_owners": owners_by_customer[row["customer_id"]]}
        ids = accounts_by_customer[row["customer_id"]]
        row["account_id"] = ids[0] if ids else None
        customer_rows.append(row)
    account_rows = []
    for row in map(plain, accounts):
        nest_range(row, "expected_balance", "expected_balance_range_usd", "_min_usd", "_max_usd")
        account_rows.append(row)
    counterparty_rows = []
    for row in map(plain, counterparties):
        nest_range(row, "expected_amount", "expected_amount_range_usd", "_min_usd", "_max_usd")
        row["associated_customer_ids"] = sorted(links_by_counterparty[row["counterparty_id"]])
        counterparty_rows.append(row)
    policy = [
        {
            **plain(r["definition"]),
            "pattern_id": r["pattern_id"],
            "enabled_for_initial_synthesis": bool(r["enabled_for_initial_synthesis"]),
        }
        for r in patterns
    ]
    rows = [Transaction.model_validate({k: v for k, v in r.items() if v is not None}) for r in transactions]
    return customer_rows, account_rows, counterparty_rows, policy, rows


class Dataset:
    def __init__(self, customers, accounts, counterparties, patterns, transactions):
        self.customers = self._index(customers, "customer_id")
        self.accounts = self._index(accounts, "account_id")
        self.counterparties = self._index(counterparties, "counterparty_id")
        canonical = json.dumps(patterns, sort_keys=True, separators=(",", ":"))
        self.policy_hash = hashlib.sha256(canonical.encode()).hexdigest()
        self.patterns = {p["pattern_id"]: p for p in patterns}
        self.enabled = {k: p for k, p in self.patterns.items() if p["enabled_for_initial_synthesis"]}
        supported = {"TM-01", "TM-03", "TM-04", "TM-07", "TM-08", "TM-09"}
        if self.enabled.keys() - supported:
            raise ValueError("Unsupported enabled detectors: " + str(self.enabled.keys() - supported))
        required = {
            "TM-01": {
                "near_threshold_floor_usd",
                "near_threshold_ceiling_usd",
                "min_txn_count",
                "window_days",
                "min_aggregate_usd",
            },
            "TM-03": {
                "min_distinct_out_of_state_states",
                "min_deposit_count",
                "window_days",
                "min_out_of_region_share",
            },
            "TM-04": {"max_hours_deposit_to_outflow", "min_outflow_to_inflow_ratio"},
            "TM-07": {"amount_tolerance_pct", "max_days_between", "min_pairs", "min_amount_usd"},
            "TM-08": {
                "quiet_days_before",
                "active_burst_days_max",
                "quiet_days_after",
                "min_burst_wire_count",
                "min_burst_total_usd",
            },
            "TM-09": {"min_round_wire_share", "min_wire_count", "lookback_days", "new_counterparty_days"},
        }
        for key, pattern in self.enabled.items():
            thresholds = pattern["demo_thresholds"]
            if required[key] - thresholds.keys():
                raise ValueError(f"Missing policy thresholds for {key}")
            for field in required[key]:
                if not isinstance(thresholds[field], (int, float)) or thresholds[field] <= 0:
                    raise ValueError(f"Invalid positive threshold: {key}.{field}")
        if not transactions:
            raise ValueError("The RDS transactions table is empty")
        if len({r.transaction_id for r in transactions}) != len(transactions):
            raise ValueError("Transaction IDs must be unique")
        for row in transactions:
            self.validate_transaction(row)
        self.transactions = sorted(transactions, key=lambda r: (r.txn_ts, r.transaction_id))
        self.start = self.transactions[0].txn_ts
        self.split(self.default_stream_start())

    @classmethod
    def load(cls):
        return cls(*load_records())

    @staticmethod
    def _index(entries, key):
        indexed = {r[key]: r for r in entries}
        if len(indexed) != len(entries):
            raise ValueError(f"Duplicate {key} values")
        return indexed

    def default_stream_start(self):
        if os.environ.get("AML_STREAM_START"):
            return datetime.fromisoformat(os.environ["AML_STREAM_START"])
        count = int(os.environ.get("AML_STREAM_EVENTS", "1000"))
        if count <= 0:
            return None
        return self.transactions[max(len(self.transactions) - count, 1)].txn_ts

    def split(self, stream_start):
        """Rows before stream_start are history; the rest are replayed in event-time order."""
        if stream_start is None:
            self.history, self.stream = self.transactions, []
        else:
            self.history = [r for r in self.transactions if r.txn_ts < stream_start]
            self.stream = [r for r in self.transactions if r.txn_ts >= stream_start]
        if not self.history:
            raise ValueError("The stream start leaves no RDS transactions as history")
        self.stream_start = stream_start

    def validate_transaction(self, transaction: Transaction):
        if transaction.customer_id not in self.customers:
            raise ValueError("Customer profile missing; event rejected for manual review")
        account = self.accounts.get(transaction.account_id)
        if not account or account["customer_id"] != transaction.customer_id:
            raise ValueError("Account does not belong to customer")


def by_customer(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row.customer_id].append(row)
    return groups
