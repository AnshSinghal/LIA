"""Parse one SELECT, reject writes, and inject the dean school predicate."""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

from app.metrics import DEAN_SCHOOL

class GuardError(ValueError):
    pass


ALLOWLIST = frozenset(
    {
        "faculty_workload",
        "room_utilisation",
        "section_enrolment",
        "timetable_slots",
        "timetable_detail",
        "staff",
        "rooms",
        "ltpe_courses",
        "ltpe_catalog",
        "ltpe_subject_dump",
        "phd_supervision",
        "phd_supervision_scoped",
        "staff_load_extract",
        "data_version",
        "school_load_summary",
        "staff_clashes",
        "room_clashes",
        "timetable_staff_gaps",
        "timetable_room_gaps",
        "faculty_student_ratio",
        "phd_scholar_counts",
    }
)

_FORBIDDEN = (
    "insert ",
    "update ",
    "delete ",
    "drop ",
    "alter ",
    "truncate ",
    "grant ",
    "revoke ",
    "copy ",
    "pg_sleep",
    "pg_read_file",
    "pg_ls_dir",
    "lo_import",
    "dblink",
    "for update",
    "into outfile",
)


def _forbidden(sql: str) -> None:
    lowered = f" {sql.lower()} "
    for token in _FORBIDDEN:
        if token in lowered:
            raise GuardError(f"Statement is not a read-only SELECT ({token.strip()}).")


def parse_select(sql: str) -> exp.Select:
    if not sql or not sql.strip():
        raise GuardError("Empty SQL.")
    _forbidden(sql)
    try:
        trees = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.ParseError as exc:
        raise GuardError(f"SQL could not be parsed: {exc}") from exc
    trees = [tree for tree in trees if tree is not None]
    if len(trees) != 1:
        raise GuardError("Only one SQL statement is allowed.")
    tree = trees[0]
    if not isinstance(tree, exp.Select):
        raise GuardError("Only a single SELECT is allowed.")
    if tree.args.get("with"):
        raise GuardError("CTEs are not allowed.")
    if tree.args.get("into"):
        raise GuardError("SELECT INTO is not allowed.")
    tables = set()
    for table in tree.find_all(exp.Table):
        name = (table.name or "").lower()
        if name:
            tables.add(name)
    unknown = sorted(tables - ALLOWLIST)
    if unknown:
        raise GuardError(f"Table is not allowlisted: {', '.join(unknown)}.")
    return tree


def inject_school(tree: exp.Select, persona: str) -> exp.Select:
    if persona != "dean_cs":
        return tree
    predicate = exp.EQ(
        this=exp.column("school_name"),
        expression=exp.Literal.string(DEAN_SCHOOL),
    )
    where = tree.args.get("where")
    if where is not None:
        where.set("this", exp.and_(where.this, predicate))
    else:
        tree.set("where", exp.Where(this=predicate))
    return tree


def apply_page(tree: exp.Select, limit: int | None, offset: int | None) -> exp.Select:
    if limit is None:
        return tree
    tree.set("limit", exp.Limit(expression=exp.Literal.number(int(limit))))
    if offset:
        tree.set("offset", exp.Offset(expression=exp.Literal.number(int(offset))))
    else:
        tree.set("offset", None)
    return tree


def render(tree: exp.Expression) -> str:
    sql = tree.sql(dialect="postgres")
    if ";" in sql:
        raise GuardError("Rendered SQL contained more than one statement.")
    _forbidden(sql)
    return sql


def prepare(sql: str, persona: str, *, page: int = 1, page_size: int = 20) -> tuple[str, str]:
    """Return (count_sql, page_sql) after persona injection."""
    if page < 1:
        page = 1
    tree = inject_school(parse_select(sql), persona)
    count_tree = tree.copy()
    count_tree.set("order", None)
    count_tree.set("limit", None)
    count_tree.set("offset", None)
    count_sql = f"SELECT count(*) AS n FROM ({render(count_tree)}) AS counted"
    page_tree = apply_page(tree.copy(), page_size, (page - 1) * page_size)
    return count_sql, render(page_tree)


def guard_sql(sql: str, persona: str, *, limit: int | None = 20, offset: int = 0) -> str:
    tree = inject_school(parse_select(sql), persona)
    if limit is not None:
        tree = apply_page(tree, limit, offset)
    return render(tree)


def sql_str(value: str) -> str:
    if not isinstance(value, str) or re.search(r"[\x00]", value):
        raise GuardError("Unsafe string.")
    return "'" + value.replace("'", "''") + "'"
