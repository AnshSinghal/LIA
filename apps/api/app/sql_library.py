"""Fixed SELECT text for reviewed templates. Values are escaped or taken from allowlists."""

from __future__ import annotations

import re

from app.guard import GuardError, sql_str
from app.slots import Slots

_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}


def _day(value: str | None) -> str:
    if value not in _DAYS:
        raise GuardError("A Monday–Friday day is required.")
    return value


def _clock(value: str | None) -> str:
    if not value or not re.fullmatch(r"\d{2}:\d{2}", value):
        raise GuardError("A clock time is required.")
    return value


def _school(slots: Slots) -> str:
    if not slots.school:
        return ""
    return f" AND school_name = {sql_str(slots.school)}"


def under_sql(slots: Slots, status: str = "under") -> str:
    return f"""
        SELECT staff_id, name, designation, school_name, actual_hours, effective_mandate,
               (effective_mandate - actual_hours) AS gap_hours
        FROM faculty_workload
        WHERE status = {sql_str(status)}{_school(slots)}
        ORDER BY gap_hours DESC, name
    """


def excluded_count_sql() -> str:
    return """
        SELECT count(*) AS excluded_people
        FROM (
            SELECT status, school_name FROM faculty_workload
        ) AS scoped
        WHERE status = 'not_eligible'
    """


def long_day_sql(slots: Slots) -> str:
    threshold = int(slots.hour_threshold or 5)
    return f"""
        SELECT staff_id, name, designation, school_name, day, hours
        FROM (
            SELECT s.staff_id, s.name, s.designation, s.home_department AS school_name,
                   t.day, count(*) AS hours
            FROM timetable_slots AS t
            JOIN staff AS s ON s.staff_id = t.staff_code
            GROUP BY s.staff_id, s.name, s.designation, s.home_department, t.day
            HAVING count(*) > {threshold}
        ) AS scoped
        ORDER BY hours DESC, name
    """


def five_days_sql() -> str:
    return """
        SELECT staff_id, name, designation, school_name, days_taught
        FROM (
            SELECT s.staff_id, s.name, s.designation, s.home_department AS school_name,
                   count(DISTINCT t.day) AS days_taught
            FROM staff AS s
            JOIN timetable_slots AS t ON t.staff_code = s.staff_id
            GROUP BY s.staff_id, s.name, s.designation, s.home_department
            HAVING count(DISTINCT t.day) = 5
        ) AS scoped
        ORDER BY school_name, name
    """


def subject_load_sql() -> str:
    return """
        SELECT subject_name, sum(teaching_hours) AS teaching_hours
        FROM (
            SELECT subject_name, school_name, count(*) AS teaching_hours
            FROM timetable_slots
            GROUP BY subject_name, school_name
        ) AS scoped
        GROUP BY subject_name
        ORDER BY teaching_hours DESC, subject_name
    """


def subject_teachers_sql(slots: Slots) -> str:
    subject = slots.subject or "data structures"
    return f"""
        SELECT staff_code, staff_name, school_name, count(*) AS teaching_hours
        FROM (
            SELECT staff_code, staff_name, school_name
            FROM timetable_slots
            WHERE subject_name ILIKE {sql_str('%' + subject + '%')}
        ) AS scoped
        GROUP BY staff_code, staff_name, school_name
        ORDER BY teaching_hours DESC, staff_name
    """


def busiest_days_sql() -> str:
    return """
        SELECT day, sum(slot_hours) AS teaching_hours
        FROM (
            SELECT day, school_name, count(*) AS slot_hours
            FROM timetable_slots
            GROUP BY day, school_name
        ) AS scoped
        GROUP BY day
        ORDER BY teaching_hours DESC, day
    """


def avg_rank_sql() -> str:
    return """
        SELECT designation,
               sum(people) AS people,
               sum(hours) AS total_hours,
               CASE WHEN sum(people) = 0 THEN NULL ELSE round(sum(hours) / sum(people), 2) END AS avg_teaching_hours,
               max(mandate_hours) AS mandate_hours
        FROM (
            SELECT designation, school_name, count(*) AS people,
                   sum(actual_hours) AS hours, max(mandate_hours) AS mandate_hours
            FROM faculty_workload
            GROUP BY designation, school_name
        ) AS scoped
        GROUP BY designation
        ORDER BY designation
    """


def low_busy_sql(slots: Slots) -> str:
    threshold = int(slots.busy_below or 20)
    return f"""
        SELECT room_number, school_name, seating_capacity, scheduled_hours, busy_pct, avg_occupancy_pct
        FROM room_utilisation
        WHERE busy_pct < {threshold}{_school(slots)}
        ORDER BY busy_pct, room_number
    """


def busiest_rooms_sql() -> str:
    return """
        SELECT room_number, school_name, scheduled_hours, busy_pct, seating_capacity
        FROM room_utilisation
        ORDER BY scheduled_hours DESC, room_number
    """


def low_occupancy_sql(slots: Slots) -> str:
    threshold = int(slots.occupancy_below or 50)
    return f"""
        SELECT room_number, school_name, seating_capacity, scheduled_hours, avg_occupancy_pct, busy_pct
        FROM room_utilisation
        WHERE scheduled_hours > 0 AND avg_occupancy_pct < {threshold}{_school(slots)}
        ORDER BY avg_occupancy_pct, room_number
    """


def large_low_sql() -> str:
    return """
        SELECT room_number, school_name, seating_capacity, scheduled_hours, avg_occupancy_pct
        FROM room_utilisation
        WHERE seating_capacity >= 100 AND scheduled_hours > 0 AND avg_occupancy_pct < 50
        ORDER BY avg_occupancy_pct, room_number
    """


def _overlap(day: str, start: str, end: str, staff: bool) -> str:
    column = "t.staff_code = s.staff_id" if staff else "t.location = r.room_number"
    return f"""
        NOT EXISTS (
            SELECT 1 FROM timetable_slots AS t
            WHERE {column}
              AND t.day = '{day}'
              AND t.from_time < TIME '{end}'
              AND TIME '{start}' < t.to_time
        )
    """


def free_sql(slots: Slots) -> str:
    day, start, end = _day(slots.day), _clock(slots.start), _clock(slots.end)
    return f"""
        SELECT entity_kind, entity_name, entity_id, detail, school_name
        FROM (
            SELECT 'faculty' AS entity_kind, s.name AS entity_name, s.staff_id AS entity_id,
                   s.designation AS detail, s.home_department AS school_name
            FROM staff AS s
            WHERE s.staff_category IN ('Teaching', 'Administrative & Teaching')
              AND {_overlap(day, start, end, True)}
            UNION ALL
            SELECT 'room' AS entity_kind, r.room_number AS entity_name, r.room_number AS entity_id,
                   r.room_description AS detail, r.school_name
            FROM rooms AS r
            WHERE {_overlap(day, start, end, False)}
        ) AS scoped
        ORDER BY entity_kind, school_name, entity_name
    """


def vacant_sql(slots: Slots, capacity: bool = False) -> str:
    day, start, end = _day(slots.day), _clock(slots.start), _clock(slots.end)
    extra = ""
    if capacity:
        extra += f" AND r.seating_capacity = {int(slots.seat_count or 60)}"
    if slots.school:
        extra += f" AND r.school_name = {sql_str(slots.school)}"
    return f"""
        SELECT room_number, school_name, seating_capacity, room_description
        FROM (
            SELECT r.room_number, r.school_name, r.seating_capacity, r.room_description
            FROM rooms AS r
            WHERE {_overlap(day, start, end, False)}
            {extra}
        ) AS scoped
        ORDER BY school_name, room_number
    """


def clash_sql(kind: str) -> str:
    if kind == "staff":
        return """
            SELECT staff_code, staff_name, school_name, day, period_name, bookings, locations
            FROM staff_clashes
            ORDER BY day, period_name, staff_name
        """
    return """
        SELECT room_number, school_name, day, period_name, bookings, staff_names
        FROM room_clashes
        ORDER BY day, period_name, room_number
    """


def gap_sql(kind: str) -> str:
    if kind == "staff":
        return """
            SELECT staff_code, staff_name, school_name, slots
            FROM timetable_staff_gaps
            ORDER BY staff_code
        """
    return """
        SELECT room_number, school_name, slots
        FROM timetable_room_gaps
        ORDER BY room_number
    """


def weeks_sql() -> str:
    return """
        SELECT start_date, end_date, count(*) AS slots
        FROM (
            SELECT start_date, end_date, school_name FROM timetable_slots
        ) AS scoped
        GROUP BY start_date, end_date
        ORDER BY start_date
    """


def phd_top_sql() -> str:
    return """
        SELECT faculty_mapped_staff_id, faculty_mapped_staff_name, school_name, scholars, supervision_hours
        FROM (
            SELECT faculty_mapped_staff_id, faculty_mapped_staff_name, department AS school_name,
                   count(*) AS scholars, round(CAST(0.25 * count(*) AS numeric), 2) AS supervision_hours
            FROM phd_supervision
            GROUP BY faculty_mapped_staff_id, faculty_mapped_staff_name, department
        ) AS scoped
        ORDER BY scholars DESC, faculty_mapped_staff_name
    """


def ltpe_name_sql(subject: str) -> str:
    return f"""
        SELECT course_id, course_name, display_code, school_name,
               lecturer_hours, tutorial_hours, practical_hours, skill_hours
        FROM ltpe_catalog
        WHERE course_name ILIKE {sql_str('%' + subject + '%')}
        ORDER BY course_name
    """


def ltpe_practical_sql() -> str:
    return """
        SELECT course_id, course_name, school_name, practical_hours, lecturer_hours, tutorial_hours, skill_hours
        FROM ltpe_catalog
        WHERE practical_hours > 0
        ORDER BY course_name
    """


def ltpe_overlap_sql() -> str:
    return """
        SELECT count(*) AS timetable_code_overlap
        FROM (
            SELECT c.course_id, c.offering_department AS school_name
            FROM ltpe_courses AS c
            JOIN timetable_slots AS t
              ON t.subject_code = c.course_id OR t.subject_code = c.display_code
        ) AS scoped
    """


def school_summary_sql() -> str:
    return """
        SELECT school_name, eligible_faculty, under_count, over_count, met_count,
               under_pct, actual_hours, mandated_hours, gap_hours
        FROM school_load_summary
        ORDER BY school_name
    """


def school_one_sql(school: str) -> str:
    return f"""
        SELECT school_name, eligible_faculty, under_count, over_count,
               actual_hours, mandated_hours, gap_hours
        FROM school_load_summary
        WHERE school_name = {sql_str(school)}
    """


def people_status_sql(school: str, status: str) -> str:
    return f"""
        SELECT staff_id, name, designation, school_name, actual_hours, effective_mandate,
               (effective_mandate - actual_hours) AS gap_hours
        FROM faculty_workload
        WHERE status = {sql_str(status)} AND school_name = {sql_str(school)}
        ORDER BY gap_hours DESC, name
    """


def meeting_sql() -> str:
    return """
        SELECT school_name, actual_hours, mandated_hours, gap_hours, eligible_faculty
        FROM school_load_summary
        WHERE actual_hours >= mandated_hours
        ORDER BY school_name
    """


def fsr_sql() -> str:
    return """
        SELECT school_name, section_students, sections, row_sum_enrolment, faculty_count,
               baseline_ratio, staff_phd_scholars, ratio_with_staff_phd_in_denominator
        FROM faculty_student_ratio
        ORDER BY school_name
    """


def fsr_phd_sql() -> str:
    return """
        SELECT school_name, section_students, faculty_count, baseline_ratio,
               staff_phd_scholars, ratio_with_staff_phd_in_denominator,
               full_time_scholars_in_supervision_extract, ratio_if_students_plus_full_time_scholars
        FROM (
            SELECT r.school_name, r.section_students, r.faculty_count, r.baseline_ratio,
                   r.staff_phd_scholars, r.ratio_with_staff_phd_in_denominator,
                   COALESCE(p.full_time_scholars, 0) AS full_time_scholars_in_supervision_extract,
                   CASE WHEN r.faculty_count = 0 THEN NULL
                        ELSE round(
                            CAST(r.section_students + COALESCE(p.full_time_scholars, 0) AS numeric)
                            / r.faculty_count, 2)
                   END AS ratio_if_students_plus_full_time_scholars
            FROM faculty_student_ratio AS r
            LEFT JOIN phd_scholar_counts AS p ON p.school_name = r.school_name
        ) AS scoped
        ORDER BY school_name
    """


def proxy_sql() -> str:
    return """
        SELECT school_name, actual_hours AS loaded_window_teaching_hours,
               mandated_hours AS loaded_window_effective_mandate
        FROM school_load_summary
        ORDER BY school_name
    """


def workload_sql(staff_id: str) -> str:
    return f"""
        SELECT staff_id, name, designation, school_name, lecture_hours, practical_hours, tutorial_hours,
               teaching_hours, actual_hours, mandate_hours, effective_mandate, relaxation_hours,
               phd_hours, phd_missing, experiential_excluded, status, pct_of_mandate
        FROM faculty_workload
        WHERE staff_id = {sql_str(staff_id)}
    """


def person_timetable_sql(staff_id: str) -> str:
    return f"""
        SELECT day, period_name, from_time, to_time, room_number, subject_name, session_type,
               enrollments, seating_capacity, meeting_occupancy_pct, school_name
        FROM timetable_detail
        WHERE staff_code = {sql_str(staff_id)}
        ORDER BY day_order, from_time
    """


def room_util_sql(room: str) -> str:
    return f"""
        SELECT room_number, school_name, scheduled_hours, busy_pct, seating_capacity, avg_occupancy_pct
        FROM room_utilisation
        WHERE room_number = {sql_str(room)}
    """


def room_timetable_sql(room: str) -> str:
    return f"""
        SELECT day, period_name, from_time, to_time, staff_name, subject_name, session_type,
               enrollments, seating_capacity, meeting_occupancy_pct, school_name
        FROM timetable_detail
        WHERE room_number = {sql_str(room)}
        ORDER BY day_order, from_time
    """


_SECTION_ID = re.compile(r"^[A-Z]{2,}[A-Z0-9]*-S\d+(?:-[A-Z]\d+)?$")


def section_timetable_sql(section: str) -> str:
    if not _SECTION_ID.fullmatch(section or ""):
        raise GuardError("A section id is required.")
    return f"""
        SELECT day, period_name, from_time, to_time, room_number, staff_name, subject_name,
               session_type, enrollments, seating_capacity, meeting_occupancy_pct, school_name
        FROM timetable_detail
        WHERE section = {sql_str(section)}
        ORDER BY day_order, from_time
    """


def relaxation_group_sql() -> str:
    return """
        SELECT CASE WHEN coalesce(hours_relaxation, 0) > 0 THEN 'has_relaxation' ELSE 'no_relaxation' END AS grp,
               count(*) AS people,
               count(mandated_hours) AS with_mandate,
               round(CAST(avg(mandated_hours) AS numeric), 2) AS avg_mandated_hours,
               round(CAST(avg(hours_relaxation) AS numeric), 2) AS avg_relaxation
        FROM staff_load_extract
        GROUP BY 1
        ORDER BY 1
    """


def id_overlap_sql() -> str:
    return """
        SELECT count(*) AS id_overlap
        FROM (
            SELECT s.staff_id, s.home_department AS school_name
            FROM staff AS s
            JOIN staff_load_extract AS l ON l.staff_id = s.staff_id
        ) AS scoped
    """


def room_stats_sql() -> str:
    return """
        SELECT count(*) AS rooms,
               sum(CASE WHEN busy_pct < 20 THEN 1 ELSE 0 END) AS below_20,
               sum(CASE WHEN scheduled_hours = 0 THEN 1 ELSE 0 END) AS unused
        FROM (
            SELECT room_number, school_name, busy_pct, scheduled_hours FROM room_utilisation
        ) AS scoped
    """


def seat_stats_sql() -> str:
    return """
        SELECT sum(CASE WHEN scheduled_hours > 0 THEN 1 ELSE 0 END) AS scheduled_rooms,
               sum(CASE WHEN avg_occupancy_pct < 50 THEN 1 ELSE 0 END) AS below_50,
               sum(CASE WHEN seating_capacity >= 100 AND avg_occupancy_pct < 50 THEN 1 ELSE 0 END) AS large_low
        FROM (
            SELECT school_name, scheduled_hours, avg_occupancy_pct, seating_capacity
            FROM room_utilisation
        ) AS scoped
    """
