"""FSR, LTPE, checks, and advice narratives."""

from __future__ import annotations

from app.execute import execute
from app.metrics import proxy_comparison
from app.pack import WORKLOAD_EXCLUSIONS, filters_for, pack, visible_rows
from app.query import fetch_all
from app.sql_library import (
    busiest_rooms_sql,
    fsr_phd_sql,
    fsr_sql,
    id_overlap_sql,
    large_low_sql,
    ltpe_name_sql,
    ltpe_overlap_sql,
    ltpe_practical_sql,
    proxy_sql,
    room_stats_sql,
    school_summary_sql,
    seat_stats_sql,
)

ASSUME = ["Each timetable row is 1 hour.", "Universe A relaxation is 0 because staff_load does not join."]


def _all(conn, sql, persona):
    _columns, rows, _total, page_sql = fetch_all(conn, sql, persona)
    return visible_rows(rows, persona), page_sql

def _fsr(slots, persona, page, conn):
    def answer(rows, _shown, total):
        lines = [
            "The numerator is one enrolment per section.",
            "A lecture section and its practical batch are different section ids, so a person can be counted twice.",
            "The denominator is staff in Teaching or Administrative & Teaching whose designation is not PhD Scholar, by home department.",
            "Enrolment was not summed on every timetable row.",
        ]
        for row in rows:
            if row["school_name"] == "School of Computer Science":
                lines.append(
                    f"School of Computer Science section enrolment is {row['section_students']}. "
                    f"Summing every timetable row would show {row['row_sum_enrolment']} and is not used. "
                    f"Baseline ratio {row['baseline_ratio']} is {row['section_students']} / {row['faculty_count']}."
                )
        if total <= 20:
            lines.append("Every school in this view is listed.")
        return " ".join(lines)
    return execute(conn, fsr_sql(), slots, persona, page, "faculty_student_ratio", "Section enrolment over teaching staff.", answer,
                   ["PhD scholars with that staff designation are not in the denominator."], ["Section grain, not timetable-row grain."])


def _fsr_phd(slots, persona, page, conn):
    def answer(rows, _shown, total):
        bits = []
        for row in rows:
            bits.append(
                f"{row['school_name']}: (1) baseline ratio {row['baseline_ratio']} "
                f"({row['section_students']} section enrolments / {row['faculty_count']} faculty). "
                f"(2) baseline students plus {row['full_time_scholars_in_supervision_extract']} full-time scholars "
                f"from the supervision extract gives ratio {row['ratio_if_students_plus_full_time_scholars']}. "
                f"Separately, adding {row['staff_phd_scholars']} staff-designation PhD scholars to the faculty denominator "
                f"gives {row['ratio_with_staff_phd_in_denominator']}. These extracts are not joined."
            )
        if total <= 20:
            bits.append("Every school in this view is listed.")
        return " ".join(bits)
    return execute(conn, fsr_phd_sql(), slots, persona, page, "faculty_student_ratio_phd",
                   "Baseline ratio, supervision-extract scholars, and staff-designation PhD scholars, labelled separately.",
                   answer, ["The supervision extract is not joined to the staff master by name or id."], ["Full-time scholars are added only to the student count."])


def _proxy(template_id, kind):
    def handler(slots, persona, page, conn):
        body = execute(
            conn, proxy_sql(), slots, persona, page, template_id,
            "Loaded-window hours only.",
            lambda rows, _s, total: proxy_comparison(kind) + " The table is eligible teaching hours and effective mandate for that loaded window.",
            ["There is no earlier week, month, or semester in the extract."],
            ["Eligible faculty only.", "Relaxation is 0 in Universe A.", "Email is offered and is not sent until a separate confirm step."],
        )
        body["clarifying_question"] = {
            "text": "Email the data owner to ask for the missing period? Nothing is sent until you confirm.",
            "options": [
                {"id": "request-email", "label": "Email the data owner"},
                {"id": "keep-proxy", "label": "Keep this loaded window"},
            ],
        }
        return body
    return handler


def _ltpe(template_id, sql_fn, empty_note, found_note):
    def handler(slots, persona, page, conn):
        overlap, _sql = _all(conn, ltpe_overlap_sql(), persona)
        overlap_n = overlap[0]["timetable_code_overlap"] if overlap else 0

        def answer(rows, _shown, total):
            if total == 0:
                return (
                    f"{empty_note} Timetable subject-code overlap with LTPE ids in this view is {overlap_n}. "
                    "Department names were not fuzzy-matched."
                )
            return found_note.format(total=total, overlap=overlap_n)
        return execute(conn, sql_fn(slots), slots, persona, page, template_id, "LTPE extract, not the timetable.", answer,
                       ["LTPE course codes do not join to timetable subject codes."], ["L lecturer, T tutorial, P practical, E skill hours."])
    return handler


def _inactive(slots, persona, page, conn):
    rows = [
        {"column_name": row["column_name"]}
        for row in conn.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'staff'
            ORDER BY ordinal_position
            """
        )
    ]
    names = ", ".join(row["column_name"] for row in rows)
    sql = "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'staff'"
    body = pack(
        "missing_data",
        "This cannot be answered. The staff extract has no active-status column. "
        f"Columns present: {names}. Inactive faculty who are still teaching cannot be identified.",
        template_id="inactive_staff",
        summary="The staff extract has no active flag.",
        filters=filters_for(persona, slots),
        exclusions=["No active or inactive status is stored."],
        assumptions=["The column list was read from the loaded staff table."],
        columns=["column_name"], rows=rows, total=len(rows), page=1, sql=sql,
    )
    body["_sql"] = sql
    return body


def _advice_room(slots, persona, page, conn):
    stats, _sql = _all(conn, room_stats_sql(), persona)
    top, _top_sql = _all(conn, busiest_rooms_sql(), persona)
    stat = stats[0] if stats else {"rooms": 0, "below_20": 0, "unused": 0}
    lead = ""
    if top:
        lead = (
            f"The busiest room in this view is {top[0]['room_number']} at {top[0]['scheduled_hours']} scheduled hours "
            f"({top[0]['busy_pct']} busy percent). "
        )
    text = (
        f"{stat['below_20']} of {stat['rooms']} rooms are under 20% busy, including {stat['unused']} with zero bookings. "
        "Consolidate meetings into rooms that are already partly used before opening an empty room. "
        + lead
        + "Busy percent is scheduled hours / 45. This answer does not invent a room-to-room move or a saved-hour figure."
    )
    return execute(conn, busiest_rooms_sql(), slots, persona, page, "advice_room_busy", "Room busy percent from the utilisation view.", lambda *_: text,
                   [], ["45-hour week.", "Each timetable row is 1 hour."])


def _advice_faculty(slots, persona, page, conn):
    schools, _sql = _all(conn, school_summary_sql(), persona)
    overlap_rows, _overlap_sql = _all(conn, id_overlap_sql(), persona)
    overlap = overlap_rows[0]["id_overlap"] if overlap_rows else 0
    if not schools:
        text = "No eligible faculty are in this view, so there is no load to rebalance."
    else:
        under = sum(row["under_count"] or 0 for row in schools)
        over = sum(row["over_count"] or 0 for row in schools)
        eligible = sum(row["eligible_faculty"] or 0 for row in schools)
        top_pct = max(schools, key=lambda row: ((row["under_pct"] or 0), row["under_count"] or 0))
        top_gap = max(schools, key=lambda row: ((row["gap_hours"] or 0), row["school_name"]))
        text = (
            f"1. {under} of {eligible} eligible faculty in this view are under the effective mandate and {over} are over it. "
            "Move timetable hours from over-mandate faculty toward under-mandate faculty in the same school. "
            f"2. The highest share under mandate is {top_pct['school_name']} at {top_pct['under_pct']}% "
            f"({top_pct['under_count']} of {top_pct['eligible_faculty']}). "
            f"The largest mandate-minus-actual gap is {top_gap['gap_hours']} hours in {top_gap['school_name']} "
            f"(actual {top_gap['actual_hours']}, mandate {top_gap['mandated_hours']}). "
            f"3. Do not apply staff_load relaxation to this timetable. Staff-id overlap with that extract is {overlap}. "
            "Experiential hours stay excluded."
        )
    return execute(conn, school_summary_sql(), slots, persona, page, "advice_faculty_load", "Advice from the eligible-faculty summary.", lambda *_: text, WORKLOAD_EXCLUSIONS, ASSUME)


def _advice_seat(slots, persona, page, conn):
    stats, _sql = _all(conn, seat_stats_sql(), persona)
    stat = stats[0] if stats else {"scheduled_rooms": 0, "below_50": 0, "large_low": 0}
    examples, _ex = _all(conn, large_low_sql(), persona)
    example = ""
    if examples:
        row = examples[0]
        example = (
            f" Example from the query: {row['room_number']} seats {row['seating_capacity']} "
            f"and averages {row['avg_occupancy_pct']}%."
        )
    text = (
        f"1. {stat['below_50']} rooms with meetings average under 50% seat occupancy "
        f"({stat['scheduled_rooms']} rooms have at least one meeting). "
        "Occupancy is the average of enrolment / seating capacity across that room's timetable rows. "
        f"2. {stat['large_low']} rooms with seating capacity of at least 100 are under 50%."
        + example
        + " 3. Place higher-enrolment sections in those large rooms and smaller sections in smaller rooms. "
        "A lecture section and its practical batch are different section ids."
    )
    return execute(conn, large_low_sql(), slots, persona, page, "advice_seat_occupancy", "Seat occupancy from timetable rows and room capacity.", lambda *_: text,
                   [], ["Large means capacity >= 100.", "Low means average occupancy < 50%."])


def _summary_room(slots, persona, page, conn):
    return _retarget(_advice_room(slots, persona, page, conn), "room_utilisation_summary")


def _retarget(body, template_id):
    body["how_i_got_this"]["sql_or_template_id"] = template_id + "\n" + body.get("_sql", "")
    return body


def _summary_seat(slots, persona, page, conn):
    return _retarget(_advice_seat(slots, persona, page, conn), "seat_occupancy_summary")

