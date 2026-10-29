"""Template-first router. Out of scope is decided before any SQL."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.metrics import DEAN_SCHOOL
from app.slots import Slots, extract_slots, school_choices

REFUSE = "refuse"
CLARIFY = "clarify"
TEMPLATE = "template"
DYNAMIC = "dynamic"
MISSING = "missing_data"


@dataclass
class Option:
    id: str
    label: str
    template_id: str | None = None
    followup: str | None = None
    school: str | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "template_id": self.template_id,
            "followup": self.followup,
            "school": self.school,
        }


@dataclass
class Decision:
    route: str
    template_id: str | None = None
    slots: Slots = field(default_factory=Slots)
    clarifying_question: str | None = None
    options: list[Option] = field(default_factory=list)
    reason: str | None = None


def out_of_scope_reason(message: str) -> str | None:
    from app.slots import normalize

    text = normalize(message)
    if re.search(r"\b(weather|forecast|temperature|rainfall)\b", text):
        return "Weather is outside this utilisation assistant."
    write_verb = r"\b(insert|update|delete|drop|alter|truncate|change|modify|edit|reschedule|move|cancel|assign|write)\b"
    timetable_noun = r"\b(timetable|schedule|class|slot)\b"
    if re.search(write_verb, text) and re.search(timetable_noun, text):
        return "LIA is read-only and cannot change the timetable."
    if re.search(
        r"\b(grade|grades|gpa|student records?|which students?|list of students|list students|students? named|named students?)\b",
        text,
    ):
        return "Student-level records are out of scope."
    return None


def _has_under(text: str) -> bool:
    return re.search(r"under[-\s]?utili[sz]", text) is not None


def _has_over(text: str) -> bool:
    return re.search(r"over[-\s]?load", text) is not None


def _occupancy_clarify(period_note: str | None = None) -> Decision:
    question = "Do you mean room utilisation or faculty teaching load?"
    if period_note:
        question = f"{period_note} {question}"
    return Decision(
        route=CLARIFY,
        clarifying_question=question,
        options=[
            Option("room_utilisation", "Room utilisation", followup="busy_or_seat"),
            Option("faculty_load", "Faculty teaching load", template_id="avg_load_by_rank"),
        ],
        reason="ambiguous occupancy",
    )


def _busy_or_seat() -> Decision:
    return Decision(
        route=CLARIFY,
        clarifying_question="For rooms, do you want busy percent or seat occupancy?",
        options=[
            Option("busy_pct", "Busy percent (scheduled hours / 45)", template_id="room_utilisation_summary"),
            Option("seat_occupancy", "Seat occupancy (enrolment / capacity)", template_id="seat_occupancy_summary"),
        ],
        reason="room metric",
    )


def _school_clarify() -> Decision:
    options = [
        Option(school, school, template_id="school_hours", school=school)
        for school in school_choices()
    ]
    return Decision(
        route=CLARIFY,
        clarifying_question="Which school should the mandated and actual hours use?",
        options=options,
        reason="school required",
    )


def _option_match(message: str, options: list[dict]) -> dict | None:
    from app.slots import normalize

    text = normalize(message)
    if not text:
        return None
    exact: list[dict] = []
    prefix: list[dict] = []
    for option in options:
        label = normalize(option.get("label") or "")
        ident = normalize(option.get("id") or "").replace("_", " ")
        if text in {label, ident, normalize(option.get("id") or "")}:
            exact.append(option)
            continue
        if label and (label in text or (len(text) >= 4 and label.startswith(text))):
            prefix.append(option)
    if exact:
        return exact[0]
    if len(prefix) == 1:
        return prefix[0]
    return None


def _from_template_id(template_id: str, slots: Slots) -> Decision:
    return Decision(route=TEMPLATE, template_id=template_id, slots=slots, reason="template id")


def _apply_school_hours(decision: Decision, persona: str) -> Decision:
    if decision.template_id != "school_hours":
        return decision
    if decision.slots.school is None and persona == "dean_cs":
        decision.slots.school = DEAN_SCHOOL
        return decision
    if decision.slots.school is None and persona == "university":
        return _school_clarify()
    return decision


def classify(
    message: str,
    *,
    persona: str = "university",
    names: list[str] | None = None,
    pending: dict | None = None,
    template_id: str | None = None,
) -> Decision:
    from app.slots import normalize

    reason = out_of_scope_reason(message)
    if reason:
        return Decision(route=REFUSE, reason=reason, slots=extract_slots(message, names))

    slots = extract_slots(message, names)
    if template_id:
        return _apply_school_hours(_from_template_id(template_id, slots), persona)

    if pending and pending.get("options"):
        chosen = _option_match(message, pending["options"])
        if not chosen:
            return Decision(
                route=CLARIFY,
                clarifying_question=pending.get("question"),
                options=[Option(**{k: opt.get(k) for k in ("id", "label", "template_id", "followup", "school")}) for opt in pending["options"]],
                slots=slots,
                reason="repeat",
            )
        if chosen.get("followup") == "busy_or_seat":
            return _busy_or_seat()
        if chosen.get("school"):
            slots.school = chosen["school"]
        if chosen.get("template_id"):
            return _apply_school_hours(
                Decision(route=TEMPLATE, template_id=chosen["template_id"], slots=slots, reason="clarification choice"),
                persona,
            )

    if slots.person_ambiguous:
        options = [Option(name, name, template_id="faculty_workload_person") for name in slots.person_ambiguous]
        return Decision(
            route=CLARIFY,
            clarifying_question="Which person do you mean?",
            options=options,
            slots=slots,
            reason="ambiguous person",
        )

    text = normalize(message)
    decision = _match(text, slots)
    return _apply_school_hours(decision, persona)


def _match(text: str, slots: Slots) -> Decision:
    def hit(template_id: str, route: str = TEMPLATE) -> Decision:
        return Decision(route=route, template_id=template_id, slots=slots)

    if "inactive" in text and "faculty" in text:
        return hit("inactive_staff", MISSING)
    if "weeks" in text and ("loaded" in text or "timetable data" in text):
        return hit("weeks_loaded")
    if "missing" in text and "faculty" in text:
        return hit("timetable_faculty_missing")
    if "missing" in text and "room" in text:
        return hit("timetable_rooms_missing")
    if re.search(r"\boccupancy\b", text) and not re.search(r"\b(seat|busy|room|faculty|improve)\b", text) and "%" not in text:
        note = None
        if any(phrase in text for phrase in ("last month", "last week", "semester")):
            note = (
                "That earlier period is not loaded. After you choose, the answer uses "
                "17 Aug 2026 to 04 Sep 2026 and labels it as a proxy."
            )
        return _occupancy_clarify(note)
    if "last week" in text or ("compare" in text and "week" in text and "last" in text):
        return hit("proxy_last_week")
    if "last month" in text:
        return hit("proxy_last_month")
    if "semester" in text and re.search(r"utili[sz]|changed|change|trend", text):
        return hit("proxy_semester")
    if "improve" in text and ("room busy" in text or "busy %" in text or "busy percent" in text):
        return hit("advice_room_busy")
    if "improve" in text and ("seat" in text or ("occupancy" in text and "faculty" not in text)):
        return hit("advice_seat_occupancy")
    if ("improve" in text and "faculty" in text) or ("3 things" in text and "faculty" in text):
        return hit("advice_faculty_load")
    if "justification" in text and "relaxation" in text:
        return hit("relaxation_justification")
    if "relaxation" in text and ("compared" in text or "rest" in text or "with a relaxation" in text):
        return hit("relaxation_compare")
    if "phd" in text and slots.person_name and re.search(r"load|supervision", text):
        return hit("phd_person")
    if "phd" in text and re.search(r"supervis", text):
        return hit("phd_top")
    if ("full-time" in text or "full time" in text) and ("phd" in text or "ratio" in text or "scholar" in text):
        return hit("faculty_student_ratio_phd")
    if "ratio" in text and ("affected" in text or "counting" in text):
        return hit("faculty_student_ratio_phd")
    if "faculty-student" in text or "faculty student" in text or ("ratio" in text and "school" in text):
        return hit("faculty_student_ratio")
    if "two places" in text or "booked in two" in text:
        return hit("staff_clashes")
    if "double-booked" in text or "double booked" in text:
        return hit("room_clashes")
    if ("timetable" in text or "schedule" in text) and slots.person_name:
        return hit("person_timetable")
    if ("timetable" in text or "schedule" in text) and slots.section and slots.room:
        return _schedule_which(slots)
    if ("timetable" in text or "schedule" in text) and (slots.section or "section" in text):
        return hit("section_timetable")
    if ("timetable" in text or "schedule" in text) and (slots.room or "room" in text):
        return hit("room_timetable")
    if "practical component" in text:
        return hit("ltpe_practical")
    if "l-t-p" in text or "ltpe" in text or "structure of" in text:
        return hit("ltpe_structure")
    if "subject" in text and ("highest" in text or "faculty load" in text):
        return hit("subject_load")
    if "single day" in text or ("more than" in text and "hours" in text and "day" in text):
        return hit("long_day")
    if "busiest" in text and "day" in text:
        return hit("busiest_days")
    if "five days" in text or "all five" in text:
        return hit("five_days")
    if "who teaches" in text:
        return hit("subject_teachers")
    if "average" in text and "rank" in text:
        return hit("avg_load_by_rank")
    if "gap" in text and "mandate" in text:
        return hit("school_gap")
    if "meeting" in text and "mandat" in text:
        return hit("schools_meeting")
    if "mandated" in text and "actual" in text and "school" in text:
        return hit("school_hours")
    if _has_under(text) and "percentage" in text:
        return hit("school_under_percentage")
    if _has_under(text) and "absolute" in text:
        return hit("school_under_absolute")
    if _has_under(text):
        return hit("faculty_under_list")
    if _has_over(text):
        return hit("faculty_over_list")
    if "busiest" in text and "room" in text:
        return hit("busiest_rooms")
    if re.search(r"\bbusy\b", text) and ("room" in text or "%" in text or "percent" in text):
        return hit("rooms_low_busy")
    if ("large" in text and "room" in text) or ("large" in text and "occupancy" in text):
        return hit("rooms_large_low_occupancy")
    if "occupancy" in text and re.search(r"less than|under|below|50", text):
        return hit("rooms_low_occupancy")
    if slots.seat_count:
        return hit("rooms_vacant_capacity")
    if re.search(r"\b(free|vacant)\b", text) and "faculty" in text and "room" in text:
        return hit("free_people_and_rooms")
    if "vacant" in text and "room" in text:
        return hit("rooms_vacant")
    if "free" in text and "room" in text:
        return hit("rooms_vacant")
    if slots.person_name and "lecture" in text and "practical" in text:
        return hit("faculty_session_split")
    if slots.person_name and re.search(r"percentage of mandate|percent of mandate|% of mandate", text):
        return hit("faculty_pct_mandate")
    if slots.person_name and re.search(r"\b(workload|load)\b", text):
        return hit("faculty_workload_person")
    if re.search(r"\boccupancy\b", text) and not re.search(r"seat|busy|room|faculty|improve|%", text):
        return _occupancy_clarify()
    if text in {"show occupancy", "occupancy", "what is the occupancy"}:
        return _occupancy_clarify()
    return Decision(route=DYNAMIC, slots=slots, reason="no template")


def _schedule_which(slots: Slots) -> Decision:
    return Decision(
        route=CLARIFY,
        clarifying_question="Do you mean the section timetable or the room timetable?",
        options=[
            Option("section_schedule", f"Section {slots.section}", template_id="section_timetable"),
            Option("room_schedule", f"Room {slots.room}", template_id="room_timetable"),
        ],
        slots=slots,
        reason="section or room",
    )


def _concrete_option(options: list[Option]) -> Option | None:
    if not options:
        return None
    first = options[0]
    if first.template_id:
        return first
    if first.followup == "busy_or_seat":
        return Option(
            "busy_pct",
            "Busy percent (scheduled hours / 45)",
            template_id="room_utilisation_summary",
        )
    return None


def assume_after_limit(decision: Decision, clarify_count: int) -> Decision:
    """At most two clarifying questions. The next turn answers, including a reply that did not match a button."""
    if decision.route != CLARIFY or clarify_count < 2:
        return decision
    chosen = _concrete_option(decision.options)
    if chosen is None or not chosen.template_id:
        return decision
    slots = decision.slots
    if chosen.school:
        slots.school = chosen.school
    return Decision(
        route=TEMPLATE,
        template_id=chosen.template_id,
        slots=slots,
        reason="assumed after two clarifying questions",
    )
