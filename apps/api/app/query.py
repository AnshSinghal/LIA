"""Read-only SELECT execution with persona injection and paging."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from app.guard import prepare


def json_cell(value):
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return value


def run_sql(conn, sql: str, persona: str, *, page: int = 1, page_size: int = 20):
    count_sql, page_sql = prepare(sql, persona, page=page, page_size=page_size)
    count_cur = conn.execute(count_sql)
    total = int(count_cur.fetchone()["n"])
    page_cur = conn.execute(page_sql)
    columns = [desc.name for desc in page_cur.description] if page_cur.description else []
    rows = []
    for record in page_cur.fetchall():
        rows.append({key: json_cell(record[key]) for key in columns})
    return columns, rows, total, page_sql


def fetch_all(conn, sql: str, persona: str, *, limit: int = 2000):
    columns, rows, total, page_sql = run_sql(conn, sql, persona, page=1, page_size=limit)
    if total > limit:
        raise RuntimeError(f"Query returned {total} rows, above the safety limit of {limit}.")
    return columns, rows, total, page_sql
