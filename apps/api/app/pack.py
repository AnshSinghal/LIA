"""Response envelope shared by every route."""

from __future__ import annotations

from app.catalog import related
from app.metrics import DEAN_SCHOOL, LOADED_WINDOW

PAGE_SIZE = 20
PERIOD = (
    f"{LOADED_WINDOW}, one weekly pattern (Monday–Friday, nine periods). "
    "This is the only loaded window."
)
WORKLOAD_EXCLUSIONS = [
    "Experiential hours are excluded because LTPE course codes do not match timetable subject codes.",
    "PhD supervision hours count only when the staff id is in the supervision extract. People are not matched by name.",
    "Relaxation in Universe A is 0. The staff_load extract does not join this staff master, so a 2-hour relaxation is not applied.",
    "Visiting faculty, lab assistants, and lab technicians are outside the five mandated designations.",
]


def page_note(page: int, total: int, shown: int) -> str:
    if total > shown:
        return f" This page shows {shown} of {total} (page {page}), not the full set."
    return ""


def empty_table(page: int = 1) -> dict:
    return {"columns": [], "rows": [], "total_count": 0, "page": page, "page_size": PAGE_SIZE}


def slice_page(rows: list, page: int) -> list:
    start = max(page - 1, 0) * PAGE_SIZE
    return rows[start : start + PAGE_SIZE]


def visible_rows(rows: list[dict], persona: str) -> list[dict]:
    if persona != "dean_cs":
        return rows
    kept = []
    for row in rows:
        if "school_name" not in row:
            kept.append(row)
            continue
        if row.get("school_name") == DEAN_SCHOOL:
            kept.append(row)
    return kept


def scope_conflict(slots, persona: str) -> bool:
    school = getattr(slots, "school", None)
    return bool(school and persona == "dean_cs" and school != DEAN_SCHOOL)


def pack(
    route: str,
    answer: str,
    *,
    template_id: str | None,
    summary: str,
    filters: list[str],
    exclusions: list[str],
    assumptions: list[str],
    columns: list[str],
    rows: list[dict],
    total: int,
    page: int,
    sql: str | None,
    period: str = PERIOD,
    suggestions: list | None = None,
    clarifying_question: dict | None = None,
) -> dict:
    return {
        "route": route,
        "answer": answer,
        "how_i_got_this": {
            "summary": summary,
            "filters": filters,
            "period": period,
            "exclusions": exclusions,
            "assumptions": assumptions,
            "data_as_of": None,
            "sql_or_template_id": "\n".join(part for part in (template_id, sql) if part) or None,
        },
        "table": {
            "columns": columns,
            "rows": rows,
            "total_count": total,
            "page": page,
            "page_size": PAGE_SIZE,
        },
        "suggestions": suggestions if suggestions is not None else related(template_id),
        "clarifying_question": clarifying_question,
        "evidence": {
            "row_ids": _ids(rows),
            "counts": {"returned": len(rows), "total": total},
        },
    }


def _ids(rows: list[dict]) -> list[str]:
    found = []
    for row in rows:
        for key in ("staff_id", "room_number", "sno", "course_id", "entity_id", "staff_code"):
            if row.get(key) not in (None, ""):
                found.append(str(row[key]))
                break
    return found


def filters_for(persona: str, slots) -> list[str]:
    found = [f"persona={persona}"]
    if persona == "dean_cs":
        found.append("server injected school_name = School of Computer Science")
    school = getattr(slots, "school", None)
    if school:
        found.append(f"requested school={school}")
    person = getattr(slots, "person_name", None)
    if person:
        found.append(f"person={person}")
    room = getattr(slots, "room", None)
    if room:
        found.append(f"room={room}")
    section = getattr(slots, "section", None)
    if section:
        found.append(f"section={section}")
    if getattr(slots, "busy_below", None):
        found.append(f"busy_below={slots.busy_below}")
    if getattr(slots, "occupancy_below", None):
        found.append(f"occupancy_below={slots.occupancy_below}")
    if getattr(slots, "hour_threshold", None):
        found.append(f"hour_threshold={slots.hour_threshold}")
    if getattr(slots, "seat_count", None):
        found.append(f"seat_count={slots.seat_count}")
    return found


def conflict_answer(slots) -> str:
    return (
        f"{slots.school} is outside the School of Computer Science dean view, "
        "so no rows from that school are shown."
    )
