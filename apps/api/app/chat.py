"""Chat orchestration: refuse, clarify, template, or dynamic SQL."""

from __future__ import annotations

import logging
import re
import time
import uuid

from psycopg.types.json import Json

from app.agent import run_dynamic
from app.catalog import KNOWN_TEMPLATE_IDS
from app.db import admin_conn, reader_conn
from app.emailer import is_email_request
from app.pack import filters_for, pack
from app.query import fetch_all, json_cell
from app.review import lookup_approved, note_for_review, run_approved
from app.router import assume_after_limit, classify, out_of_scope_reason
from app.service import run_template
from app.trace import record_trace

log = logging.getLogger("lia.chat")
_NAMES: dict[str, list[str]] = {}
_PRONOUN = re.compile(r"\b(her|his|their|hers|she|he)\b", re.I)


def remember_person(message: str, state: dict) -> str:
    """A follow-up like 'show her timetable' keeps the person from the previous turn."""
    name = str((state or {}).get("last_person_name") or "").strip()
    if not name or name.lower() in message.lower() or not _PRONOUN.search(message):
        return message
    return f"{message} for {name}"


def _names(conn, persona: str) -> list[str]:
    if persona not in _NAMES:
        rows, _sql = _rows(
            conn,
            """
            SELECT name, school_name FROM (
                SELECT name, home_department AS school_name FROM staff
            ) AS scoped
            ORDER BY name
            """,
            persona,
        )
        _NAMES[persona] = [row["name"] for row in rows]
    return _NAMES[persona]


def _rows(conn, sql: str, persona: str):
    _columns, rows, _total, page_sql = fetch_all(conn, sql, persona)
    return rows, page_sql


def _state(conn, thread_id: str) -> dict:
    row = conn.execute("SELECT state FROM chat_threads WHERE thread_id = %s", (thread_id,)).fetchone()
    if not row:
        return {"clarify_count": 0, "pending": None, "last_answer": ""}
    return row["state"] or {"clarify_count": 0, "pending": None, "last_answer": ""}


def _save(conn, thread_id: str, persona: str, state: dict, draft: str | None = None):
    conn.execute(
        """
        INSERT INTO chat_threads (thread_id, persona, state)
        VALUES (%s, %s, %s)
        ON CONFLICT (thread_id) DO UPDATE
        SET persona = EXCLUDED.persona, state = EXCLUDED.state, updated_at = now()
        """,
        (thread_id, persona, Json(state)),
    )
    if draft is not None:
        conn.execute(
            """
            INSERT INTO email_drafts (thread_id, subject, body)
            VALUES (%s, 'LIA utilisation draft', %s)
            ON CONFLICT (thread_id) DO UPDATE
            SET body = EXCLUDED.body, created_at = now(), sent_at = NULL
            """,
            (thread_id, draft),
        )


def _attach(result: dict, data_as_of: str | None, thread_id: str):
    sql = result.pop("_sql", None)
    result["thread_id"] = thread_id
    result["data_as_of"] = data_as_of
    result.setdefault("how_i_got_this", {})["data_as_of"] = data_as_of
    return result, sql


def _refuse(reason: str, persona: str):
    body = pack(
        "refuse",
        reason,
        template_id=None,
        summary="Refused before SQL because the question is out of scope.",
        filters=[f"persona={persona}"],
        exclusions=["No database query was run."],
        assumptions=[],
        columns=[],
        rows=[],
        total=0,
        page=1,
        sql=None,
        period="not queried",
    )
    body["_sql"] = None
    return body


def _clarify(decision, persona: str):
    text = decision.clarifying_question or "Which of these do you mean?"
    body = pack(
        "clarify",
        text,
        template_id=None,
        summary="One clarifying question, with touch options.",
        filters=filters_for(persona, decision.slots),
        exclusions=["No metric was calculated before the choice."],
        assumptions=[],
        columns=[],
        rows=[],
        total=0,
        page=1,
        sql=None,
        clarifying_question={
            "text": text,
            "options": [{"id": opt.id, "label": opt.label} for opt in decision.options],
        },
    )
    body["_sql"] = None
    return body


def _draft(thread_id: str, state: dict, persona: str):
    body_text = state.get("last_answer") or "No previous answer is stored on this thread."
    draft = f"Persona: {persona}\n\n{body_text}"
    body = pack(
        "clarify",
        "A draft was stored. Nothing was sent. Use the send action to confirm.",
        template_id=None,
        summary="Email draft stored. SMTP was not contacted.",
        filters=[f"persona={persona}"],
        exclusions=["Email is not sent without the confirm endpoint."],
        assumptions=[],
        columns=[],
        rows=[],
        total=0,
        page=1,
        sql=None,
        clarifying_question={
            "text": "Send the stored draft to the data owner?",
            "options": [
                {"id": "confirm-email", "label": "Send email"},
                {"id": "cancel-email", "label": "Don't send"},
            ],
        },
    )
    body["_sql"] = None
    body["_draft"] = draft
    return body


def handle_chat(message: str, persona: str, thread_id: str | None, page: int, template_id: str | None) -> dict:
    started = time.perf_counter()
    thread_id = thread_id or str(uuid.uuid4())
    page = max(1, int(page or 1))
    message = (message or "").strip()[:2000]
    sql = None
    result: dict
    try:
        with reader_conn() as conn:
            version = conn.execute("SELECT loaded_at FROM data_version WHERE id = 1").fetchone()
            data_as_of = json_cell(version["loaded_at"]) if version else None
            names = _names(conn, persona)
            with admin_conn() as admin:
                state = _state(admin, thread_id)
                message = remember_person(message, state)
                if out_of_scope_reason(message):
                    decision = classify(message, persona=persona, names=names)
                    result = _refuse(decision.reason or "Out of scope.", persona)
                elif template_id is None and not state.get("pending") and is_email_request(message):
                    result = _draft(thread_id, state, persona)
                else:
                    if template_id and template_id not in KNOWN_TEMPLATE_IDS:
                        result = _refuse("That template is not in the catalog.", persona)
                    else:
                        decision = classify(
                            message,
                            persona=persona,
                            names=names,
                            pending=state.get("pending"),
                            template_id=template_id,
                        )
                        assumed = False
                        decision = assume_after_limit(decision, int(state.get("clarify_count") or 0))
                        if decision.reason == "assumed after two clarifying questions":
                            assumed = True
                        if decision.route == "refuse":
                            result = _refuse(decision.reason or "Out of scope.", persona)
                        elif decision.route == "clarify":
                            state["clarify_count"] = int(state.get("clarify_count") or 0) + 1
                            state["pending"] = {
                                "question": decision.clarifying_question,
                                "options": [opt.as_dict() for opt in decision.options],
                            }
                            result = _clarify(decision, persona)
                        elif decision.route == "dynamic":
                            state["pending"] = None
                            saved = lookup_approved(admin, message)
                            if saved:
                                result = run_approved(conn, saved, persona, page)
                            else:
                                result = run_dynamic(message, persona, page, conn)
                                review = note_for_review(admin, message, result.get("_model_sql"), result.get("answer") or "")
                                if review:
                                    result["review"] = review
                                    if review["status"] == "pending_owner_review":
                                        result["answer"] = f"For owner review. {result.get('answer', '')}"
                                        result.setdefault("how_i_got_this", {}).setdefault("assumptions", []).append(
                                            "This question is not a reviewed template until a university user approves it."
                                        )
                        else:
                            state["pending"] = None
                            state["clarify_count"] = 0
                            result = run_template(decision.template_id, decision.slots, persona, page, conn)
                            if assumed:
                                note = (
                                    "Two clarifying questions were already asked, "
                                    "so LIA used the first option and answered."
                                )
                                result["answer"] = f"{note} {result.get('answer', '')}"
                                how = result.setdefault("how_i_got_this", {})
                                how.setdefault("assumptions", []).append(note)
                            person = getattr(decision.slots, "person_name", None)
                            if person:
                                state["last_person_name"] = person
                state["last_answer"] = result.get("answer")
                _save(admin, thread_id, persona, state, result.pop("_draft", None))
                admin.commit()
        result, sql = _attach(result, data_as_of, thread_id)
    except Exception:
        log.exception("chat failed")
        result = _refuse("The question could not be answered from the loaded extracts.", persona)
        result, sql = _attach(result, None, thread_id)
        result["route"] = "missing_data"
    record_trace(
        {
            "thread_id": thread_id,
            "persona": persona,
            "route": result.get("route"),
            "template_id": (result.get("how_i_got_this") or {}).get("sql_or_template_id"),
            "sql": sql,
            "row_count": (result.get("table") or {}).get("total_count"),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "data_version": result.get("data_as_of"),
            "message": message[:500],
        }
    )
    return result


def load_draft(thread_id: str) -> str | None:
    with admin_conn() as conn:
        row = conn.execute("SELECT body FROM email_drafts WHERE thread_id = %s", (thread_id,)).fetchone()
        return row["body"] if row else None


def mark_sent(thread_id: str) -> None:
    with admin_conn() as conn:
        conn.execute("UPDATE email_drafts SET sent_at = now() WHERE thread_id = %s", (thread_id,))
        conn.commit()
