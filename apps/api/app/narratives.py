"""Narrative templates whose answers cite specific result cells."""

from __future__ import annotations

from app.execute import execute
from app.metrics import proxy_comparison, sana_workload_text, session_split_text
from app.pack import WORKLOAD_EXCLUSIONS, filters_for, pack, visible_rows
from app.query import fetch_all, json_cell
from app.sql_library import (
    busiest_rooms_sql,
    fsr_phd_sql,
    fsr_sql,
    id_overlap_sql,
    large_low_sql,
    ltpe_name_sql,
    ltpe_overlap_sql,
    ltpe_practical_sql,
    meeting_sql,
    people_status_sql,
    person_timetable_sql,
    phd_top_sql,
    proxy_sql,
    relaxation_group_sql,
    room_stats_sql,
    room_timetable_sql,
    room_util_sql,
    section_timetable_sql,
    school_one_sql,
    school_summary_sql,
    seat_stats_sql,
    vacant_sql,
    free_sql,
    workload_sql,
)

ASSUME = ["Each timetable row is 1 hour.", "Universe A relaxation is 0 because staff_load does not join."]


def _all(conn, sql, persona):
    _columns, rows, _total, page_sql = fetch_all(conn, sql, persona)
    return visible_rows(rows, persona), page_sql


def _window(slots) -> str:
    periods = ", ".join(slots.overlapping_periods()) or "none"
    if slots.point:
        rule = f"{slots.day} at {slots.point}. A period overlaps when its half-open [from, to) interval contains that minute."
    else:
        rule = (
            f"{slots.day} from {slots.start} to {slots.end}. "
            "A period overlaps when its [from, to) interval overlaps this half-open range."
        )
    return f"{rule} Overlapping periods: {periods}."


def _need_window(slots, template_id):
    if slots.day and slots.start and slots.end:
        return None
    body = pack(
        "missing_data",
        "Name the day and clock range. A period counts when its interval overlaps that range.",
        template_id=template_id,
        summary="The clock window was not understood.",
        filters=filters_for("university", slots),
        exclusions=[],
        assumptions=[],
        columns=[],
        rows=[],
        total=0,
        page=1,
        sql=None,
    )
    body["_sql"] = None
    return body


def _require_person(conn, slots, persona, template_id):
    if not slots.person_name:
        body = pack(
            "missing_data",
            "Name the faculty member as it appears on the staff master.",
            template_id=template_id, summary="No person slot.", filters=filters_for(persona, slots),
            exclusions=[], assumptions=["Names are matched exactly against the staff master."],
            columns=[], rows=[], total=0, page=1, sql=None,
        )
        body["_sql"] = None
        return None, body
    from app.guard import sql_str
    sql = (
        "SELECT staff_id, name, designation, school_name FROM ("
        "SELECT staff_id, name, designation, home_department AS school_name FROM staff "
        f"WHERE lower(name) = lower({sql_str(slots.person_name)})"
        ") AS scoped"
    )
    rows, _page_sql = _all(conn, sql, persona)
    if not rows:
        body = pack(
            "missing_data",
            f"No staff row named {slots.person_name} is in this view. A similar name was not used.",
            template_id=template_id, summary="Person lookup missed in this persona view.",
            filters=filters_for(persona, slots), exclusions=["No fuzzy match across extracts."],
            assumptions=[], columns=[], rows=[], total=0, page=1, sql=sql,
        )
        body["_sql"] = sql
        return None, body
    if len(rows) > 1:
        ids = ", ".join(row["staff_id"] for row in rows)
        body = pack(
            "clarify",
            f"More than one staff row is named {slots.person_name}: {ids}.",
            template_id=template_id, summary="Ambiguous staff name.",
            filters=filters_for(persona, slots), exclusions=[], assumptions=[],
            columns=["staff_id", "name", "school_name"], rows=rows, total=len(rows), page=1, sql=sql,
        )
        body["_sql"] = sql
        return None, body
    return rows[0], None


def _workload(kind):
    def handler(slots, persona, page, conn):
        person, err = _require_person(conn, slots, persona, kind)
        if err:
            return err
        staff_id = person["staff_id"]

        def answer(rows, _shown, _total):
            if not rows:
                return "No workload row was returned for that staff id in this view."
            row = rows[0]
            if kind == "faculty_session_split":
                return session_split_text(row) + f" Total teaching hours {row['actual_hours']}."
            if kind == "faculty_pct_mandate":
                phrase = "over mandate" if row["status"] == "over" else (
                    "under mandate" if row["status"] == "under" else "at mandate"
                )
                return (
                    f"{row['actual_hours']} / {row['effective_mandate']} = {row['pct_of_mandate']}% "
                    f"of the effective mandate, which is {phrase}."
                )
            return sana_workload_text(row)

        return execute(
            conn, workload_sql(staff_id), slots, persona, page, kind,
            "One staff id from the staff master, hours from the timetable.",
            answer, WORKLOAD_EXCLUSIONS, ASSUME,
        )
    return handler


def _person_timetable(slots, persona, page, conn):
    person, err = _require_person(conn, slots, persona, "person_timetable")
    if err:
        return err

    def answer(rows, _shown, total):
        notes = []
        for row in rows:
            if row.get("day") == "Monday" and row.get("session_type") == "Lecture":
                notes.append(
                    f"{row['day']} {row['period_name']} in {row['room_number']} has enrolment "
                    f"{row['enrollments']} of capacity {row['seating_capacity']} "
                    f"({row['meeting_occupancy_pct']}% for that meeting)."
                )
        return f"{total} timetable rows for this staff id in the loaded week. " + " ".join(notes)

    return execute(
        conn, person_timetable_sql(person["staff_id"]), slots, persona, page, "person_timetable",
        "Timetable rows for one staff id.", answer, [], ["Each row is 1 hour.", "Ordered Monday–Friday."],
    )


def _room_timetable(slots, persona, page, conn):
    if not slots.room:
        body = pack("missing_data", "Name the room number.", template_id="room_timetable", summary="No room slot.",
                    filters=filters_for(persona, slots), exclusions=[], assumptions=[], columns=[], rows=[], total=0, page=1, sql=None)
        body["_sql"] = None
        return body
    util, _sql = _all(conn, room_util_sql(slots.room), persona)

    def answer(_rows, _shown, total):
        if not util:
            return f"Room {slots.room} is not in this view, so its timetable is not shown."
        row = util[0]
        return (
            f"Room {row['room_number']} is scheduled {row['scheduled_hours']} hours out of 45, "
            f"busy percent {row['busy_pct']}. The timetable has {total} rows."
        )

    return execute(
        conn, room_timetable_sql(slots.room), slots, persona, page, "room_timetable",
        "Room timetable plus busy percent from scheduled hours / 45.", answer, [],
        ["Busy percent uses 45 hours.", "Each timetable row is 1 hour."],
    )


def _section_timetable(slots, persona, page, conn):
    if not slots.section:
        body = pack(
            "missing_data",
            "Name the section id.",
            template_id="section_timetable",
            summary="No section slot.",
            filters=filters_for(persona, slots),
            exclusions=[],
            assumptions=[],
            columns=[],
            rows=[],
            total=0,
            page=1,
            sql=None,
        )
        body["_sql"] = None
        return body

    def answer(_rows, _shown, total):
        if total == 0:
            return f"Section {slots.section} is not in this view, so its timetable is not shown."
        return f"Section {slots.section} has {total} timetable rows in the loaded week."

    return execute(
        conn, section_timetable_sql(slots.section), slots, persona, page, "section_timetable",
        "Weekly timetable rows for one exact section id.",
        answer,
        [],
        [
            "Each timetable row is 1 hour.",
            "A lecture section and its practical or tutorial batch are different section ids.",
            "Ordered Monday–Friday.",
        ],
    )


def _free(slots, persona, page, conn):
    err = _need_window(slots, "free_people_and_rooms")
    if err:
        return err
    return execute(
        conn, free_sql(slots), slots, persona, page, "free_people_and_rooms",
        "Faculty and rooms with no overlapping timetable row.",
        lambda rows, _s, total: (
            f"{total} faculty and rooms have no overlapping booking. "
            "Faculty means staff in Teaching or Administrative & Teaching. " + _window(slots)
        ),
        [], ["A period overlaps the asked range when the half-open intervals overlap."],
    )


def _vacant(capacity: bool):
    template_id = "rooms_vacant_capacity" if capacity else "rooms_vacant"

    def handler(slots, persona, page, conn):
        err = _need_window(slots, template_id)
        if err:
            return err

        def answer(_rows, _shown, total):
            if capacity:
                head = f"{total} rooms with seating capacity {int(slots.seat_count or 60)} are vacant."
            else:
                head = f"{total} rooms are vacant."
            return head + " Vacant means no timetable row overlaps the window. " + _window(slots)

        return execute(
            conn, vacant_sql(slots, capacity), slots, persona, page, template_id,
            "Rooms with no overlapping booking.", answer, [], ["Half-open clock overlap."],
        )
    return handler


def _phd_person(slots, persona, page, conn):
    person, err = _require_person(conn, slots, persona, "phd_person")
    if err:
        return err
    from app.guard import sql_str
    sql = f"""
        SELECT count(*) AS scholars
        FROM (
            SELECT faculty_mapped_staff_id, school_name
            FROM phd_supervision_scoped
            WHERE faculty_mapped_staff_id = {sql_str(person['staff_id'])}
        ) AS scoped
    """

    def answer(rows, _shown, _total):
        scholars = rows[0]["scholars"] if rows else 0
        if not scholars:
            return (
                f"PhD supervision load is 0. Staff id {person['staff_id']} is absent from the supervision extract. "
                "The lookup used the staff id only, not the name."
            )
        return (
            f"Staff id {person['staff_id']} has {scholars} scholars in the supervision extract "
            f"({0.25 * scholars} hours at 0.25 each)."
        )

    return execute(conn, sql, slots, persona, page, "phd_person", "Supervision rows for one staff id.", answer,
                   ["Name matching was not used."], ["0.25 hours per scholar when the id is present."])


def _phd_top(slots, persona, page, conn):
    return execute(
        conn, phd_top_sql(), slots, persona, page, "phd_top",
        "Scholar counts from the supervision extract.",
        lambda rows, _s, total: (
            "The supervision extract has no rows in this view. People are not matched by name."
            if total == 0
            else f"{total} faculty are in the supervision extract for this view. Hours in the table are 0.25 per scholar."
        ),
        ["Universe A staff ids are not joined by name."], ["0.25 hours per supervised scholar."],
    )


def _justification(slots, persona, page, conn):
    person, err = _require_person(conn, slots, persona, "relaxation_justification")
    if err:
        return err
    columns = [
        row["column_name"]
        for row in conn.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'staff_load_extract'
            ORDER BY ordinal_position
            """
        )
    ]
    found = conn.execute(
        """
        SELECT staff_id, staff_name, hours_relaxation, mandated_hours
        FROM staff_load_extract WHERE staff_id = %s
        """,
        (person["staff_id"],),
    ).fetchall()
    rows = [{key: json_cell(value) for key, value in row.items()} for row in found]
    if rows:
        answer = f"A staff_load row exists for staff id {person['staff_id']}, but the extract has no justification column. Columns: {', '.join(columns)}."
    else:
        answer = (
            f"No staff_load row exists for staff id {person['staff_id']}. "
            f"Columns in that extract: {', '.join(columns)}. There is no justification column, so a reason cannot be quoted. "
            "The lookup used the staff id only."
        )
    sql = "SELECT staff_id, staff_name, hours_relaxation, mandated_hours FROM staff_load_extract WHERE staff_id = <resolved id>"
    body = pack(
        "missing_data" if not rows else "template", answer, template_id="relaxation_justification",
        summary="Staff id lookup in staff_load, after the persona-scoped staff master.",
        filters=filters_for(persona, slots) + [f"staff_id={person['staff_id']}"],
        exclusions=["No justification text exists in the extract.", "No match by name."],
        assumptions=["The staff id was resolved inside the persona view before this lookup."],
        columns=list(rows[0].keys()) if rows else ["column_name"],
        rows=rows or [{"column_name": name} for name in columns],
        total=len(rows or columns), page=1, sql=sql,
    )
    body["_sql"] = sql
    return body


def _relaxation_compare(slots, persona, page, conn):
    overlap_rows, _sql = _all(conn, id_overlap_sql(), persona)
    overlap = overlap_rows[0]["id_overlap"] if overlap_rows else 0

    def answer(rows, _shown, _total):
        if persona == "dean_cs":
            return (
                "The staff_load extract has no school attribute, so this comparison cannot be limited to the "
                "School of Computer Science without guessing. The rows are withheld. "
                f"Staff-id overlap with the staff master in this view is {overlap}, so actual timetable hours cannot be compared."
            )
        parts = [
            f"{row['grp']}: {row['people']} people, {row['with_mandate']} with a mandate value, average mandated hours {row['avg_mandated_hours']}"
            for row in rows
        ]
        return (
            " ".join(parts)
            + f" Staff-id overlap with the staff master is {overlap}, so actual timetable hours cannot be compared. "
            "The extract has no justification text. Relaxation values are not applied to Universe A."
        )

    return execute(
        conn, relaxation_group_sql(), slots, persona, page, "relaxation_compare",
        "Relaxation groups from staff_load only.", answer,
        ["Timetable hours are not invented for staff_load ids."], ["Universe B does not join Universe A."],
    )


def _school_gap(slots, persona, page, conn):
    def answer(rows, _shown, _total):
        if not rows:
            return "No school summary is in this view."
        top = max(rows, key=lambda row: ((row["gap_hours"] or 0), row["school_name"]))
        return (
            f"{top['school_name']} has the largest gap: {top['gap_hours']} hours "
            f"(effective mandate {top['mandated_hours']}, actual timetable hours {top['actual_hours']}). "
            "Gap is summed effective mandate minus summed actual hours for eligible faculty. "
            "A positive gap means the school is below mandate in aggregate. Relaxation is 0 in Universe A."
        )
    return execute(conn, school_summary_sql(), slots, persona, page, "school_gap", "School gap from eligible faculty.", answer, WORKLOAD_EXCLUSIONS, ASSUME)


def _school_hours(slots, persona, page, conn):
    if not slots.school:
        body = pack("clarify", "Which school?", template_id="school_hours", summary="School was not named.",
                    filters=filters_for(persona, slots), exclusions=[], assumptions=[], columns=[], rows=[], total=0, page=1, sql=None,
                    clarifying_question={"text": "Which school should the mandated and actual hours use?", "options": []})
        body["_sql"] = None
        return body

    def answer(rows, _shown, _total):
        if not rows:
            return "No mandated-hours summary was returned for that school in this view."
        row = rows[0]
        return (
            f"{row['school_name']}: total effective mandate {row['mandated_hours']} hours and actual teaching hours "
            f"{row['actual_hours']} for eligible faculty. Relaxation is 0 in Universe A."
        )
    return execute(conn, school_one_sql(slots.school), slots, persona, page, "school_hours", "Eligible mandate and actual hours for one school.", answer, WORKLOAD_EXCLUSIONS, ASSUME)


def _meeting(slots, persona, page, conn):
    def answer(rows, _shown, total):
        names = ", ".join(row["school_name"] for row in rows) or "none"
        return (
            "A school meets its mandated load when summed actual timetable hours of eligible faculty "
            "are at least the summed effective mandate. Effective mandate uses relaxation 0 in Universe A. "
            f"Schools meeting that test in this view: {names}."
        )
    return execute(conn, meeting_sql(), slots, persona, page, "schools_meeting", "Schools at or above summed effective mandate.", answer, WORKLOAD_EXCLUSIONS, ASSUME)


def _ranked_people(template_id, key):
    def handler(slots, persona, page, conn):
        schools, _sql = _all(conn, school_summary_sql(), persona)
        if not schools:
            body = pack("template", "No eligible faculty are in this view.", template_id=template_id,
                        summary="School summary was empty.", filters=filters_for(persona, slots),
                        exclusions=WORKLOAD_EXCLUSIONS, assumptions=ASSUME, columns=[], rows=[], total=0, page=1, sql=_sql)
            body["_sql"] = _sql
            return body
        if key == "pct":
            top = max(schools, key=lambda row: ((row["under_pct"] or 0), (row["under_count"] or 0), row["school_name"]))
            if persona == "dean_cs":
                prefix = (
                    f"Within the School of Computer Science view, {top['under_count']} of {top['eligible_faculty']} "
                    f"eligible faculty ({top['under_pct']}%) are under the effective mandate. "
                    "Other schools are outside this persona, so this is not a university-wide ranking."
                )
            else:
                prefix = (
                    f"{top['school_name']} has the highest share of eligible faculty under the effective mandate: "
                    f"{top['under_count']} of {top['eligible_faculty']} ({top['under_pct']}%)."
                )
        else:
            top = max(schools, key=lambda row: ((row["under_count"] or 0), row["school_name"]))
            prefix = f"{top['school_name']} has the most under-utilised eligible faculty in absolute count: {top['under_count']}."
        return execute(
            conn, people_status_sql(top["school_name"], "under"), slots, persona, page, template_id,
            "Under-mandate faculty in the leading school.",
            lambda rows, _s, total: prefix + f" The people list has {total} faculty.",
            WORKLOAD_EXCLUSIONS, ASSUME,
        )
    return handler


from app.narratives_more import (
    _advice_faculty,
    _advice_room,
    _advice_seat,
    _fsr,
    _fsr_phd,
    _inactive,
    _ltpe,
    _proxy,
    _summary_room,
    _summary_seat,
)

NARRATIVES = {
    "faculty_workload_person": _workload("faculty_workload_person"),
    "faculty_pct_mandate": _workload("faculty_pct_mandate"),
    "faculty_session_split": _workload("faculty_session_split"),
    "person_timetable": _person_timetable,
    "room_timetable": _room_timetable,
    "section_timetable": _section_timetable,
    "free_people_and_rooms": _free,
    "rooms_vacant": _vacant(False),
    "rooms_vacant_capacity": _vacant(True),
    "phd_person": _phd_person,
    "phd_top": _phd_top,
    "relaxation_justification": _justification,
    "relaxation_compare": _relaxation_compare,
    "school_gap": _school_gap,
    "school_hours": _school_hours,
    "schools_meeting": _meeting,
    "school_under_percentage": _ranked_people("school_under_percentage", "pct"),
    "school_under_absolute": _ranked_people("school_under_absolute", "count"),
    "faculty_student_ratio": _fsr,
    "faculty_student_ratio_phd": _fsr_phd,
    "proxy_last_week": _proxy("proxy_last_week", "previous week"),
    "proxy_semester": _proxy("proxy_semester", "semester trend"),
    "proxy_last_month": _proxy("proxy_last_month", "previous month"),
    "ltpe_structure": _ltpe(
        "ltpe_structure",
        lambda slots: ltpe_name_sql(slots.subject or "calculus"),
        "No LTPE course in this view matches that name.",
        "{total} LTPE courses match. L is lecturer hours, T is tutorial hours, P is practical hours, and E is skill hours. "
        "This is the LTPE extract. Timetable subject-code overlap with LTPE course id or display code is {overlap}, so these courses do not join to the timetable.",
    ),
    "ltpe_practical": _ltpe(
        "ltpe_practical",
        lambda _slots: ltpe_practical_sql(),
        "No LTPE course in this view has practical hours above zero.",
        "{total} LTPE courses have practical hours above zero. This list is the LTPE Subjects extract, not the timetable. "
        "Timetable subject-code overlap with LTPE ids is {overlap}.",
    ),
    "inactive_staff": _inactive,
    "advice_room_busy": _advice_room,
    "advice_faculty_load": _advice_faculty,
    "advice_seat_occupancy": _advice_seat,
    "room_utilisation_summary": _summary_room,
    "seat_occupancy_summary": _summary_seat,
}
