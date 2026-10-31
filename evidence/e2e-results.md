# LIA end-to-end evidence

Commands were run against the stack started with `docker compose up -d --build` from `/home/contact_cyberultron_com/lia`. API base `http://127.0.0.1:8010`. Web `http://127.0.0.1:8090`.

## 1. Compose

`docker compose up -d --build` exited 0. Images `lia-api` and `lia-web` built. Postgres became healthy, then the API, then the web container started.

## 2. Health

`GET /api/health` **200**

```json
{"status": "ok", "data_as_of": "2026-10-30T17:21:04.520239+00:00", "timetable_rows": 2073}
```

## 3. University persona

### Sana workload — 200, route `template`

Answer: Sana Bhardwaj (staff id 26982489), Assistant Professor in School of Computer Science, has **20** teaching hours this week against an effective mandate of **14**, so this is **over mandate**. PhD contribution is **0** because the staff id is absent from the supervision extract. Experiential hours are excluded because LTPE course codes do not match timetable subject codes. Relaxation applied here is 0.

Table cell: `actual_hours` 20, `effective_mandate` 14, `lecture_hours` 12, `practical_hours` 8, `tutorial_hours` 0, `phd_missing` true, `experiential_excluded` true, `pct_of_mandate` 142.9.

### Lecture / practical / tutorial — 200

`Lecture 12, practical 8, tutorial 0. Total teaching hours 20.`

### Room P-CC-015 — 200

`Room P-CC-015 is scheduled 15 hours out of 45, busy percent 33.3. The timetable has 15 rows.`

First meeting: Monday Period - 2, Sana Bhardwaj, Programming in C, enrolment 105 / capacity 240 = 43.8%.

### Under-utilised list — 200

`total_count` **105**, rows on page 1 **20**. Answer states this page is 20 of 105, not the full set. 33 people outside the five mandated designations are excluded.

### Weather — 200, route `refuse`

```json
{"route": "refuse", "answer": "Weather is outside this utilisation assistant.", "period": "not queried", "total_count": 0}
```

Trace line from `/traces/turns.jsonl` (sql is null):

```json
{"route": "refuse", "template_id": null, "sql": null, "row_count": 0, "message": "What is the weather in Delhi?"}
```

### Show occupancy — 200, route `clarify`

Question: "Do you mean room utilisation or faculty teaching load?" Options: Room utilisation, Faculty teaching load. `total_count` 0.

### Compare this week with last week — 200, route `template`

Answer does not call the loaded window last week. It says a comparison with a previous week is not possible, and the table is the loaded window offered as a labelled proxy. Period field: `17 Aug 2026 to 04 Sep 2026, one weekly pattern...` Column name: `loaded_window_teaching_hours`.

### Inactive faculty — 200, route `missing_data`

`This cannot be answered. The staff extract has no active-status column. Columns present: sr_no, staff_category, staff_id, name, designation, gender, home_department.`

## 4. Dean persona

Under-utilised list: `total_count` **45**, every returned `school_name` is School of Computer Science. Filters: persona dean_cs and the injected school predicate. No other school appears.

School of Law under-utilised request: `total_count` **0**, rows `[]`. Answer: School of Law is outside the School of Computer Science dean view, so no rows from that school are shown. SQL contains both `school_name = 'School of Law'` and `school_name = 'School of Computer Science'`.

## 5. Email

`POST /api/chat/confirm-email` `{"confirm": false}` **200**

```json
{"ok": false, "smtp_attempted": false, "error": "Confirmation is required before any email is sent."}
```

`{"confirm": true}` with SMTP env unset **200**

```json
{"ok": false, "smtp_attempted": false, "error": "SMTP is not configured. Missing: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, DATA_OWNER_EMAIL."}
```

No unhandled exception. SMTP was not contacted.

## 6. Ingest twice

```text
docker compose exec -T api python -m app.ingest
{'skipped': True, 'staff': 220, 'rooms': 225, 'timetable_slots': 2073, 'ltpe_courses': 4344, 'phd_supervision': 59, 'staff_load_extract': 640}
```

The same command a second time returned the same counts. `SELECT count(*) FROM timetable_slots` returned `(2073,)`.

## 7. Pytest

`cd apps/api && uv run pytest -q` → **74 passed**.

## 8. Web

`GET http://127.0.0.1:8090/` **200**, HTML title `LIA Utilization`.

Playwright opened that URL (persona University, data as of the health timestamp, timetable rows 2073) and clicked **What is the workload of Dr. Sana Bhardwaj this week?** The page then showed route `template` and the 20-versus-14 answer, including the PhD and experiential exclusions.

## 9. Dynamic path, no model

`How many distinct programs appear on the timetable?` **200**, route `dynamic`.

Answer: No model is configured, so this question was not sent to a SQL model and no figure was calculated. Suggestions were template questions. The answer contains no digits.

## 10. Faculty-student ratio spot check

University answer uses section enrolment **6366** for School of Computer Science and states that summing every timetable row would show **42440** and is not used. Baseline ratio **80.58** is 6366 / 79. The answer states a lecture section and its practical batch are different section ids.

## 11. Assignment leftovers, rechecked live on 2026-10-31

`uv run pytest -q` → **78 passed**.

`GET /api/suggest?q=sana%20workload` **200**. First match: `What is the workload of Dr. Sana Bhardwaj this week?`

Same thread, `Show her timetable` → route `template`, template `person_timetable`, **20** rows, staff id `26982489`.

`Compare this week with last week by school` → labelled proxy, not called last week. Options: `Email the data owner`, `Keep this loaded window`. The email chip stores a draft and does not send. Confirm still requires the separate confirm endpoint.

Unseen question through Ollama `llama3.2`, route `dynamic`, 2.6s: `SELECT school_name, COUNT(DISTINCT program) AS program_count FROM timetable_slots GROUP BY school_name`. **8** rows. Computer Science `program_count` is **4**. The number is the query result, not model prose.

`GET http://127.0.0.1:8090/` **200**.

## 12. Owner review of an unmatched question

`uv run pytest -q` → **79 passed**.

Unseen question, first ask: route `dynamic`, 0.47s, review `pending_owner_review` id 1, answer starts with “For owner review”, **8** rows.

Dean approve: **403** `Only a university user can approve a template.`

University approve: **200** `ok: true`.

Same question again: route `template`, 0.02s, label `Approved template`, still **8** rows. The model was not called.

Regressions on the same API: Sana still template 20 against 14. Weather still `refuse`. Under-utilised list still total **105**, page of **20**.
