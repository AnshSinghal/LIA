from pathlib import Path

import pytest

from app.catalog import TEMPLATES, autocomplete
from app.chat import remember_person
from app.router import assume_after_limit, classify

NAMES = ["Sana Bhardwaj"]
DATA = Path(__file__).resolve().parents[3] / "docs" / "tech - assignment"


def _decision(question, persona="university", template_id=None, pending=None):
    return classify(question, persona=persona, names=NAMES, template_id=template_id, pending=pending)


@pytest.mark.parametrize("item", TEMPLATES, ids=lambda item: item["question"][:48])
def test_sample_question_routes_to_its_template(item):
    decision = _decision(item["question"])
    if item["id"] == "school_hours":
        assert decision.route == "clarify"
        assert decision.clarifying_question
        return
    if item["id"] == "inactive_staff":
        assert decision.route == "missing_data"
        assert decision.template_id == "inactive_staff"
        return
    assert decision.route == "template"
    assert decision.template_id == item["id"]
    if "scset" in item["question"].lower():
        assert decision.slots.school == "School of Computer Science"
    if "Sana Bhardwaj" in item["question"]:
        assert decision.slots.person_name == "Sana Bhardwaj"
    if "P-CC-015" in item["question"]:
        assert decision.slots.room == "P-CC-015"


def test_weather_refuses_before_a_forced_template():
    decision = _decision("What is the weather in Delhi?", template_id="faculty_workload_person")
    assert decision.route == "refuse"
    assert decision.template_id is None


def test_timetable_writes_and_student_records_refuse():
    assert _decision("Please update the timetable for Monday").route == "refuse"
    assert _decision("Show the student grades for section A").route == "refuse"
    assert _decision("List students named Sana").route == "refuse"
    assert _decision("What is the faculty-student ratio by school?").route == "template"


def test_occupancy_for_last_month_asks_before_using_a_proxy():
    decision = _decision("Show occupancy for last month")
    assert decision.route == "clarify"
    assert "room utilisation" in decision.clarifying_question.lower()
    assert "not loaded" in decision.clarifying_question.lower()


def test_show_occupancy_asks_instead_of_answering():
    decision = _decision("Show occupancy")
    assert decision.route == "clarify"
    assert "room utilisation" in decision.clarifying_question.lower()
    pending = {"question": decision.clarifying_question, "options": [opt.as_dict() for opt in decision.options]}
    second = _decision("Room utilisation", pending=pending)
    assert second.route == "clarify"
    pending2 = {"question": second.clarifying_question, "options": [opt.as_dict() for opt in second.options]}
    third = _decision("Busy percent (scheduled hours / 45)", pending=pending2)
    assert third.template_id == "room_utilisation_summary"
    short = _decision("Busy percent", pending=pending2)
    assert short.route == "template"
    assert short.template_id == "room_utilisation_summary"


def test_third_unclear_reply_answers_instead_of_asking_again():
    decision = _decision("Show occupancy")
    pending = {"question": decision.clarifying_question, "options": [opt.as_dict() for opt in decision.options]}
    second = _decision("Room utilisation", pending=pending)
    pending2 = {"question": second.clarifying_question, "options": [opt.as_dict() for opt in second.options]}
    unmatched = _decision("not sure", pending=pending2)
    assert unmatched.route == "clarify"
    forced = assume_after_limit(unmatched, 2)
    assert forced.route == "template"
    assert forced.template_id == "room_utilisation_summary"
    assert forced.reason == "assumed after two clarifying questions"


def test_template_id_skips_matching():
    decision = _decision("hello there", template_id="busiest_days")
    assert decision.route == "template"
    assert decision.template_id == "busiest_days"


def test_dean_school_hours_use_computer_science_without_asking():
    decision = _decision("What is the total mandated and actual teaching hours of a school?", persona="dean_cs")
    assert decision.route == "template"
    assert decision.template_id == "school_hours"
    assert decision.slots.school == "School of Computer Science"


def test_named_law_school_stays_on_the_under_list_template():
    decision = _decision("Which faculty in the School of Law are under-utilised?", persona="dean_cs")
    assert decision.template_id == "faculty_under_list"
    assert decision.slots.school == "School of Law"


def test_section_timetable_is_not_treated_as_a_room():
    decision = _decision("Show the timetable for section BTCSE1-S1")
    assert decision.route == "template"
    assert decision.template_id == "section_timetable"
    assert decision.slots.section == "BTCSE1-S1"
    assert decision.slots.room is None


def test_section_and_room_together_ask_which_schedule():
    decision = _decision("Show the timetable for section BTCSE1-S1 in room P-CC-015")
    assert decision.route == "clarify"
    assert decision.clarifying_question == "Do you mean the section timetable or the room timetable?"
    assert [opt.template_id for opt in decision.options] == ["section_timetable", "room_timetable"]


def test_section_timetable_without_an_id_still_uses_that_template():
    decision = _decision("Show the timetable for section")
    assert decision.template_id == "section_timetable"
    assert decision.slots.section is None


def test_unseen_in_domain_question_is_dynamic():
    decision = _decision("How many distinct programs appear on the timetable?")
    assert decision.route == "dynamic"


def test_compare_last_week_is_the_proxy_template():
    decision = _decision("Compare this week with last week by school")
    assert decision.template_id == "proxy_last_week"


def test_paraphrases_hit_the_same_templates():
    assert _decision("underutilized faculty in scset").template_id == "faculty_under_list"
    assert _decision("Sana Bhardwaj workload this week").template_id == "faculty_workload_person"
    assert _decision("which rooms are below 20% busy").template_id == "rooms_low_busy"


def test_typing_sana_workload_suggests_the_reviewed_question():
    groups = autocomplete("sana workload")
    labels = [question["label"] for group in groups for question in group["questions"]]
    assert any("Sana Bhardwaj" in label and "workload" in label.lower() for label in labels)
    assert groups[0]["area"]


def test_short_query_does_not_suggest_the_whole_catalog():
    assert autocomplete("s") == []


def test_question_key_ignores_case_and_punctuation():
    from app.review import question_key

    assert question_key("How many Programs?") == question_key("how many programs")


def test_follow_up_pronoun_keeps_the_last_person():
    text = remember_person("Show her timetable", {"last_person_name": "Sana Bhardwaj"})
    assert text == "Show her timetable for Sana Bhardwaj"
    assert remember_person("Show her timetable", {}) == "Show her timetable"


def test_every_sample_question_in_the_workbook_is_in_the_catalog():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(DATA / "LIA - sample query.xlsx", read_only=True, data_only=True)
    found = []
    for index, row in enumerate(wb.active.iter_rows(values_only=True)):
        if index == 0:
            continue
        if row and row[1]:
            found.append(row[1])
    wb.close()
    assert [item["question"] for item in TEMPLATES] == found
