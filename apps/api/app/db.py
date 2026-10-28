"""Admin and read-only Postgres connections."""

from __future__ import annotations

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from app.config import admin_dsn, reader_dsn


@contextmanager
def admin_conn():
    conn = psycopg.connect(admin_dsn(), row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def reader_conn():
    conn = psycopg.connect(reader_dsn(), row_factory=dict_row, autocommit=True)
    try:
        conn.execute("SET statement_timeout = '5s'")
        conn.execute("SET default_transaction_read_only = on")
        yield conn
    finally:
        conn.close()
