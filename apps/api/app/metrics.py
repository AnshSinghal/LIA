"""Pure workload, room, and time rules. No database and no invented policy defaults."""

from __future__ import annotations

PERIODS: tuple[tuple[str, str, str], ...] = (
    ("Period - 1", "08:20", "09:20"),
    ("Period - 2", "09:25", "10:25"),
    ("Period - 3", "10:30", "11:30"),
    ("Period - 4", "11:35", "12:35"),
    ("Period - 5", "12:40", "13:40"),
    ("Period - 6", "13:45", "14:45"),
    ("Period - 7", "14:50", "15:50"),
    ("Period - 8", "15:55", "16:55"),
    ("Period - 9", "17:00", "18:00"),
)

MANDATES: dict[str, int] = {
    "Professor & Dean": 4,
    "Professor": 10,
    "Associate Professor": 12,
    "Assistant Professor": 14,
    "PhD Scholar": 8,
}

EXCLUDED_DESIGNATIONS = frozenset(
    {"Visiting Faculty", "Lab Assistant", "Lab Technician"}
)

WEEKLY_ROOM_HOURS = 45
LOADED_WINDOW = "17 Aug 2026 to 04 Sep 2026"
DEAN_SCHOOL = "School of Computer Science"

SCHOOL_ALIASES: tuple[tuple[str, str], ...] = (
    ("school of computer science", "School of Computer Science"),
    ("scset", "School of Computer Science"),
    ("school of artificial intelligence", "School of AI"),
    ("school of ai", "School of AI"),
    ("school of engineering", "School of Engineering"),
    ("school of liberal arts", "School of Liberal Arts"),
    ("school of management", "School of Management"),
    ("school of design", "School of Design"),
    ("school of media", "School of Media"),
    ("school of law", "School of Law"),
)

CANONICAL_SCHOOLS: tuple[str, ...] = tuple(dict.fromkeys(name for _, name in SCHOOL_ALIASES))


def mandate_hours(designation: str | None) -> int | None:
    if designation is None:
        return None
    return MANDATES.get(designation)


def effective_mandate(designation: str | None, relaxation_hours: float | None) -> float | None:
    """Effective mandate is mandate minus relaxation. Missing relaxation is 0, never 2."""
    base = mandate_hours(designation)
    if base is None:
        return None
    relaxation = 0 if relaxation_hours is None else float(relaxation_hours)
    return base - relaxation


def load_status(actual_hours: float, effective: float | None) -> str:
    if effective is None:
        return "not_eligible"
    if actual_hours < effective:
        return "under"
    if actual_hours > effective:
        return "over"
    return "met"


def supervision_hours(staff_id: str, scholars_by_staff_id: dict[str, int]) -> dict:
    """PhD hours apply only when the faculty id is in the supervision extract. Never match by name."""
    if staff_id not in scholars_by_staff_id:
        return {"scholars": 0, "hours": 0.0, "missing": True}
    scholars = int(scholars_by_staff_id[staff_id])
    return {"scholars": scholars, "hours": 0.25 * scholars, "missing": False}


def actual_weekly_hours(teaching_hours: float, phd_hours: float) -> float:
    """Experiential hours are not added. They cannot be computed from this mock."""
    return float(teaching_hours) + float(phd_hours)


def busy_pct(scheduled_hours: float, weekly_hours: int = WEEKLY_ROOM_HOURS) -> float:
    return round(100.0 * float(scheduled_hours) / float(weekly_hours), 1)


def meeting_occupancy_pct(enrolment: float, seating_capacity: float) -> float | None:
    if not seating_capacity:
        return None
    return round(100.0 * float(enrolment) / float(seating_capacity), 1)


def intervals_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    """Half-open intervals [start, end) overlap."""
    return start_a < end_b and start_b < end_a


def periods_overlapping(window_start: str, window_end: str) -> list[str]:
    return [
        name
        for name, start, end in PERIODS
        if intervals_overlap(start, end, window_start, window_end)
    ]


def section_enrolment_total(rows: list[tuple[str, str, float]]) -> float:
    """One enrolment per (school, section). Later rows do not add the same section again."""
    chosen: dict[tuple[str, str], float] = {}
    for school, section, enrolment in rows:
        chosen[(school, section)] = float(enrolment)
    return sum(chosen.values())


def row_enrolment_total(rows: list[tuple[str, str, float]]) -> float:
    return sum(float(enrolment) for _, _, enrolment in rows)


def proxy_comparison(kind: str) -> str:
    return (
        f"A comparison with a {kind} is not possible. "
        f"Only one timetable window is loaded: {LOADED_WINDOW}. "
        "The table is that loaded window, offered as a labelled proxy, "
        "and it is not a prior week, month, or semester."
    )


def sana_workload_text(row: dict) -> str:
    """Sentence built only from a result row. Callers pass query fields, not guessed totals."""
    actual = row["actual_hours"]
    mandate = row["effective_mandate"]
    status = row["status"]
    phrase = "over mandate" if status == "over" else ("under mandate" if status == "under" else "at mandate")
    return (
        f"{row['name']} (staff id {row['staff_id']}), {row['designation']} in {row['school_name']}, "
        f"has {actual} teaching hours this week against an effective mandate of {mandate}, so this is {phrase}. "
        f"PhD contribution is {row['phd_hours']} because the staff id is "
        f"{'absent from the supervision extract' if row['phd_missing'] else 'present in the supervision extract'}. "
        "Experiential hours are excluded because LTPE course codes do not match timetable subject codes. "
        f"Relaxation applied here is {row['relaxation_hours']}."
    )


def session_split_text(row: dict) -> str:
    return (
        f"Lecture {row['lecture_hours']}, practical {row['practical_hours']}, "
        f"tutorial {row['tutorial_hours']}."
    )
