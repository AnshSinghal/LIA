"""Schema and metric retrieval. Qdrant when it is up, otherwise the same keyword catalog."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re

log = logging.getLogger("lia.retrieve")

DOCS = [
    {"title": "Workload", "text": "actual weekly load is timetable teaching hours. Each timetable row is 1 hour. Add 0.25 hours per PhD scholar only when the staff id is in phd_supervision. Experiential hours are excluded. Universe A relaxation is 0. Effective mandate is designation mandate minus relaxation. Under means actual < effective mandate. Over means actual > effective mandate. Mandates: Professor & Dean 4, Professor 10, Associate Professor 12, Assistant Professor 14, PhD Scholar 8. Visiting faculty, lab assistants, and lab technicians are not eligible."},
    {"title": "Rooms", "text": "room busy percent is scheduled hours divided by 45. Seat occupancy for a room is the average of enrolment divided by seating capacity across that room's timetable rows. Do not treat unused rooms as having an occupancy. A section id such as BTCSE1-S1 or BALA1-S1-P1 is not a room number."},
    {"title": "Section timetable", "text": "The weekly timetable for a section is the timetable_detail rows whose section equals that exact section id. A lecture section and its practical or tutorial batch are different ids. Filter section, not location or room_number."},
    {"title": "Ratio", "text": "Faculty-student numerator is one enrolment per section from section_enrolment. Do not sum enrolment on every timetable row. Denominator is staff in Teaching or Administrative & Teaching whose designation is not PhD Scholar. A lecture section and a practical batch are different section ids."},
    {"title": "Extracts", "text": "Universe A is staff, rooms, and timetable_slots. Universe B is staff_load_extract, phd_supervision, and ltpe_courses. Do not join them by person name. staff_load school_name is null. LTPE offering departments do not match timetable school names."},
    {"title": "Views", "text": "Allowlisted views include faculty_workload, room_utilisation, section_enrolment, timetable_detail, timetable_slots, school_load_summary, faculty_student_ratio, phd_supervision_scoped, ltpe_catalog, staff_clashes, room_clashes. Select school_name so the server can restrict a dean to the School of Computer Science."},
    {"title": "Window", "text": "The only timetable window is 17 Aug 2026 to 04 Sep 2026. Do not label it as last week, last month, or this semester."},
    {"title": "Example hours", "text": "Example: SELECT school_name, sum(actual_hours) AS teaching_hours FROM faculty_workload WHERE status <> 'not_eligible' GROUP BY school_name"},
    {"title": "Example rooms", "text": "Example: SELECT room_number, school_name, scheduled_hours, busy_pct FROM room_utilisation ORDER BY scheduled_hours DESC"},
    {"title": "Example programs", "text": "timetable_slots columns include program and school_name. Example: SELECT school_name, count(DISTINCT program) AS program_count FROM timetable_slots GROUP BY school_name"},
    {"title": "Example slot count", "text": "Example: SELECT school_name, count(*) AS slot_rows FROM timetable_slots GROUP BY school_name. There is no column named faculty_subject_dump or room_busy_percent."},
]


def embed(text: str, dims: int = 128) -> list[float]:
    vector = [0.0] * dims
    tokens = re.findall(r"[a-z0-9%]+", text.lower())
    if not tokens:
        vector[0] = 1.0
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:4], "little") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def keyword_search(question: str, limit: int = 6) -> list[dict]:
    tokens = set(re.findall(r"[a-z0-9%]+", question.lower()))
    scored = []
    for doc in DOCS:
        words = set(re.findall(r"[a-z0-9%]+", doc["text"].lower()))
        scored.append((len(tokens & words), doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [doc for score, doc in scored if score > 0][:limit] or DOCS[:limit]


def index_catalog() -> bool:
    url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    client = QdrantClient(url=url, timeout=3)
    if client.collection_exists("lia_catalog"):
        client.delete_collection("lia_catalog")
    client.create_collection(
        collection_name="lia_catalog",
        vectors_config=VectorParams(size=128, distance=Distance.COSINE),
    )
    client.upsert(
        collection_name="lia_catalog",
        points=[
            PointStruct(id=index, vector=embed(doc["title"] + " " + doc["text"]), payload=doc)
            for index, doc in enumerate(DOCS)
        ],
    )
    return True


def search(question: str) -> list[dict]:
    url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=url, timeout=2)
        found = client.query_points(collection_name="lia_catalog", query=embed(question), limit=6)
        points = getattr(found, "points", None) or []
        docs = [point.payload for point in points if getattr(point, "payload", None)]
        if docs:
            return docs
    except Exception as exc:
        log.info("qdrant search fallback: %s", exc)
    return keyword_search(question)
