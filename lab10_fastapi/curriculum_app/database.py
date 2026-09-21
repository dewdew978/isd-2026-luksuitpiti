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

    def courses(self, search: str = "", limit: int = 20, offset: int = 0) -> list[dict]:
        self._require_db()
        limit = min(max(limit, 1), self.max_rows)
        offset = max(offset, 0)
        sql = "SELECT * FROM course"
        params: list[object] = []
        if search.strip():
            sql += " WHERE code LIKE ? OR name_th LIKE ? OR name_en LIKE ?"
            pattern = f"%{search.strip()}%"
            params.extend([pattern, pattern, pattern])
        sql += " ORDER BY code LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        conn = self.lab8b.open_db(self.path, readonly=True)
        try:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
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
            conn.execute(
                "INSERT INTO course VALUES (?,?,?,?,?,?,?,?)",
                tuple(course.get(column) for column in columns),
            )
            conn.commit()
            return course
        finally:
            conn.close()

    def plan(
        self,
        year: int | None = None,
        semester: int | None = None,
        program_id: str | None = None,
    ) -> list[dict]:
        self._require_db()
        sql = "SELECT * FROM v_plan"
        conditions: list[str] = []
        params: list[object] = []
        if program_id and program_id.strip():
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
        sql += " ORDER BY program_id, year, semester, code"
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
    ) -> list[dict]:
        self._require_db()
        sql = "SELECT * FROM v_semester_credits"
        conditions: list[str] = []
        params: list[object] = []
        if program_id and program_id.strip():
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
        sql += " ORDER BY program_id, year, semester"
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
                sql = """
                    SELECT 
                        COUNT(DISTINCT c.code) AS total_courses,
                        COALESCE(SUM(c.credits), 0) AS total_credits,
                        COALESCE(SUM(c.lecture_h), 0) AS total_lecture_hours,
                        COALESCE(SUM(c.lab_h), 0) AS total_lab_hours,
                        COALESCE(SUM(c.self_h), 0) AS total_self_hours
                    FROM plan_item p
                    JOIN course c ON c.code = p.code
                    WHERE p.program_id = ?
                """
                row = conn.execute(sql, (prog,)).fetchone()
                res = dict(row) if row else {
                    "total_courses": 0, "total_credits": 0,
                    "total_lecture_hours": 0, "total_lab_hours": 0, "total_self_hours": 0,
                }
                res["program_id"] = prog
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


SQL_SCHEMA_CONTEXT = """
program(program_id, name_th, name_en, degree, total_credits, years)
course(code, name_th, name_en, credits, lecture_h, lab_h, self_h, description_th)
plan_item(id, program_id, year, semester, code, credits, alt_group, note)
prerequisite(code, requires, kind)
v_plan(id, program_id, year, semester, code, name_th, name_en, credits, alt_group, note)
v_semester_credits(program_id, year, semester, credits, n_courses)
""".strip()


