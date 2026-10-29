import pytest

from app.guard import GuardError, guard_sql, prepare


def test_dean_predicate_is_added_beside_a_model_school_filter():
    sql = guard_sql(
        "SELECT staff_id, school_name FROM faculty_workload WHERE school_name = 'School of Law'",
        "dean_cs",
        limit=20,
    )
    assert "School of Computer Science" in sql
    assert "School of Law" in sql
    assert "LIMIT" in sql.upper()


def test_university_persona_does_not_inject_a_school():
    sql = guard_sql("SELECT staff_id FROM faculty_workload", "university", limit=None)
    assert "School of Computer Science" not in sql


def test_writes_and_multiple_statements_are_rejected():
    with pytest.raises(GuardError):
        guard_sql("DELETE FROM staff", "university")
    with pytest.raises(GuardError):
        guard_sql("SELECT staff_id FROM staff; DROP TABLE staff", "university")
    with pytest.raises(GuardError):
        guard_sql("SELECT * FROM secret_table", "university")


def test_grouped_day_query_keeps_a_single_select_and_the_dean_filter():
    source = """
        SELECT day, sum(slot_hours) AS teaching_hours
        FROM (
            SELECT day, school_name, count(*) AS slot_hours
            FROM timetable_slots
            GROUP BY day, school_name
        ) AS scoped
        GROUP BY day
        ORDER BY teaching_hours DESC, day
    """
    count_sql, page_sql = prepare(source, "dean_cs", page=2, page_size=20)
    assert "School of Computer Science" in page_sql
    assert "OFFSET" in page_sql.upper()
    assert "DROP" not in count_sql.upper()
    assert count_sql.lower().startswith("select count")
