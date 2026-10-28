"""Lexical slots for people, schools, rooms, days, and clock windows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.metrics import CANONICAL_SCHOOLS, SCHOOL_ALIASES, periods_overlapping

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'").replace("`", "'")
    text = text.replace("dr.", " ").replace("prof.", " ")
    text = re.sub(r"[^a-z0-9%:+\-\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_school(text: str) -> str | None:
    """Map SCSET and exact school names. Do not alias the longer LTPE department onto Computer Science."""
    scrubbed = normalize(text)
    # "&" is removed by normalize, so the LTPE department collapses to this phrase.
    scrubbed = scrubbed.replace("school of computer science engineering technology", " ")
    scrubbed = scrubbed.replace("school of computer science engineering and technology", " ")
    for key, name in sorted(SCHOOL_ALIASES, key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", scrubbed):
            return name
    return None


def match_person(text: str, names: list[str]) -> list[str]:
    folded = normalize(text)
    hits: list[str] = []
    for name in names:
        token = normalize(name)
        if len(token) < 3:
            continue
        if re.search(rf"\b{re.escape(token)}\b", folded):
            hits.append(name)
    hits.sort(key=lambda name: len(normalize(name)), reverse=True)
    kept: list[str] = []
    for name in hits:
        token = normalize(name)
        if any(token != normalize(other) and token in normalize(other) for other in kept):
            continue
        kept.append(name)
    return kept


def _to_24(hour: str, minute: str | None, ampm: str | None) -> str:
    value = int(hour)
    mins = int(minute or "0")
    if ampm == "pm" and value < 12:
        value += 12
    if ampm == "am" and value == 12:
        value = 0
    return f"{value:02d}:{mins:02d}"


def _add_minute(hhmm: str) -> str:
    hour, minute = (int(part) for part in hhmm.split(":"))
    minute += 1
    if minute >= 60:
        hour += 1
        minute -= 60
    return f"{hour:02d}:{minute:02d}"


def parse_when(text: str) -> dict[str, str | None]:
    day_match = re.search(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        text,
    )
    day = day_match.group(1).capitalize() if day_match else None
    start = end = point = None
    range_match = re.search(
        r"\b(?:from\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:to|-)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
        text,
    )
    point_match = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))\s*(am|pm)?\b", text)
    if range_match:
        end_ampm = range_match.group(6)
        start_ampm = range_match.group(3) or end_ampm
        start = _to_24(range_match.group(1), range_match.group(2), start_ampm)
        end = _to_24(range_match.group(4), range_match.group(5), end_ampm)
    elif point_match:
        point = _to_24(point_match.group(1), point_match.group(2), point_match.group(3))
        start = point
        end = _add_minute(point)
    return {"day": day, "start": start, "end": end, "point": point}


_ROOM_RE = re.compile(r"\b[a-z0-9]+(?:-[a-z0-9]+)+\b")
# Lecture sections (BTCSE1-S1) and practical or tutorial batches (BALA1-S1-P1).
_SECTION_RE = re.compile(r"\b[a-z]{2,}[a-z0-9]*-s\d+(?:-[a-z]\d+)?\b")


def parse_section(text: str) -> str | None:
    match = _SECTION_RE.search(text)
    return match.group(0).upper() if match else None


def parse_room(text: str) -> str | None:
    for candidate in _ROOM_RE.findall(text):
        if "seat" in candidate or not any(character.isdigit() for character in candidate):
            continue
        if _SECTION_RE.fullmatch(candidate):
            continue
        return candidate.upper()
    return None


def parse_subject(text: str) -> str | None:
    patterns = (
        r"\bwho teaches\s+([a-z0-9][a-z0-9\s]+)$",
        r"\bstructure of\s+([a-z0-9][a-z0-9\s]+)$",
        r"\bl-t-p-e structure of\s+([a-z0-9][a-z0-9\s]+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return None


@dataclass
class Slots:
    person_name: str | None = None
    person_ambiguous: list[str] = field(default_factory=list)
    school: str | None = None
    room: str | None = None
    day: str | None = None
    start: str | None = None
    end: str | None = None
    point: str | None = None
    subject: str | None = None
    section: str | None = None
    seat_count: int | None = None
    busy_below: int | None = None
    occupancy_below: int | None = None
    hour_threshold: int | None = None

    def overlapping_periods(self) -> list[str]:
        if not self.start or not self.end:
            return []
        return periods_overlapping(self.start, self.end)


def extract_slots(message: str, names: list[str] | None = None) -> Slots:
    text = normalize(message)
    people = match_person(text, names or [])
    when = parse_when(text)
    seat = re.search(r"\b(\d+)\s*-?\s*seat", text)
    threshold = re.search(r"(?:less than|under|below)\s*(\d+)\s*(?:%|percent)", text)
    hours = re.search(r"more than\s+(\d+)\s+hours", text)
    subject = parse_subject(text)
    if subject is None and "data structures" in text:
        subject = "data structures"
    if subject is None and re.search(r"\bcalculus\b", text):
        subject = "calculus"
    return Slots(
        person_name=people[0] if len(people) == 1 else None,
        person_ambiguous=people if len(people) > 1 else [],
        school=canonical_school(text),
        room=parse_room(text),
        section=parse_section(text),
        day=when["day"],
        start=when["start"],
        end=when["end"],
        point=when["point"],
        subject=subject,
        seat_count=int(seat.group(1)) if seat else None,
        busy_below=int(threshold.group(1)) if threshold and "busy" in text else None,
        occupancy_below=int(threshold.group(1)) if threshold and "occupancy" in text else None,
        hour_threshold=int(hours.group(1)) if hours else None,
    )


def school_choices() -> list[str]:
    return list(CANONICAL_SCHOOLS)
