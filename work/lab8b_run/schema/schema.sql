
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS program (
    program_id    TEXT PRIMARY KEY,
    name_th       TEXT NOT NULL,
    name_en       TEXT,
    degree        TEXT,
    total_credits INTEGER NOT NULL CHECK (total_credits BETWEEN 30 AND 300),
    years         INTEGER NOT NULL CHECK (years BETWEEN 1 AND 8)
);

CREATE TABLE IF NOT EXISTS study_plan (
    plan_id       TEXT PRIMARY KEY,
    program_id    TEXT NOT NULL REFERENCES program(program_id),
    name_th       TEXT NOT NULL,
    name_en       TEXT,
    plan_type     TEXT NOT NULL CHECK (plan_type IN ('coop', 'no_coop', 'single')),
    UNIQUE (plan_id, program_id)
);

CREATE TABLE IF NOT EXISTS course (
    code           TEXT PRIMARY KEY CHECK (code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
    name_th        TEXT NOT NULL,
    name_en        TEXT,
    credits        INTEGER NOT NULL CHECK (credits BETWEEN 0 AND 12),
    lecture_h      INTEGER,
    lab_h          INTEGER,
    self_h         INTEGER,
    description_th TEXT,
    pdf_pages      TEXT,
    printed_pages  TEXT
);

CREATE TABLE IF NOT EXISTS elective_slot (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id        TEXT NOT NULL REFERENCES study_plan(plan_id),
    year           INTEGER NOT NULL CHECK (year BETWEEN 1 AND 8),
    semester       INTEGER NOT NULL CHECK (semester BETWEEN 1 AND 3),
    slot_name_th   TEXT NOT NULL,
    slot_name_en   TEXT,
    code_pattern   TEXT,
    credits        INTEGER NOT NULL CHECK (credits BETWEEN 0 AND 12),
    credit_options TEXT,
    note           TEXT
);

CREATE TABLE IF NOT EXISTS plan_item (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id    TEXT NOT NULL,
    program_id TEXT NOT NULL,
    year       INTEGER NOT NULL CHECK (year BETWEEN 1 AND 8),
    semester   INTEGER NOT NULL CHECK (semester BETWEEN 1 AND 3),
    code       TEXT NOT NULL REFERENCES course(code),
    credits    INTEGER NOT NULL CHECK (credits BETWEEN 0 AND 12),
    alt_group  TEXT,
    note       TEXT,
    FOREIGN KEY (plan_id, program_id) REFERENCES study_plan(plan_id, program_id)
);

CREATE TABLE IF NOT EXISTS prerequisite (
    code     TEXT NOT NULL,
    requires TEXT NOT NULL,
    kind     TEXT NOT NULL CHECK (kind IN ('pre','co')),
    PRIMARY KEY (code, requires, kind)
);

CREATE TABLE IF NOT EXISTS program_course (
    program_id TEXT NOT NULL REFERENCES program(program_id),
    code       TEXT NOT NULL REFERENCES course(code),
    PRIMARY KEY (program_id, code)
);

CREATE INDEX IF NOT EXISTS ix_plan_sem ON plan_item(year, semester);
CREATE INDEX IF NOT EXISTS ix_plan_code ON plan_item(code);
CREATE INDEX IF NOT EXISTS ix_plan_plan_id ON plan_item(plan_id);
CREATE INDEX IF NOT EXISTS ix_slot_plan ON elective_slot(plan_id, year, semester);

CREATE VIEW IF NOT EXISTS v_plan AS
SELECT p.id, sp.plan_id, sp.plan_type, p.program_id, p.year, p.semester,
       p.code, c.name_th, c.name_en, p.credits, p.alt_group, p.note,
       c.pdf_pages, c.printed_pages, 0 AS is_elective_slot
FROM plan_item p
JOIN study_plan sp ON sp.plan_id = p.plan_id
LEFT JOIN course c ON c.code = p.code

UNION ALL

SELECT e.id + 100000 AS id, sp.plan_id, sp.plan_type, sp.program_id, e.year, e.semester,
       e.code_pattern AS code, e.slot_name_th AS name_th, e.slot_name_en AS name_en,
       e.credits, NULL AS alt_group, e.note,
       NULL AS pdf_pages, NULL AS printed_pages, 1 AS is_elective_slot
FROM elective_slot e
JOIN study_plan sp ON sp.plan_id = e.plan_id;

CREATE VIEW IF NOT EXISTS v_semester_credits AS
SELECT plan_id, program_id, year, semester, SUM(credits) AS credits, SUM(n_courses) AS n_courses
FROM (
    SELECT plan_id, program_id, year, semester, MAX(credits) AS credits, 1 AS n_courses
    FROM plan_item
    GROUP BY plan_id, program_id, year, semester, COALESCE(alt_group, 'x' || id)

    UNION ALL

    SELECT plan_id,
           (SELECT program_id FROM study_plan WHERE study_plan.plan_id = elective_slot.plan_id) AS program_id,
           year, semester, credits, 1 AS n_courses
    FROM elective_slot
)
GROUP BY plan_id, program_id, year, semester;

CREATE TABLE IF NOT EXISTS regulation (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id      TEXT DEFAULT 'ALL',
    category        TEXT NOT NULL,
    topic           TEXT NOT NULL,
    condition_desc  TEXT,
    min_gpa         REAL,
    max_gpa         REAL,
    min_credits     INTEGER,
    max_credits     INTEGER,
    penalty_action  TEXT,
    article_no      TEXT,
    source_page     INTEGER
);

CREATE INDEX IF NOT EXISTS ix_reg_cat ON regulation(category);
CREATE INDEX IF NOT EXISTS ix_reg_top ON regulation(topic);
