"""Run a reviewed template against the reader connection."""

from __future__ import annotations

from app.execute import execute
from app.narratives import NARRATIVES
from app.pack import WORKLOAD_EXCLUSIONS, visible_rows
from app.query import fetch_all
from app.sql_library import (
    avg_rank_sql,
    busiest_days_sql,
    busiest_rooms_sql,
    clash_sql,
    excluded_count_sql,
    five_days_sql,
    gap_sql,
    large_low_sql,
    long_day_sql,
    low_busy_sql,
    low_occupancy_sql,
    subject_load_sql,
    subject_teachers_sql,
    under_sql,
    weeks_sql,
)


def _one(conn, sql, persona):
    _columns, rows, _total, _sql = fetch_all(conn, sql, persona)
    return visible_rows(rows, persona)


def _under_answer(conn, persona):
    def answer(rows, _shown, total):
        excluded = _one(conn, excluded_count_sql(), persona)
        extra = ""
        if excluded:
            extra = (
                f" {excluded[0]['excluded_people']} people in this view are outside the five mandated "
                "designations and are excluded."
            )
        return (
            f"{total} eligible faculty are under the effective mandate "
            "(actual weekly timetable hours below mandate minus relaxation). "
            "Visiting faculty, lab assistants, and lab technicians are excluded. "
            "Mandates: Professor & Dean 4, Professor 10, Associate Professor 12, "
            "Assistant Professor 14, PhD Scholar 8. "
            "Relaxation is 0 because the staff_load extract does not join this staff master. "
            "PhD hours are 0 unless the staff id is in the supervision extract. "
            "Experiential hours are excluded."
            + extra
        )
    return answer


def _over_answer(total_rows, _shown, total):
    return (
        f"{total} eligible faculty are over-loaded: actual weekly timetable hours are above the effective mandate. "
        "Visiting faculty, lab assistants, and lab technicians are excluded. "
        "Effective mandate equals the designation mandate minus relaxation, and relaxation is 0 in Universe A. "
        "Experiential hours are excluded. PhD hours are 0 unless the staff id is in the supervision extract."
    )


def _list_specs(conn, persona):
    return {
        "faculty_under_list": (under_sql, _under_answer(conn, persona), "Eligible faculty under the effective mandate."),
        "faculty_over_list": (lambda slots: under_sql(slots, "over"), _over_answer, "Eligible faculty over the effective mandate."),
    }


def run_template(template_id, slots, persona, page, conn):
    if template_id in NARRATIVES:
        return NARRATIVES[template_id](slots, persona, page, conn)
    specs = _list_specs(conn, persona)
    if template_id not in specs and template_id not in _STATIC:
        raise KeyError(template_id)
    if template_id in specs:
        sql_fn, answer, summary = specs[template_id]
        return execute(
            conn, sql_fn(slots), slots, persona, page, template_id, summary, answer,
            WORKLOAD_EXCLUSIONS,
            ["Each timetable row is 1 hour.", "School is the staff home department.", "Universe A only."],
        )
    sql_fn, answer, summary, exclusions, assumptions = _STATIC[template_id]
    return execute(
        conn, sql_fn(slots), slots, persona, page, template_id, summary, answer, exclusions, assumptions,
    )


def _static_answer(prefix):
    def answer(rows, _shown, total):
        head = ""
        if rows and "teaching_hours" in rows[0] and "day" in rows[0]:
            head = f"{rows[0]['day']} has the most teaching hours in this view: {rows[0]['teaching_hours']}. "
        elif rows and "subject_name" in rows[0] and "teaching_hours" in rows[0]:
            head = f"Highest in this view: {rows[0]['subject_name']} with {rows[0]['teaching_hours']} timetable hours. "
        elif rows and "room_number" in rows[0] and "scheduled_hours" in rows[0] and "busy_pct" in rows[0]:
            head = (
                f"The busiest room in this ordered list is {rows[0]['room_number']} "
                f"with {rows[0]['scheduled_hours']} scheduled hours ({rows[0]['busy_pct']} busy percent). "
            )
        return prefix.format(total=total) + head
    return answer


_STATIC = {}


def _register_static():
    common_room = [
        "Busy percent is scheduled hours divided by 45 (9 periods x 5 days).",
        "Each timetable row is 1 hour.",
    ]
    items = {
        "long_day": (
            long_day_sql,
            lambda rows, _s, total: (
                f"No faculty member teaches more than 5 hours on a single day. The comparison is strict. Each timetable row is 1 hour."
                if total == 0
                else f"{total} faculty-day rows are over the strict hourly threshold. Each timetable row is 1 hour."
            ),
            "Faculty-day timetable hours compared with a strict threshold.",
            ["Rows at exactly 5 hours are not included."],
            ["Each timetable row is 1 hour."],
        ),
        "five_days": (
            lambda _s: five_days_sql(),
            lambda rows, _s, total: f"{total} faculty teach on all five weekdays in this view.",
            "Distinct weekdays with at least one timetable row.",
            [],
            ["The loaded pattern is Monday–Friday."],
        ),
        "subject_load": (
            lambda _s: subject_load_sql(),
            _static_answer("{total} subjects are ranked by timetable hours. Each row is 1 hour. "),
            "Subject load is the count of timetable rows.",
            [],
            ["Each timetable row is 1 hour.", "This page is not every subject when the total is larger."],
        ),
        "subject_teachers": (
            lambda slots: subject_teachers_sql(slots),
            lambda rows, _s, total: f"{total} faculty rows match that subject name on the timetable.",
            "Subject name search on the timetable, not the LTPE extract.",
            [],
            ["Match is a case-insensitive substring of the timetable subject name."],
        ),
        "busiest_days": (
            lambda _s: busiest_days_sql(),
            _static_answer("Days are ranked by total scheduled teaching hours. Each timetable row is 1 hour. "),
            "Busiest day means the most timetable hours.",
            [],
            ["Each timetable row is 1 hour."],
        ),
        "avg_load_by_rank": (
            lambda _s: avg_rank_sql(),
            lambda rows, _s, total: (
                f"{total} designations are listed. Average load is the mean of weekly timetable hours per person "
                "on the staff master, including people with zero hours. Mandate is populated only for the five "
                "eligible designations. Visiting faculty, lab assistants, and lab technicians have no mandate in this table."
            ),
            "Mean weekly timetable hours by designation.",
            WORKLOAD_EXCLUSIONS,
            ["People with no timetable rows count as zero hours."],
        ),
        "rooms_low_busy": (
            low_busy_sql,
            lambda rows, _s, total: (
                f"{total} rooms are under the busy threshold. Busy percent is scheduled hours / 45. "
                "Rooms with no bookings are 0% and are included."
            ),
            "Rooms whose scheduled hours are under the busy threshold.",
            [],
            common_room,
        ),
        "busiest_rooms": (
            lambda _s: busiest_rooms_sql(),
            _static_answer("Rooms are ordered by scheduled hours. Busy percent is scheduled hours / 45. "),
            "Busiest rooms by scheduled hours.",
            [],
            common_room,
        ),
        "rooms_low_occupancy": (
            low_occupancy_sql,
            lambda rows, _s, total: (
                f"{total} rooms with at least one meeting average under the occupancy threshold. "
                "Seat occupancy for a room is the average of enrolment / seating capacity across that room's timetable rows. "
                "Rooms with no meetings are omitted because occupancy is undefined."
            ),
            "Average seat occupancy across a room's timetable rows.",
            [],
            ["Grain: one ratio per timetable row, then the average for the room."],
        ),
        "rooms_large_low_occupancy": (
            lambda _s: large_low_sql(),
            lambda rows, _s, total: (
                f"{total} rooms are large and have low seat occupancy. "
                "Large means seating capacity of at least 100. Low means average occupancy under 50%. "
                "Occupancy is the average of enrolment / seating capacity across the room's timetable rows."
            ),
            "Large rooms with average occupancy under 50%.",
            [],
            ["Large means seating capacity >= 100.", "Low means average occupancy < 50%."],
        ),
        "staff_clashes": (
            lambda _s: clash_sql("staff"),
            lambda rows, _s, total: (
                "The clash query returned 0 faculty booked in two places at once."
                if total == 0
                else f"The clash query returned {total} faculty double-bookings."
            ),
            "Staff booked more than once in the same day and period.",
            [],
            ["A clash is two timetable rows for the same staff id, day, and period."],
        ),
        "room_clashes": (
            lambda _s: clash_sql("room"),
            lambda rows, _s, total: (
                "The clash query returned 0 double-booked rooms."
                if total == 0
                else f"The clash query returned {total} double-booked room periods."
            ),
            "Rooms booked more than once in the same day and period.",
            [],
            ["A clash is two timetable rows for the same room, day, and period."],
        ),
        "timetable_faculty_missing": (
            lambda _s: gap_sql("staff"),
            lambda rows, _s, total: (
                "The query found no timetable faculty missing from the staff master."
                if total == 0
                else f"The query found {total} timetable staff ids missing from the staff master."
            ),
            "Timetable staff ids with no staff-master row.",
            [],
            ["The query was run even though the mock is expected to match."],
        ),
        "timetable_rooms_missing": (
            lambda _s: gap_sql("room"),
            lambda rows, _s, total: (
                "The query found no timetable rooms missing from the room master."
                if total == 0
                else f"The query found {total} timetable rooms missing from the room master."
            ),
            "Timetable room numbers with no room-master row.",
            [],
            ["The query was run even though the mock is expected to match."],
        ),
        "weeks_loaded": (
            lambda _s: weeks_sql(),
            lambda rows, _s, total: _weeks_text(rows, total),
            "Distinct timetable start and end dates.",
            [],
            ["This is the only loaded window. It is not renamed to a prior week."],
        ),
    }
    _STATIC.update(items)


def _weeks_text(rows, total):
    if not rows:
        return "The timetable query returned no dated rows in this view."
    windows = ", ".join(f"{row['start_date']} to {row['end_date']} ({row['slots']} slots)" for row in rows)
    only = "Only one window is loaded. " if total == 1 else f"{total} windows were returned. "
    return only + "Loaded window: " + windows + "."


_register_static()
