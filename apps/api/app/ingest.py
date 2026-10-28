"""Load every Excel extract. A second run does not duplicate rows."""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from pathlib import Path

import openpyxl

from app.config import data_dir, reader_password
from app.db import admin_conn

log = logging.getLogger("lia.ingest")

EXPECTED = {
    "staff": 220,
    "rooms": 225,
    "timetable_slots": 2073,
    "ltpe_courses": 4344,
    "phd_supervision": 59,
    "staff_load_extract": 640,
}

SCHEMA = Path(__file__).with_name("schema.sql")


def _statements(script: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    for line in script.splitlines():
        if line.strip().startswith("--"):
            continue
        buffer.append(line)
        if line.rstrip().endswith(";"):
            text = "\n".join(buffer).strip().rstrip(";").strip()
            buffer = []
            if text:
                parts.append(text)
    return parts


def _sheet(path: Path, name: str) -> list[dict]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        worksheet = workbook[name]
        iterator = worksheet.iter_rows(values_only=True)
        header = [str(cell).strip() if cell is not None else "" for cell in next(iterator)]
        rows = []
        for raw in iterator:
            if raw is None or all(cell is None or str(cell).strip() == "" for cell in raw):
                continue
            padded = list(raw) + [None] * max(0, len(header) - len(raw))
            rows.append({key: padded[index] for index, key in enumerate(header)})
        return rows
    finally:
        workbook.close()


def _id(value):
    if value is None or value == "":
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _num(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clock(value):
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, time):
        return value
    return datetime.strptime(str(value).strip(), "%H:%M").time()


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), "%d-%m-%Y").date()


def _copy(conn, table: str, columns: list[str], rows: list[tuple]):
    sql = f"COPY {table} ({', '.join(columns)}) FROM STDIN"
    with conn.cursor() as cur:
        with cur.copy(sql) as copy:
            for row in rows:
                copy.write_row(row)


def _count(conn, table: str) -> int:
    return int(conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"])


def _apply_schema(conn):
    for statement in _statements(SCHEMA.read_text()):
        conn.execute(statement)


def _ensure_reader(conn):
    password = reader_password()
    exists = conn.execute("SELECT 1 AS ok FROM pg_roles WHERE rolname = 'lia_reader'").fetchone()
    if exists:
        conn.execute(f"ALTER ROLE lia_reader LOGIN PASSWORD '{password}'")
    else:
        conn.execute(f"CREATE ROLE lia_reader LOGIN PASSWORD '{password}'")
    conn.execute("ALTER ROLE lia_reader SET statement_timeout = '5s'")


def _grant(conn):
    conn.execute("GRANT USAGE ON SCHEMA public TO lia_reader")
    conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO lia_reader")
    conn.execute("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM lia_reader")
    conn.execute("REVOKE SELECT ON TABLE chat_threads, email_drafts, approved_questions FROM lia_reader")
    conn.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO lia_reader")


def _already_loaded(conn) -> bool:
    try:
        counts = {table: _count(conn, table) for table in EXPECTED}
    except Exception:
        return False
    version = conn.execute("SELECT 1 AS ok FROM data_version WHERE id = 1").fetchone()
    return bool(version) and counts == EXPECTED


def _records(folder: Path):
    staff = []
    for row in _sheet(folder / "Staff_Master_Mock.xlsx", "Staff List Report"):
        staff.append((
            int(row["Sr.No."]) if row["Sr.No."] is not None else None,
            _text(row["Staff Category"]),
            _id(row["Staff ID"]),
            _text(row["Name"]),
            _text(row["Designation"]),
            _text(row["Gender"]),
            _text(row["Home Department"]),
        ))
    rooms = []
    for row in _sheet(folder / "Room_Master_Mock.xlsx", "Room Master"):
        rooms.append((
            int(row["S.No."]) if row["S.No."] is not None else None,
            _text(row["School Name"]),
            _text(row["Block"]),
            _text(row["Floor"]),
            _id(row["Room Number"]),
            int(row["Seating Capacity"]),
            _text(row["Remarks (If Any)"]),
            _text(row["Room Description"]),
        ))
    courses = []
    for row in _sheet(folder / "LTPE.xlsx", "Subjects"):
        courses.append((
            _id(row["Course ID"]),
            _text(row["Course Name"]),
            _id(row["Display Code"]),
            _text(row["Offering Department"]),
            _num(row["Default Credit"]),
            _text(row["Category"]),
            _text(row["Sub-Category"]),
            _text(row["Type"]),
            _text(row["Status"]),
            _num(row["Lecturer Hours"]),
            _num(row["Practical Hours"]),
            _num(row["Tutorial Hours"]),
            _num(row["Skill Hours"]),
        ))
    dump = [(_id(row["Subject Code"]), _text(row["Subject Name"])) for row in _sheet(folder / "LTPE.xlsx", "Sheet1")]
    phd_path = next(folder.glob("*Doctoral*"))
    phd = []
    for row in _sheet(phd_path, "Sheet1"):
        phd.append((
            _text(row["Department"]),
            _id(row["Phd Scholar Staff ID"]),
            _text(row["Phd Scholar Staff Name"]),
            _text(row["Status(Part Time/Full Time)"]),
            _id(row["Faculty Mapped Staff ID"]),
            _text(row["Faculty Mapped Staff Name"]),
        ))
    load = []
    for row in _sheet(folder / "staff_load.xlsx", "Staff Load"):
        staff_id = _id(row.get("staff_id"))
        if not staff_id:
            continue
        load.append((staff_id, _text(row.get("staff_name")), _num(row.get("hours_relaxation")), _num(row.get("mandated_hours")), None))
    return staff, rooms, courses, dump, phd, load


def _fix_slots(folder: Path):
    """Rebuild timetable tuples with a readable SNo."""
    slots = []
    for row in _sheet(folder / "Timetable_Master_Mock.xlsx", "TIMETABLEXL"):
        sno = row.get("SNo")
        slots.append((
            int(sno) if sno is not None else None,
            _text(row["Day"]),
            _text(row["Period Name"]),
            _clock(row["From Time"]),
            _clock(row["To Time"]),
            _id(row["Location"]),
            _id(row["Subject Code"]),
            _text(row["Subject Name"]),
            _num(row["Credits"]),
            _id(row["Staff Code"]),
            _text(row["Staff name"]),
            _text(row["Section"]),
            _text(row["Semester"]),
            _text(row["Program"]),
            _text(row["School Name"]),
            _text(row["Degree"]),
            _text(row["Remarks"]),
            _text(row["Subject Session Type"]),
            _text(row["Class Type"]),
            int(row["Number of Enrollments"] or 0),
            _day(row["Timetable Start Date"]),
            _day(row["Timetable End Date"]),
        ))
    return slots


def load(conn=None) -> dict:
    own = conn is None
    if own:
        ctx = admin_conn()
        conn = ctx.__enter__()
    try:
        _ensure_reader(conn)
        _apply_schema(conn)
        conn.commit()
        conn.execute("SELECT pg_advisory_lock(424242)")
        if _already_loaded(conn):
            counts = {table: _count(conn, table) for table in EXPECTED}
            _grant(conn)
            conn.commit()
            conn.execute("SELECT pg_advisory_unlock(424242)")
            log.info("ingest skipped %s", counts)
            return {"skipped": True, **counts}
        folder = data_dir()
        staff, rooms, courses, dump, phd, load_rows = _records(folder)
        slots = _fix_slots(folder)
        if len(slots) != 2073:
            raise RuntimeError(f"expected 2073 timetable rows, found {len(slots)}")
        if len(staff) != 220 or len(rooms) != 225:
            raise RuntimeError(f"unexpected master sizes staff={len(staff)} rooms={len(rooms)}")
        conn.execute(
            """
            TRUNCATE TABLE timetable_slots, staff, rooms, ltpe_courses, ltpe_subject_dump,
            phd_supervision, staff_load_extract, data_version RESTART IDENTITY
            """
        )
        _copy(conn, "staff", ["sr_no", "staff_category", "staff_id", "name", "designation", "gender", "home_department"], staff)
        _copy(conn, "rooms", ["sno", "school_name", "block", "floor", "room_number", "seating_capacity", "remarks", "room_description"], rooms)
        _copy(conn, "timetable_slots", [
            "sno", "day", "period_name", "from_time", "to_time", "location", "subject_code", "subject_name",
            "credits", "staff_code", "staff_name", "section", "semester", "program", "school_name", "degree",
            "remarks", "session_type", "class_type", "enrollments", "start_date", "end_date",
        ], slots)
        _copy(conn, "ltpe_courses", [
            "course_id", "course_name", "display_code", "offering_department", "default_credit", "category",
            "sub_category", "course_type", "status", "lecturer_hours", "practical_hours", "tutorial_hours", "skill_hours",
        ], courses)
        _copy(conn, "ltpe_subject_dump", ["subject_code", "subject_name"], dump)
        _copy(conn, "phd_supervision", [
            "department", "phd_scholar_staff_id", "phd_scholar_staff_name", "status",
            "faculty_mapped_staff_id", "faculty_mapped_staff_name",
        ], phd)
        _copy(conn, "staff_load_extract", ["staff_id", "staff_name", "hours_relaxation", "mandated_hours", "school_name"], load_rows)
        counts = {table: _count(conn, table) for table in EXPECTED}
        if counts != EXPECTED:
            raise RuntimeError(f"loaded counts {counts} != {EXPECTED}")
        conn.execute(
            """
            INSERT INTO data_version (id, loaded_at, timetable_rows, staff_rows, room_rows, label)
            VALUES (1, now(), %s, %s, %s, 'universe-a-and-b')
            """,
            (counts["timetable_slots"], counts["staff"], counts["rooms"]),
        )
        _grant(conn)
        conn.commit()
        conn.execute("SELECT pg_advisory_unlock(424242)")
        log.info("ingest loaded %s ltpe_dump=%s", counts, _count(conn, "ltpe_subject_dump"))
        return {"skipped": False, **counts, "ltpe_subject_dump": _count(conn, "ltpe_subject_dump")}
    except Exception:
        conn.rollback()
        try:
            conn.execute("SELECT pg_advisory_unlock(424242)")
            conn.commit()
        except Exception:
            pass
        raise
    finally:
        if own:
            ctx.__exit__(None, None, None)


def main():
    logging.basicConfig(level=logging.INFO)
    print(load())


if __name__ == "__main__":
    main()
