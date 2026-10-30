"""Unmatched questions stay labelled for owner review until a university user approves the SQL."""

from __future__ import annotations

import re

from app.agent import _grid
from app.pack import pack
from app.query import run_sql

_SPACE = re.compile(r"[^a-z0-9%]+")


def question_key(message: str) -> str:
    return _SPACE.sub(" ", message.lower()).strip()


def lookup_approved(conn, message: str) -> dict | None:
    row = conn.execute(
        """
        SELECT id, sql FROM approved_questions
        WHERE question_key = %s AND status = 'approved'
        """,
        (question_key(message),),
    ).fetchone()
    if not row:
        return None
    return {"id": int(row["id"]), "sql": row["sql"]}


def run_approved(conn, saved: dict, persona: str, page: int) -> dict:
    columns, rows, total, page_sql = run_sql(conn, saved["sql"], persona, page=page)
    body = pack(
        "template",
        _grid(columns, rows, total),
        template_id=f"approved:{saved['id']}",
        summary="Approved template. This question no longer calls the model.",
        filters=[f"persona={persona}"],
        exclusions=["The model does not invent figures."],
        assumptions=["The saved SELECT was approved by a university user."],
        columns=columns,
        rows=rows,
        total=total,
        page=page,
        sql=page_sql,
    )
    body["_sql"] = page_sql
    body["review"] = {"status": "approved", "id": saved["id"], "label": "Approved template"}
    return body


def note_for_review(conn, message: str, model_sql: str | None, answer: str) -> dict | None:
    if not model_sql or not model_sql.strip():
        return None
    lowered = answer.lower()
    if "no model is configured" in lowered or "could not be completed" in lowered:
        return None
    key = question_key(message)
    row = conn.execute(
        """
        INSERT INTO approved_questions (question_key, question, sql)
        VALUES (%s, %s, %s)
        ON CONFLICT (question_key) DO UPDATE
        SET ask_count = approved_questions.ask_count + 1,
            sql = CASE WHEN approved_questions.status = 'approved' THEN approved_questions.sql ELSE EXCLUDED.sql END,
            question = EXCLUDED.question,
            updated_at = now()
        RETURNING id, status, ask_count
        """,
        (key, message.strip()[:500], model_sql.strip()),
    ).fetchone()
    status = "approved" if row["status"] == "approved" else "pending_owner_review"
    label = "Approved template" if status == "approved" else "For owner review"
    return {"status": status, "id": int(row["id"]), "label": label, "ask_count": int(row["ask_count"])}


def approve(conn, review_id: int) -> dict:
    row = conn.execute(
        """
        UPDATE approved_questions
        SET status = 'approved', updated_at = now()
        WHERE id = %s
        RETURNING id, question
        """,
        (review_id,),
    ).fetchone()
    if not row:
        return {"ok": False, "error": "That review item does not exist."}
    return {"ok": True, "id": int(row["id"]), "question": row["question"]}
