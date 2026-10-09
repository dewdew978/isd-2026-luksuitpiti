"""Curriculum DB adapter that reuses Lab 8B database functions."""

from pathlib import Path
from types import ModuleType


class CurriculumDatabase:
    def __init__(self, lab8b: ModuleType, path: Path, max_rows: int = 100):
        self.lab8b = lab8b
        self.path = path.resolve()
        self.max_rows = max_rows

    def _require_db(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"ไม่พบฐานข้อมูล: {self.path}")

    def program(self) -> dict | None:
        self._require_db()
        conn = self.lab8b.open_db(self.path, readonly=True)
        try:
            row = conn.execute("SELECT * FROM program LIMIT 1").fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def programs(self) -> list[dict]:
        self._require_db()
        conn = self.lab8b.open_db(self.path, readonly=True)
        try:
            rows = conn.execute(
                "SELECT program_id, name_th, name_en, degree, total_credits, years FROM program ORDER BY program_id"
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def courses(
        self,
        search: str = "",
        program_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        self._require_db()
        limit = min(max(limit, 1), self.max_rows)
        offset = max(offset, 0)
        sql = """
            SELECT c.*, GROUP_CONCAT(DISTINCT COALESCE(pc.program_id, p.program_id)) AS programs_str
            FROM course c
            LEFT JOIN program_course pc ON c.code = pc.code
            LEFT JOIN plan_item p ON c.code = p.code
        """
        conditions: list[str] = []
        params: list[object] = []
        if search.strip():
            conditions.append("(c.code LIKE ? OR c.name_th LIKE ? OR c.name_en LIKE ?)")
            pattern = f"%{search.strip()}%"
            params.extend([pattern, pattern, pattern])
        if program_id and program_id.strip() and program_id.strip().upper() != "ALL":
            conditions.append("(pc.program_id = ? OR p.program_id = ?)")
            prog_clean = program_id.strip().upper()
            params.extend([prog_clean, prog_clean])
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " GROUP BY c.code ORDER BY c.code LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        conn = self.lab8b.open_db(self.path, readonly=True)
        try:
            results = []
            for row in conn.execute(sql, params).fetchall():
                d = dict(row)
                p_str = d.pop("programs_str", None)
                d["programs"] = [p.strip() for p in p_str.split(",") if p.strip()] if p_str else []
                results.append(d)
            return results
        finally:
            conn.close()

    def create_course(self, course: dict) -> dict:
        self._require_db()
        columns = (
            "code", "name_th", "name_en", "credits", "lecture_h", "lab_h",
            "self_h", "description_th",
        )
        conn = self.lab8b.open_db(self.path)
        try:
            program_id = course.get("program_id")
            prog_clean = None
            effective_plan_id = None
            year = None
            semester = None

            if program_id and program_id.strip() and program_id.strip().upper() != "NONE":
                prog_clean = program_id.strip().upper()
                raw_year = course.get("year")
                raw_sem = course.get("semester")

                if raw_year is None or raw_sem is None:
                    raise ValueError("กรุณาระบุชั้นปี (year) และภาคการศึกษา (semester) เมื่อกำหนดหลักสูตร")
                try:
                    year = int(raw_year)
                    semester = int(raw_sem)
                except (ValueError, TypeError) as exc:
                    raise ValueError("ชั้นปี (year) และภาคการศึกษา (semester) ต้องเป็นตัวเลขจำนวนเต็ม") from exc

                if not (1 <= year <= 8):
                    raise ValueError("ชั้นปี (year) ต้องอยู่ระหว่าง 1 ถึง 8")
                if not (1 <= semester <= 3):
                    raise ValueError("ภาคการศึกษา (semester) ต้องอยู่ระหว่าง 1 ถึง 3")

                # Dynamic check of study plans for this program
                plan_rows = conn.execute(
                    "SELECT plan_id, plan_type FROM study_plan WHERE program_id = ?",
                    (prog_clean,),
                ).fetchall()
                available_plan_ids = [r["plan_id"] for r in plan_rows]

                req_plan_id = course.get("plan_id")
                if req_plan_id and req_plan_id.strip():
                    req_plan_id = req_plan_id.strip()
                    if req_plan_id not in available_plan_ids:
                        raise ValueError(
                            f"plan_id '{req_plan_id}' ไม่ถูกต้องสำหรับหลักสูตร {prog_clean} (แผนที่เป็นไปได้: {', '.join(available_plan_ids)})"
                        )
                    effective_plan_id = req_plan_id
                else:
                    if len(available_plan_ids) == 1:
                        # Exactly one plan (e.g. AIT_SINGLE): Safe to auto-fill
                        effective_plan_id = available_plan_ids[0]
                    elif len(available_plan_ids) > 1:
                        # Multiple plans: default to non-coop plan if omitted
                        non_coop_plans = [p for p in available_plan_ids if "NON_COOP" in p or "no_coop" in p.lower()]
                        effective_plan_id = non_coop_plans[0] if non_coop_plans else available_plan_ids[0]
                    else:
                        raise ValueError(f"ไม่พบแผนการศึกษาสำหรับหลักสูตร {prog_clean}")

                course["plan_id"] = effective_plan_id

            conn.execute(
                "INSERT INTO course (code, name_th, name_en, credits, lecture_h, lab_h, self_h, description_th) VALUES (?,?,?,?,?,?,?,?)",
                tuple(course.get(column) for column in columns),
            )

            if prog_clean and effective_plan_id:
                conn.execute(
                    "INSERT INTO plan_item (plan_id, program_id, year, semester, code, credits) VALUES (?,?,?,?,?,?)",
                    (effective_plan_id, prog_clean, year, semester, course["code"], course["credits"]),
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS program_course (program_id TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(program_id, code))"
                )
                conn.execute(
                    "INSERT OR IGNORE INTO program_course (program_id, code) VALUES (?,?)",
                    (prog_clean, course["code"]),
                )
            conn.commit()
            return course
        finally:
            conn.close()

    def course_prerequisites(self, code: str) -> dict | None:
        self._require_db()
        code = code.strip()
        if not code:
            return None
        conn = self.lab8b.open_db(self.path, readonly=True)
        try:
            course = conn.execute(
                "SELECT code, name_th, name_en, credits FROM course WHERE code = ?",
                (code,),
            ).fetchone()

            if course is None:
                has_prereq = conn.execute(
                    "SELECT 1 FROM prerequisite WHERE code = ? OR requires = ? LIMIT 1",
                    (code, code),
                ).fetchone()
                if not has_prereq:
                    return None
                name_th = None
                name_en = None
                credits = None
            else:
                code = course["code"]
                name_th = course["name_th"]
                name_en = course["name_en"]
                credits = course["credits"]

            req_rows = conn.execute(
                """
                SELECT 
                    p.requires AS code,
                    c.name_th,
                    c.name_en,
                    p.kind,
                    c.credits
                FROM prerequisite p
                LEFT JOIN course c ON c.code = p.requires
                WHERE p.code = ?
                ORDER BY p.requires
                """,
                (code,),
            ).fetchall()

            req_by_rows = conn.execute(
                """
                SELECT 
                    p.code AS code,
                    c.name_th,
                    c.name_en,
                    p.kind,
                    c.credits
                FROM prerequisite p
                LEFT JOIN course c ON c.code = p.code
                WHERE p.requires = ?
                ORDER BY p.code
                """,
                (code,),
            ).fetchall()

            requires_list = [dict(r) for r in req_rows]
            required_by_list = [dict(r) for r in req_by_rows]

            return {
                "code": code,
                "name_th": name_th,
                "name_en": name_en,
                "credits": credits,
                "requires": requires_list,
                "prerequisites": requires_list,
                "required_by": required_by_list,
            }
        finally:
            conn.close()


    def study_plans(self, program_id: str | None = None, plan_id: str | None = None) -> list[dict]:
        self._require_db()
        sql = "SELECT plan_id, program_id, name_th, name_en, plan_type FROM study_plan"
        conditions: list[str] = []
        params: list[object] = []
        if program_id and program_id.strip() and program_id.strip().upper() != "ALL":
            conditions.append("program_id = ?")
            params.append(program_id.strip().upper())
        if plan_id and plan_id.strip():
            conditions.append("plan_id = ?")
            params.append(plan_id.strip())
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY program_id, plan_id"
        conn = self.lab8b.open_db(self.path, readonly=True)
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def elective_slots(
        self,
        plan_id: str | None = None,
        year: int | None = None,
        semester: int | None = None,
    ) -> list[dict]:
        self._require_db()
        sql = "SELECT * FROM elective_slot"
        conditions: list[str] = []
        params: list[object] = []
        if plan_id and plan_id.strip():
            conditions.append("plan_id = ?")
            params.append(plan_id.strip())
        if year is not None:
            conditions.append("year = ?")
            params.append(year)
        if semester is not None:
            conditions.append("semester = ?")
            params.append(semester)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY plan_id, year, semester, id"
        conn = self.lab8b.open_db(self.path, readonly=True)
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def plan(
        self,
        year: int | None = None,
        semester: int | None = None,
        program_id: str | None = None,
        plan_id: str | None = None,
    ) -> list[dict]:
        self._require_db()
        sql = "SELECT * FROM v_plan"
        conditions: list[str] = []
        params: list[object] = []
        if plan_id and plan_id.strip():
            conditions.append("plan_id = ?")
            params.append(plan_id.strip())
        elif program_id and program_id.strip() and program_id.strip().upper() != "ALL":
            conditions.append("program_id = ?")
            params.append(program_id.strip().upper())
        if year is not None:
            conditions.append("year = ?")
            params.append(year)
        if semester is not None:
            conditions.append("semester = ?")
            params.append(semester)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY program_id, plan_id, year, semester, code"
        conn = self.lab8b.open_db(self.path, readonly=True)
        try:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def plan_summary(
        self,
        year: int | None = None,
        semester: int | None = None,
        program_id: str | None = None,
        plan_id: str | None = None,
    ) -> list[dict]:
        self._require_db()
        sql = "SELECT * FROM v_semester_credits"
        conditions: list[str] = []
        params: list[object] = []
        if plan_id and plan_id.strip():
            conditions.append("plan_id = ?")
            params.append(plan_id.strip())
        elif program_id and program_id.strip() and program_id.strip().upper() != "ALL":
            conditions.append("program_id = ?")
            params.append(program_id.strip().upper())
        if year is not None:
            conditions.append("year = ?")
            params.append(year)
        if semester is not None:
            conditions.append("semester = ?")
            params.append(semester)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY program_id, plan_id, year, semester"
        conn = self.lab8b.open_db(self.path, readonly=True)
        try:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def stats(self, program_id: str | None = None) -> dict:
        self._require_db()
        conn = self.lab8b.open_db(self.path, readonly=True)
        try:
            if program_id and program_id.strip():
                prog = program_id.strip().upper()
                prog_row = conn.execute(
                    "SELECT name_th, total_credits FROM program WHERE program_id = ?",
                    (prog,),
                ).fetchone()

                sql = """
                    WITH prog_courses AS (
                        SELECT DISTINCT c.code, c.credits, c.lecture_h, c.lab_h, c.self_h
                        FROM course c
                        LEFT JOIN program_course pc ON c.code = pc.code
                        LEFT JOIN plan_item p ON c.code = p.code
                        WHERE pc.program_id = ? OR p.program_id = ?
                    )
                    SELECT 
                        COUNT(*) AS total_courses,
                        COALESCE(SUM(credits), 0) AS total_credits,
                        COALESCE(SUM(lecture_h), 0) AS total_lecture_hours,
                        COALESCE(SUM(lab_h), 0) AS total_lab_hours,
                        COALESCE(SUM(self_h), 0) AS total_self_hours
                    FROM prog_courses
                """
                row = conn.execute(sql, (prog, prog)).fetchone()
                res = dict(row) if row else {
                    "total_courses": 0, "total_credits": 0,
                    "total_lecture_hours": 0, "total_lab_hours": 0, "total_self_hours": 0,
                }
                res["program_id"] = prog
                res["program_name_th"] = prog_row["name_th"] if prog_row else None
                res["program_total_credits"] = prog_row["total_credits"] if prog_row else None
                return res
            else:
                sql = """
                    SELECT 
                        COUNT(*) AS total_courses,
                        COALESCE(SUM(credits), 0) AS total_credits,
                        COALESCE(SUM(lecture_h), 0) AS total_lecture_hours,
                        COALESCE(SUM(lab_h), 0) AS total_lab_hours,
                        COALESCE(SUM(self_h), 0) AS total_self_hours
                    FROM course
                """
                row = conn.execute(sql).fetchone()
                res = dict(row) if row else {
                    "total_courses": 0, "total_credits": 0,
                    "total_lecture_hours": 0, "total_lab_hours": 0, "total_self_hours": 0,
                }
                res["program_id"] = None
                res["program_name_th"] = None
                res["program_total_credits"] = None
                return res
        finally:
            conn.close()

    def query_from_model(self, sql: str) -> tuple[str, list[dict]]:
        """Use Lab 8B's SQL guard and read-only connection directly."""
        self._require_db()
        safe_sql = self.lab8b.guard_sql(sql)
        conn = self.lab8b.open_db(self.path, readonly=True)
        try:
            rows = [dict(row) for row in conn.execute(safe_sql).fetchall()]
            return safe_sql, rows[:self.max_rows]
        finally:
            conn.close()

    def regulations(
        self,
        category: str | None = None,
        search: str = "",
        limit: int = 50,
    ) -> list[dict]:
        self._require_db()
        sql = "SELECT * FROM regulation"
        conditions: list[str] = []
        params: list[object] = []
        if category and category.strip():
            conditions.append("category = ?")
            params.append(category.strip())
        if search and search.strip():
            conditions.append("(topic LIKE ? OR condition_desc LIKE ? OR penalty_action LIKE ?)")
            pattern = f"%{search.strip()}%"
            params.extend([pattern, pattern, pattern])
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY id LIMIT ?"
        params.append(min(max(limit, 1), self.max_rows))
        conn = self.lab8b.open_db(self.path, readonly=True)
        try:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()


SQL_SCHEMA_CONTEXT = """
program(program_id, name_th, name_en, degree, total_credits, years)
study_plan(plan_id, program_id, name_th, name_en, plan_type) -- plan_type: 'coop', 'no_coop', 'single'
course(code, name_th, name_en, credits, lecture_h, lab_h, self_h, description_th)
plan_item(id, plan_id, program_id, year, semester, code, credits, alt_group, note)
elective_slot(id, plan_id, year, semester, slot_name_th, slot_name_en, code_pattern, credits, credit_options, note)
prerequisite(code, requires, kind)
v_plan(id, plan_id, plan_type, program_id, year, semester, code, name_th, name_en, credits, alt_group, note, is_elective_slot)
v_semester_credits(plan_id, program_id, year, semester, credits, n_courses)
regulation(id, program_id, category, topic, condition_desc, min_gpa, max_gpa, min_credits, max_credits, penalty_action, article_no, source_page)
""".strip()


