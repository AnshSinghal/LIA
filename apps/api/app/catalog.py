"""Touch-list catalog. The 47 sample questions are the suggestion source."""

from __future__ import annotations

TEMPLATES: list[dict] = [
    {"id": "faculty_workload_person", "area": "Faculty workload", "question": "What is the workload of Dr. Sana Bhardwaj this week?"},
    {"id": "faculty_pct_mandate", "area": "Faculty workload", "question": "What is Dr. Sana Bhardwaj's load as a percentage of mandate?"},
    {"id": "faculty_session_split", "area": "Faculty workload", "question": "How many lecture, practical and tutorial hours does Dr. Sana Bhardwaj teach?"},
    {"id": "faculty_under_list", "area": "Faculty utilisation: under and over load", "question": "Give me the list of faculty who are under-utilised"},
    {"id": "faculty_under_list", "area": "Faculty utilisation: under and over load", "question": "Which faculty in SCSET are under-utilised?"},
    {"id": "faculty_over_list", "area": "Faculty utilisation: under and over load", "question": "Which faculty are over-loaded?"},
    {"id": "school_under_percentage", "area": "Faculty utilisation: school, rank and profile", "question": "Which school has the most under-utilised faculty in percentage terms, and who are they?"},
    {"id": "school_under_absolute", "area": "Faculty utilisation: school, rank and profile", "question": "Which school has the most under-utilised faculty in absolute count, and who are they?"},
    {"id": "avg_load_by_rank", "area": "Faculty utilisation: school, rank and profile", "question": "What is the average load by rank this week?"},
    {"id": "long_day", "area": "Teaching pattern and distribution", "question": "Who teaches more than 5 hours on a single day?"},
    {"id": "busiest_days", "area": "Teaching pattern and distribution", "question": "Which days are the busiest for faculty?"},
    {"id": "five_days", "area": "Teaching pattern and distribution", "question": "Who teaches on all five days?"},
    {"id": "subject_load", "area": "Courses and subjects", "question": "Which subjects have the highest faculty load?"},
    {"id": "subject_teachers", "area": "Courses and subjects", "question": "Who teaches Data Structures?"},
    {"id": "ltpe_structure", "area": "Course LTPE and credits", "question": "What is the L-T-P-E structure of Calculus?"},
    {"id": "ltpe_practical", "area": "Course LTPE and credits", "question": "Which subjects have a practical component?"},
    {"id": "rooms_low_busy", "area": "Room utilisation", "question": "Which rooms are less than 20% busy?"},
    {"id": "rooms_low_busy", "area": "Room utilisation", "question": "Which rooms are less than 20% busy in SCSET?"},
    {"id": "busiest_rooms", "area": "Room utilisation", "question": "Which are the busiest rooms?"},
    {"id": "rooms_low_occupancy", "area": "Room capacity and seat occupancy", "question": "Which rooms have less than 50% occupancy?"},
    {"id": "rooms_large_low_occupancy", "area": "Room capacity and seat occupancy", "question": "Which large rooms have low seat occupancy?"},
    {"id": "free_people_and_rooms", "area": "Free rooms and faculty", "question": "Which faculty and rooms are free on Tuesday 2 to 4 pm?"},
    {"id": "rooms_vacant", "area": "Free rooms and faculty", "question": "Which rooms are vacant in SCSET on Monday at 10:30?"},
    {"id": "rooms_vacant_capacity", "area": "Free rooms and faculty", "question": "How many 60-seater rooms are vacant on Wednesday from 3 to 5 pm?"},
    {"id": "person_timetable", "area": "Timetable schedule", "question": "Provide the timetable schedule for Dr. Sana Bhardwaj this week"},
    {"id": "room_timetable", "area": "Timetable schedule", "question": "Show the timetable for room P-CC-015"},
    {"id": "staff_clashes", "area": "Clashes and timetable quality", "question": "Which faculty are booked in two places at once?"},
    {"id": "room_clashes", "area": "Clashes and timetable quality", "question": "Which rooms are double-booked?"},
    {"id": "phd_person", "area": "PhD supervision", "question": "What is the PhD supervision load of Dr. Sana Bhardwaj?"},
    {"id": "phd_top", "area": "PhD supervision", "question": "Which faculty supervise the most PhD scholars?"},
    {"id": "relaxation_justification", "area": "Load relaxation", "question": "What is the justification for Dr. Sana Bhardwaj's relaxation?"},
    {"id": "relaxation_compare", "area": "Load relaxation", "question": "What is the load of faculty with a relaxation compared to the rest?"},
    {"id": "school_gap", "area": "Mandate versus actual: school view", "question": "Which school has the largest gap between mandate and actual load?"},
    {"id": "school_hours", "area": "Mandate versus actual: school view", "question": "What is the total mandated and actual teaching hours of a school?"},
    {"id": "schools_meeting", "area": "Mandate versus actual: school view", "question": "Which schools are meeting their mandated load?"},
    {"id": "faculty_student_ratio", "area": "Faculty-student ratio (school level)", "question": "What is the faculty-student ratio by school?"},
    {"id": "faculty_student_ratio_phd", "area": "Faculty-student ratio (school level)", "question": "How is the ratio affected by counting full-time PhD scholars?"},
    {"id": "proxy_last_week", "area": "Comparison and trends", "question": "Compare this week with last week by school"},
    {"id": "proxy_semester", "area": "Comparison and trends", "question": "How has faculty utilisation changed over the semester?"},
    {"id": "proxy_last_month", "area": "Comparison and trends", "question": "Which schools improved their utilisation since last month?"},
    {"id": "weeks_loaded", "area": "Data checks", "question": "Which weeks of timetable data are loaded?"},
    {"id": "timetable_faculty_missing", "area": "Data checks", "question": "Which faculty in the timetable are missing from the Faculty Master?"},
    {"id": "inactive_staff", "area": "Data checks", "question": "Which faculty in the Faculty Master are inactive but still teaching?"},
    {"id": "timetable_rooms_missing", "area": "Data checks", "question": "Which rooms in the timetable are missing from the Room Master?"},
    {"id": "advice_room_busy", "area": "Advice and improvement", "question": "What can I do to improve Room Busy %?"},
    {"id": "advice_faculty_load", "area": "Advice and improvement", "question": "What are 3 things I should do to improve faculty load?"},
    {"id": "advice_seat_occupancy", "area": "Advice and improvement", "question": "How can I improve seat occupancy?"},
]

KNOWN_TEMPLATE_IDS = frozenset(item["id"] for item in TEMPLATES) | {
    "room_utilisation_summary",
    "seat_occupancy_summary",
}


def grouped() -> list[dict]:
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for item in TEMPLATES:
        if item["area"] not in groups:
            groups[item["area"]] = []
            order.append(item["area"])
        groups[item["area"]].append({"template_id": item["id"], "label": item["question"]})
    return [{"area": area, "questions": groups[area]} for area in order]


def related(template_id: str | None, limit: int = 3) -> list[dict]:
    area = next((item["area"] for item in TEMPLATES if item["id"] == template_id), None)
    pool = [item for item in TEMPLATES if item["area"] == area and item["id"] != template_id] if area else TEMPLATES
    seen: set[str] = set()
    chips = []
    for item in pool:
        if item["question"] in seen:
            continue
        seen.add(item["question"])
        chips.append({"template_id": item["id"], "label": item["question"]})
        if len(chips) >= limit:
            break
    return chips


def autocomplete(query: str, limit: int = 8) -> list[dict]:
    """Matching templates while the user types. The chosen text stays editable."""
    text = " ".join(query.lower().replace("-", " ").split())
    if len(text) < 2:
        return []
    tokens = [tok for tok in text.split() if len(tok) > 1]
    hits = []
    for item in TEMPLATES:
        question = item["question"].lower().replace("-", " ")
        if text in question or (tokens and all(tok in question for tok in tokens)):
            hits.append(item)
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for item in hits[:limit]:
        if item["area"] not in groups:
            groups[item["area"]] = []
            order.append(item["area"])
        groups[item["area"]].append({"template_id": item["id"], "label": item["question"]})
    return [{"area": area, "questions": groups[area]} for area in order]


def suggest_questions(message: str, limit: int = 3) -> list[dict]:
    tokens = {tok for tok in message.lower().replace("-", " ").split() if len(tok) > 3}
    scored = []
    for item in TEMPLATES:
        words = set(item["question"].lower().replace("-", " ").split())
        scored.append((len(tokens & words), item))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["question"]))
    chips = []
    seen: set[str] = set()
    for score, item in scored:
        if score <= 0 or item["question"] in seen:
            continue
        seen.add(item["question"])
        chips.append({"template_id": item["id"], "label": item["question"]})
        if len(chips) >= limit:
            break
    if chips:
        return chips
    return [{"template_id": item["id"], "label": item["question"]} for item in TEMPLATES[:limit]]
