CREATE TABLE IF NOT EXISTS staff (
    sr_no integer,
    staff_category text NOT NULL,
    staff_id text PRIMARY KEY,
    name text NOT NULL,
    designation text,
    gender text,
    home_department text
);

CREATE TABLE IF NOT EXISTS rooms (
    sno integer,
    school_name text,
    block text,
    floor text,
    room_number text PRIMARY KEY,
    seating_capacity integer,
    remarks text,
    room_description text
);

CREATE TABLE IF NOT EXISTS timetable_slots (
    sno integer,
    day text NOT NULL,
    period_name text NOT NULL,
    from_time time NOT NULL,
    to_time time NOT NULL,
    location text NOT NULL,
    subject_code text,
    subject_name text,
    credits numeric,
    staff_code text NOT NULL,
    staff_name text,
    section text,
    semester text,
    program text,
    school_name text,
    degree text,
    remarks text,
    session_type text,
    class_type text,
    enrollments integer,
    start_date date,
    end_date date
);

CREATE TABLE IF NOT EXISTS ltpe_courses (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course_id text,
    course_name text,
    display_code text,
    offering_department text,
    default_credit numeric,
    category text,
    sub_category text,
    course_type text,
    status text,
    lecturer_hours numeric,
    practical_hours numeric,
    tutorial_hours numeric,
    skill_hours numeric
);

CREATE TABLE IF NOT EXISTS ltpe_subject_dump (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject_code text,
    subject_name text
);

CREATE TABLE IF NOT EXISTS phd_supervision (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    department text,
    phd_scholar_staff_id text,
    phd_scholar_staff_name text,
    status text,
    faculty_mapped_staff_id text,
    faculty_mapped_staff_name text
);

CREATE TABLE IF NOT EXISTS staff_load_extract (
    staff_id text PRIMARY KEY,
    staff_name text,
    hours_relaxation numeric,
    mandated_hours numeric,
    school_name text
);

CREATE TABLE IF NOT EXISTS data_version (
    id integer PRIMARY KEY,
    loaded_at timestamptz NOT NULL,
    timetable_rows integer NOT NULL,
    staff_rows integer NOT NULL,
    room_rows integer NOT NULL,
    label text NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_threads (
    thread_id text PRIMARY KEY,
    persona text NOT NULL,
    state jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approved_questions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question_key text NOT NULL UNIQUE,
    question text NOT NULL,
    sql text NOT NULL,
    ask_count integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'pending',
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS email_drafts (
    thread_id text PRIMARY KEY,
    subject text NOT NULL,
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    sent_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_tt_staff ON timetable_slots (staff_code);
CREATE INDEX IF NOT EXISTS idx_tt_room ON timetable_slots (location);
CREATE INDEX IF NOT EXISTS idx_tt_school ON timetable_slots (school_name);
CREATE INDEX IF NOT EXISTS idx_tt_day ON timetable_slots (day);

CREATE OR REPLACE VIEW faculty_workload AS
SELECT
    s.staff_id,
    s.name,
    s.designation,
    s.staff_category,
    s.gender,
    s.home_department AS school_name,
    COALESCE(h.lecture_hours, 0)::numeric AS lecture_hours,
    COALESCE(h.practical_hours, 0)::numeric AS practical_hours,
    COALESCE(h.tutorial_hours, 0)::numeric AS tutorial_hours,
    COALESCE(h.teaching_hours, 0)::numeric AS teaching_hours,
    m.mandate_hours,
    0::numeric AS relaxation_hours,
    CASE WHEN m.mandate_hours IS NULL THEN NULL ELSE m.mandate_hours END AS effective_mandate,
    0::numeric AS phd_hours,
    TRUE AS phd_missing,
    TRUE AS experiential_excluded,
    COALESCE(h.teaching_hours, 0)::numeric AS actual_hours,
    CASE
        WHEN m.mandate_hours IS NULL THEN 'not_eligible'
        WHEN COALESCE(h.teaching_hours, 0) < m.mandate_hours THEN 'under'
        WHEN COALESCE(h.teaching_hours, 0) > m.mandate_hours THEN 'over'
        ELSE 'met'
    END AS status,
    CASE
        WHEN m.mandate_hours IS NULL OR m.mandate_hours = 0 THEN NULL
        ELSE round(100.0 * COALESCE(h.teaching_hours, 0) / m.mandate_hours, 1)
    END AS pct_of_mandate
FROM staff s
LEFT JOIN (
    SELECT
        staff_code,
        count(*) FILTER (WHERE session_type = 'Lecture') AS lecture_hours,
        count(*) FILTER (WHERE session_type = 'Practical') AS practical_hours,
        count(*) FILTER (WHERE session_type = 'Tutorial') AS tutorial_hours,
        count(*) AS teaching_hours
    FROM timetable_slots
    GROUP BY staff_code
) h ON h.staff_code = s.staff_id
LEFT JOIN (
    VALUES
        ('Professor & Dean'::text, 4::numeric),
        ('Professor', 10),
        ('Associate Professor', 12),
        ('Assistant Professor', 14),
        ('PhD Scholar', 8)
) AS m(designation, mandate_hours) ON m.designation = s.designation;

CREATE OR REPLACE VIEW room_utilisation AS
SELECT
    r.room_number,
    r.school_name,
    r.block,
    r.floor,
    r.seating_capacity,
    r.remarks,
    r.room_description,
    COALESCE(u.scheduled_hours, 0)::numeric AS scheduled_hours,
    round(100.0 * COALESCE(u.scheduled_hours, 0) / 45.0, 1) AS busy_pct,
    u.avg_occupancy_pct
FROM rooms r
LEFT JOIN (
    SELECT
        t.location AS room_number,
        count(*) AS scheduled_hours,
        round(avg(100.0 * t.enrollments / NULLIF(rm.seating_capacity, 0)), 1) AS avg_occupancy_pct
    FROM timetable_slots t
    JOIN rooms rm ON rm.room_number = t.location
    GROUP BY t.location
) u ON u.room_number = r.room_number;

CREATE OR REPLACE VIEW section_enrolment AS
SELECT DISTINCT ON (school_name, section)
    school_name,
    section,
    program,
    semester,
    enrollments
FROM timetable_slots
ORDER BY school_name, section, enrollments;

CREATE OR REPLACE VIEW timetable_detail AS
SELECT
    t.sno,
    t.day,
    t.period_name,
    t.from_time,
    t.to_time,
    t.location AS room_number,
    t.subject_code,
    t.subject_name,
    t.credits,
    t.staff_code,
    t.staff_name,
    t.section,
    t.semester,
    t.program,
    t.school_name,
    t.degree,
    t.session_type,
    t.class_type,
    t.enrollments,
    t.start_date,
    t.end_date,
    r.seating_capacity,
    round(100.0 * t.enrollments / NULLIF(r.seating_capacity, 0), 1) AS meeting_occupancy_pct,
    CASE t.day
        WHEN 'Monday' THEN 1
        WHEN 'Tuesday' THEN 2
        WHEN 'Wednesday' THEN 3
        WHEN 'Thursday' THEN 4
        WHEN 'Friday' THEN 5
        ELSE 6
    END AS day_order
FROM timetable_slots t
LEFT JOIN rooms r ON r.room_number = t.location;

CREATE OR REPLACE VIEW school_load_summary AS
SELECT
    school_name,
    count(*) FILTER (WHERE status <> 'not_eligible') AS eligible_faculty,
    count(*) FILTER (WHERE status = 'under') AS under_count,
    count(*) FILTER (WHERE status = 'over') AS over_count,
    count(*) FILTER (WHERE status = 'met') AS met_count,
    round(
        100.0 * count(*) FILTER (WHERE status = 'under')
        / NULLIF(count(*) FILTER (WHERE status <> 'not_eligible'), 0),
        1
    ) AS under_pct,
    COALESCE(sum(actual_hours) FILTER (WHERE status <> 'not_eligible'), 0) AS actual_hours,
    COALESCE(sum(effective_mandate) FILTER (WHERE status <> 'not_eligible'), 0) AS mandated_hours,
    COALESCE(sum(effective_mandate - actual_hours) FILTER (WHERE status <> 'not_eligible'), 0) AS gap_hours
FROM faculty_workload
GROUP BY school_name;

CREATE OR REPLACE VIEW faculty_student_ratio AS
WITH students AS (
    SELECT school_name, sum(enrollments) AS section_students, count(*) AS sections
    FROM section_enrolment
    GROUP BY school_name
),
row_students AS (
    SELECT school_name, sum(enrollments) AS row_sum_enrolment
    FROM timetable_slots
    GROUP BY school_name
),
faculty AS (
    SELECT home_department AS school_name, count(*) AS faculty_count
    FROM staff
    WHERE staff_category IN ('Teaching', 'Administrative & Teaching')
      AND designation <> 'PhD Scholar'
    GROUP BY home_department
),
staff_phd AS (
    SELECT home_department AS school_name, count(*) AS staff_phd_scholars
    FROM staff
    WHERE designation = 'PhD Scholar'
    GROUP BY home_department
),
schools AS (
    SELECT home_department AS school_name FROM staff
    UNION
    SELECT school_name FROM timetable_slots
)
SELECT
    sch.school_name,
    COALESCE(st.section_students, 0) AS section_students,
    COALESCE(st.sections, 0) AS sections,
    COALESCE(rs.row_sum_enrolment, 0) AS row_sum_enrolment,
    COALESCE(f.faculty_count, 0) AS faculty_count,
    CASE
        WHEN COALESCE(f.faculty_count, 0) = 0 THEN NULL
        ELSE round(COALESCE(st.section_students, 0)::numeric / f.faculty_count, 2)
    END AS baseline_ratio,
    COALESCE(sp.staff_phd_scholars, 0) AS staff_phd_scholars,
    CASE
        WHEN COALESCE(f.faculty_count, 0) + COALESCE(sp.staff_phd_scholars, 0) = 0 THEN NULL
        ELSE round(
            COALESCE(st.section_students, 0)::numeric
            / (f.faculty_count + COALESCE(sp.staff_phd_scholars, 0)),
            2
        )
    END AS ratio_with_staff_phd_in_denominator
FROM schools sch
LEFT JOIN students st ON st.school_name = sch.school_name
LEFT JOIN row_students rs ON rs.school_name = sch.school_name
LEFT JOIN faculty f ON f.school_name = sch.school_name
LEFT JOIN staff_phd sp ON sp.school_name = sch.school_name;

CREATE OR REPLACE VIEW phd_scholar_counts AS
SELECT
    department AS school_name,
    count(*) AS scholars,
    count(*) FILTER (WHERE status = 'Full Time') AS full_time_scholars,
    count(*) FILTER (WHERE status = 'Part Time') AS part_time_scholars
FROM phd_supervision
GROUP BY department;

CREATE OR REPLACE VIEW phd_supervision_scoped AS
SELECT
    department AS school_name,
    phd_scholar_staff_id,
    phd_scholar_staff_name,
    status,
    faculty_mapped_staff_id,
    faculty_mapped_staff_name
FROM phd_supervision;

CREATE OR REPLACE VIEW ltpe_catalog AS
SELECT
    course_id,
    course_name,
    display_code,
    offering_department AS school_name,
    lecturer_hours,
    practical_hours,
    tutorial_hours,
    skill_hours,
    default_credit
FROM ltpe_courses;

CREATE OR REPLACE VIEW staff_clashes AS
SELECT
    c.staff_code,
    s.name AS staff_name,
    s.home_department AS school_name,
    c.day,
    c.period_name,
    c.bookings,
    c.locations
FROM (
    SELECT
        staff_code,
        day,
        period_name,
        count(*) AS bookings,
        string_agg(DISTINCT location, ', ' ORDER BY location) AS locations
    FROM timetable_slots
    GROUP BY staff_code, day, period_name
    HAVING count(*) > 1
) c
JOIN staff s ON s.staff_id = c.staff_code;

CREATE OR REPLACE VIEW room_clashes AS
SELECT
    c.location AS room_number,
    r.school_name,
    c.day,
    c.period_name,
    c.bookings,
    c.staff_names
FROM (
    SELECT
        location,
        day,
        period_name,
        count(*) AS bookings,
        string_agg(DISTINCT staff_name, ', ' ORDER BY staff_name) AS staff_names
    FROM timetable_slots
    GROUP BY location, day, period_name
    HAVING count(*) > 1
) c
JOIN rooms r ON r.room_number = c.location;

CREATE OR REPLACE VIEW timetable_staff_gaps AS
SELECT
    t.staff_code,
    max(t.staff_name) AS staff_name,
    t.school_name,
    count(*) AS slots
FROM timetable_slots t
LEFT JOIN staff s ON s.staff_id = t.staff_code
WHERE s.staff_id IS NULL
GROUP BY t.staff_code, t.school_name;

CREATE OR REPLACE VIEW timetable_room_gaps AS
SELECT
    t.location AS room_number,
    t.school_name,
    count(*) AS slots
FROM timetable_slots t
LEFT JOIN rooms r ON r.room_number = t.location
WHERE r.room_number IS NULL
GROUP BY t.location, t.school_name;
