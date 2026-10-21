"""RDS PostgreSQL connections. Every input and all application state live in this database."""

import os
import re

import psycopg
from psycopg.rows import dict_row

from . import config  # noqa: F401 - loads .env before connection settings are read

SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def checked_schema(name):
    if not SCHEMA_NAME.match(name):
        raise ValueError("AML_APP_SCHEMA must be a lowercase PostgreSQL identifier")
    return name


def connect(read_only=False, schema=None, autocommit=True, row_factory=dict_row, **kwargs):
    options = ["-c statement_timeout=15000"]
    if read_only:
        options.append("-c default_transaction_read_only=on")
    if schema:
        options.append(f"-c search_path={checked_schema(schema)}")
    missing = [k for k in ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"] if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"RDS connection settings missing from the environment: {', '.join(missing)}")
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        sslmode=os.environ.get("DB_SSLMODE", "require"),
        connect_timeout=10,
        options=" ".join(options),
        autocommit=autocommit,
        row_factory=row_factory,
        **kwargs,
    )
