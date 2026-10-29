"""Shared paged execution for reviewed SQL."""

from __future__ import annotations

from app.pack import (
    PERIOD,
    conflict_answer,
    filters_for,
    pack,
    page_note,
    scope_conflict,
    slice_page,
    visible_rows,
)
from app.query import fetch_all


def execute(conn, sql, slots, persona, page, template_id, summary, answer, exclusions, assumptions, period=PERIOD):
    filters = filters_for(persona, slots)
    columns, rows, _total, page_sql = fetch_all(conn, sql, persona)
    if scope_conflict(slots, persona):
        rows = visible_rows(rows, persona)
        total = len(rows)
        shown = slice_page(rows, page)
        text = conflict_answer(slots) + f" The guarded query returned {total} rows."
        text += page_note(page, total, len(shown))
    else:
        rows = visible_rows(rows, persona)
        total = len(rows)
        shown = slice_page(rows, page)
        text = answer(rows, shown, total) if callable(answer) else str(answer)
        text += page_note(page, total, len(shown))
    body = pack(
        "template",
        text,
        template_id=template_id,
        summary=summary,
        filters=filters,
        exclusions=exclusions,
        assumptions=assumptions,
        columns=columns,
        rows=shown,
        total=total,
        page=page,
        sql=page_sql,
        period=period,
    )
    body["_sql"] = page_sql
    return body
