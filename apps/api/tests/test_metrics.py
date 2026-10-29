from app.metrics import (
    DEAN_SCHOOL,
    actual_weekly_hours,
    busy_pct,
    effective_mandate,
    load_status,
    mandate_hours,
    meeting_occupancy_pct,
    periods_overlapping,
    proxy_comparison,
    row_enrolment_total,
    sana_workload_text,
    section_enrolment_total,
    session_split_text,
    supervision_hours,
)
from app.slots import canonical_school as slot_school
from app.slots import extract_slots


def test_mandates_are_exact_and_do_not_invent_relaxation():
    assert mandate_hours("Professor") == 10
    assert mandate_hours("Associate Professor") == 12
    assert mandate_hours("Professor & Dean") == 4
    assert mandate_hours("Assistant Professor") == 14
    assert mandate_hours("PhD Scholar") == 8
    assert mandate_hours("Visiting Faculty") is None
    assert mandate_hours("Lab Assistant") is None
    assert effective_mandate("Assistant Professor", None) == 14
    assert effective_mandate("Assistant Professor", 0) == 14
    assert effective_mandate("Assistant Professor", 2) == 12


def test_sana_shape_is_over_mandate_without_phd_or_experiential():
    assert load_status(20, 14) == "over"
    assert load_status(14, 14) == "met"
    assert load_status(13, 14) == "under"
    assert load_status(8, None) == "not_eligible"
    phd = supervision_hours("26982489", {"15120639": 4})
    assert phd["missing"] is True
    assert phd["hours"] == 0
    assert actual_weekly_hours(20, phd["hours"]) == 20
    text = sana_workload_text(
        {
            "name": "Sana Bhardwaj",
            "staff_id": "26982489",
            "designation": "Assistant Professor",
            "school_name": "School of Computer Science",
            "actual_hours": 20,
            "effective_mandate": 14,
            "status": "over",
            "phd_hours": 0,
            "phd_missing": True,
            "relaxation_hours": 0,
        }
    )
    assert "20" in text and "14" in text
    assert "over mandate" in text
    assert "supervision extract" in text
    assert "Experiential hours are excluded" in text
    assert session_split_text({"lecture_hours": 12, "practical_hours": 8, "tutorial_hours": 0}) == (
        "Lecture 12, practical 8, tutorial 0."
    )


def test_room_and_section_grains():
    assert busy_pct(15) == 33.3
    assert meeting_occupancy_pct(105, 240) == 43.8
    rows = [("School of Computer Science", "Lec", 100), ("School of Computer Science", "Lec", 100), ("School of Computer Science", "Lab", 40)]
    assert section_enrolment_total(rows) == 140
    assert row_enrolment_total(rows) == 240


def test_clock_overlap_is_half_open():
    assert periods_overlapping("14:00", "16:00") == ["Period - 6", "Period - 7", "Period - 8"]
    assert periods_overlapping("15:00", "17:00") == ["Period - 7", "Period - 8"]
    assert periods_overlapping("10:30", "10:31") == ["Period - 3"]


def test_scset_alias_does_not_swallow_the_longer_ltpe_name():
    assert slot_school("Which faculty in SCSET are under-utilised?") == DEAN_SCHOOL
    assert slot_school("school of computer science engineering & technology") is None
    assert slot_school("school of computer science engineering & technology calculus") is None


def test_hyphenated_words_are_not_room_codes():
    slots = extract_slots("Give me the list of faculty who are under-utilised")
    assert slots.room is None
    assert slots.section is None
    room = extract_slots("Show the timetable for room P-CC-015")
    assert room.room == "P-CC-015"
    assert room.section is None
    section = extract_slots("Show the timetable for section BTCSE1-S1")
    assert section.section == "BTCSE1-S1"
    assert section.room is None
    batch = extract_slots("Show the timetable for section BALA1-S1-P1")
    assert batch.section == "BALA1-S1-P1"
    assert batch.room is None


def test_free_window_slots():
    tuesday = extract_slots("Which faculty and rooms are free on Tuesday 2 to 4 pm?")
    assert (tuesday.day, tuesday.start, tuesday.end) == ("Tuesday", "14:00", "16:00")
    monday = extract_slots("Which rooms are vacant in SCSET on Monday at 10:30?")
    assert monday.school == DEAN_SCHOOL
    assert monday.point == "10:30"
    assert monday.overlapping_periods() == ["Period - 3"]
    wednesday = extract_slots("How many 60-seater rooms are vacant on Wednesday from 3 to 5 pm?")
    assert wednesday.seat_count == 60
    assert (wednesday.start, wednesday.end) == ("15:00", "17:00")
    assert "Period - 9" not in wednesday.overlapping_periods()


def test_proxy_text_does_not_rename_the_window():
    text = proxy_comparison("previous week")
    assert "labelled proxy" in text
    assert "17 Aug 2026 to 04 Sep 2026" in text
    assert "last week" not in text.lower()
