"""LangGraph dynamic SQL path. Numbers in the answer are copied from the result grid."""

from __future__ import annotations

import re
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.catalog import suggest_questions
from app.guard import ALLOWLIST, prepare
from app.llm import NO_MODEL_ANSWER, complete, provider_order
from app.pack import pack
from app.query import run_sql
from app.retrieve import search


class State(TypedDict, total=False):
    question: str
    persona: str
    page: int
    context: str
    sql: str
    error: str
    repaired: bool
    fallback: bool
    columns: list
    rows: list
    total: int
    answer: str
    page_sql: str


def _extract_sql(text: str) -> str:
    fenced = re.search(r"```sql\s*(.*?)```", text, re.I | re.S)
    if fenced:
        return fenced.group(1).strip().rstrip(";")
    match = re.search(r"(?is)\b(with|select)\b.*", text)
    return (match.group(0) if match else text).strip().rstrip(";")


_SCHEMA = """
timetable_slots(day, period_name, from_time, to_time, location, subject_code, subject_name, staff_code, staff_name, section, semester, program, school_name, degree, session_type, enrollments, start_date, end_date)
timetable_detail includes section. A section id looks like BTCSE1-S1 or BALA1-S1-P1. Filter timetable_detail.section for a section timetable. Do not use a section id as a room number.
faculty_workload(staff_id, name, designation, school_name, lecture_hours, practical_hours, tutorial_hours, teaching_hours, effective_mandate, actual_hours, status, pct_of_mandate)
room_utilisation(room_number, school_name, seating_capacity, scheduled_hours, busy_pct, avg_occupancy_pct)
Example: SELECT school_name, count(DISTINCT program) AS program_count FROM timetable_slots GROUP BY school_name
Example: SELECT school_name, count(*) AS slot_rows FROM timetable_slots GROUP BY school_name
""".strip()


def _prompt(question: str, context: str, error: str = "", previous: str = "") -> str:
    views = ", ".join(sorted(ALLOWLIST))
    repair = f"\nThe previous SELECT failed: {error}\nSQL:\n{previous}\nWrite a corrected SELECT using only the columns above.\n" if error else ""
    return (
        "Write one PostgreSQL SELECT inside a ```sql fence and no other prose. "
        f"Use only these relations: {views}. "
        "Copy column names from the schema. GROUP BY every selected column that is not aggregated. "
        "Every timetable row is 1 hour. Room busy percent is scheduled_hours / 45. "
        "Do not join staff_load_extract to staff by name. "
        "Do not invent columns. "
        "Include school_name in the outer SELECT so a dean filter can be applied by the server. "
        "No INSERT, no UPDATE, no DELETE.\n"
        f"Schema:\n{_SCHEMA}\n"
        f"Context:\n{context}\n{repair}Question: {question}"
    )


def _grid(columns: list[str], rows: list[dict], total: int) -> str:
    if total == 0:
        return "The query returned 0 rows."
    shown = len(rows)
    preview = " | ".join(", ".join(f"{col}={row.get(col)}" for col in columns) for row in rows)
    note = f" This page shows {shown} of {total}, not the full set." if total > shown else ""
    return f"The query returned {total} rows.{note} {preview}".strip()


def _graph(conn):
    graph = StateGraph(State)

    def retrieve(state: State) -> dict:
        docs = search(state["question"])
        text = "\n".join(f"{doc.get('title', '')}: {doc.get('text', '')}" for doc in docs)
        return {"context": text[:4000]}

    def draft(state: State) -> dict:
        if not provider_order():
            return {"fallback": True}
        text = complete(_prompt(state["question"], state.get("context") or ""))
        if not text:
            return {"fallback": True}
        return {"sql": _extract_sql(text), "fallback": False, "error": ""}

    def guard(state: State) -> dict:
        if state.get("fallback"):
            return {}
        try:
            _count, page_sql = prepare(state.get("sql") or "", state["persona"], page=state.get("page") or 1)
            return {"page_sql": page_sql, "error": ""}
        except Exception as exc:
            return {"error": str(exc)[:400]}

    def execute(state: State) -> dict:
        if state.get("fallback") or state.get("error"):
            return {}
        try:
            columns, rows, total, page_sql = run_sql(conn, state["sql"], state["persona"], page=state.get("page") or 1)
            return {"columns": columns, "rows": rows, "total": total, "page_sql": page_sql, "error": ""}
        except Exception as exc:
            return {"error": str(exc)[:400]}

    def repair(state: State) -> dict:
        text = complete(_prompt(state["question"], state.get("context") or "", state.get("error") or "", state.get("sql") or ""))
        if not text:
            return {"repaired": True, "fallback": True}
        return {"sql": _extract_sql(text), "repaired": True, "error": "", "fallback": False}

    def phrase(state: State) -> dict:
        if state.get("fallback") or not state.get("sql"):
            return {"answer": NO_MODEL_ANSWER, "rows": [], "columns": [], "total": 0, "page_sql": None}
        if state.get("error"):
            return {"answer": "The query could not be completed, so no figure is reported."}
        return {"answer": _grid(state.get("columns") or [], state.get("rows") or [], int(state.get("total") or 0))}

    def after_guard(state: State) -> str:
        if state.get("fallback"):
            return "phrase"
        if state.get("error"):
            if not state.get("repaired") and provider_order():
                return "repair"
            return "phrase"
        return "execute"

    def after_execute(state: State) -> str:
        if state.get("error") and not state.get("repaired") and provider_order():
            return "repair"
        return "phrase"

    graph.add_node("retrieve", retrieve)
    graph.add_node("draft", draft)
    graph.add_node("guard", guard)
    graph.add_node("execute", execute)
    graph.add_node("repair", repair)
    graph.add_node("phrase", phrase)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "draft")
    graph.add_edge("draft", "guard")
    graph.add_conditional_edges("guard", after_guard)
    graph.add_conditional_edges("execute", after_execute)
    graph.add_edge("repair", "guard")
    graph.add_edge("phrase", END)
    return graph.compile()


def run_dynamic(question: str, persona: str, page: int, conn) -> dict:
    state = _graph(conn).invoke(
        {"question": question, "persona": persona, "page": page, "repaired": False, "fallback": False}
    )
    fallback = bool(state.get("fallback") or not state.get("sql"))
    answer = state.get("answer") or NO_MODEL_ANSWER
    rows = [] if fallback else (state.get("rows") or [])
    columns = [] if fallback else (state.get("columns") or [])
    total = 0 if fallback else int(state.get("total") or 0)
    sql = None if fallback else state.get("page_sql")
    body = pack(
        "dynamic",
        answer,
        template_id=None,
        summary="No model is configured." if fallback else "Dynamic SELECT, with numbers copied from the result grid.",
        filters=[f"persona={persona}"],
        exclusions=["The model does not invent figures."],
        assumptions=["Only an allowlisted SELECT can run.", "The dean school predicate is injected after parsing."],
        columns=columns,
        rows=rows,
        total=total,
        page=page,
        sql=sql,
        suggestions=suggest_questions(question),
    )
    body["_sql"] = sql
    body["_model_sql"] = None if fallback else state.get("sql")
    return body
