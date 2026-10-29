from app.guard import prepare
from app.slots import Slots
from app import sql_library as sql


def sample_sqls() -> list[str]:
    slots = Slots(
        school="School of Computer Science",
        day="Tuesday",
        start="14:00",
        end="16:00",
        subject="calculus",
        room="P-CC-015",
        busy_below=20,
        occupancy_below=50,
        hour_threshold=5,
        seat_count=60,
    )
    monday = Slots(day="Monday", start="10:30", end="10:31", school="School of Computer Science")
    return [
        sql.under_sql(slots),
        sql.under_sql(Slots(), "over"),
        sql.excluded_count_sql(),
        sql.long_day_sql(slots),
        sql.five_days_sql(),
        sql.subject_load_sql(),
        sql.subject_teachers_sql(slots),
        sql.busiest_days_sql(),
        sql.avg_rank_sql(),
        sql.low_busy_sql(slots),
        sql.busiest_rooms_sql(),
        sql.low_occupancy_sql(slots),
        sql.large_low_sql(),
        sql.free_sql(slots),
        sql.vacant_sql(monday),
        sql.vacant_sql(slots, capacity=True),
        sql.clash_sql("staff"),
        sql.clash_sql("room"),
        sql.gap_sql("staff"),
        sql.gap_sql("room"),
        sql.weeks_sql(),
        sql.phd_top_sql(),
        sql.ltpe_name_sql("calculus"),
        sql.ltpe_practical_sql(),
        sql.ltpe_overlap_sql(),
        sql.school_summary_sql(),
        sql.school_one_sql("School of Computer Science"),
        sql.people_status_sql("School of Computer Science", "under"),
        sql.meeting_sql(),
        sql.fsr_sql(),
        sql.fsr_phd_sql(),
        sql.proxy_sql(),
        sql.workload_sql("26982489"),
        sql.person_timetable_sql("26982489"),
        sql.room_util_sql("P-CC-015"),
        sql.room_timetable_sql("P-CC-015"),
        sql.section_timetable_sql("BTCSE1-S1"),
        sql.relaxation_group_sql(),
        sql.id_overlap_sql(),
        sql.room_stats_sql(),
        sql.seat_stats_sql(),
    ]


def test_every_template_query_parses_and_accepts_the_dean_filter():
    for statement in sample_sqls():
        _count, page = prepare(statement, "dean_cs", page=1, page_size=20)
        assert "School of Computer Science" in page
        lowered = page.lower()
        assert "insert " not in lowered
        assert "delete " not in lowered
        assert "update " not in lowered
