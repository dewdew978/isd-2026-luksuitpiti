"""Qwen text-to-SQL adapter that reuses Lab 8B's Ollama helper."""

import json
import re
from types import ModuleType
from typing import Any

import requests

from .config import Settings
from .database import CurriculumDatabase, SQL_SCHEMA_CONTEXT


SQL_SCHEMA = {
    "type": "object",
    "properties": {"sql": {"type": "string"}},
    "required": ["sql"],
    "additionalProperties": False,
}
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


class QwenTextToSQL:
    def __init__(self, config: Settings, lab8b: ModuleType):
        self.config = config
        self.lab8b = lab8b

    def available(self) -> bool:
        try:
            return requests.get(
                f"{self.config.ollama_url}/api/tags", timeout=3
            ).ok
        except requests.RequestException:
            return False

    def _chat(self, prompt: str, schema: dict) -> dict:
        # MODEL INTEGRATION POINT: เปลี่ยนฟังก์ชันนี้หากไม่ใช้ Ollama/Qwen
        # เรียกฟังก์ชัน Ollama ของ Lab 8B โดยตรง เพื่อไม่สร้าง client ซ้ำใน Lab 10
        raw = self.lab8b.ollama_generate(
            prompt, fmt=schema, timeout=self.config.request_timeout,
            model=self.config.ollama_model, num_ctx=4096, num_predict=256,
        )
        return self.lab8b.parse_json_loose(raw)

    def make_sql(self, question: str) -> str:
        prompt = f"""แปลงคำถามเป็น SQLite SQL จาก schema นี้
{SQL_SCHEMA_CONTEXT}

กติกา:
- ตอบ SELECT หรือ WITH คำสั่งเดียว
- ถามหน่วยกิตรวม, หน่วยกิตรวมทั้งหมด, หน่วยกิตตลอดหลักสูตร, หรือหลักสูตรมีกี่หน่วยกิต ให้ใช้ total_credits จากตาราง program (เช่น SELECT total_credits FROM program LIMIT 1 หรือระบุ WHERE program_id = '...') ห้ามใช้ SUM(credits) FROM course เด็ดขาด เพราะตาราง course คือรายวิชาทั้งหมดของคณะ
- ถามหน่วยกิตรายเทอมให้ใช้ v_semester_credits
- ถามรายวิชาตามแผนให้ใช้ v_plan (หากนับจำนวนวิชาจริงในแผน ให้ใส่เงื่อนไข WHERE is_elective_slot = 0 เสมอ เพื่อไม่รวม slot รายวิชาเลือก)
- หากถามเกี่ยวกับแผนการเรียนหรือหน่วยกิตรายเทอม (จาก v_semester_credits หรือ v_plan):
  1) หากผู้ใช้ระบุแผน ให้กรองตามแผนที่ระบุ: แผนสหกิจศึกษาใช้ sp.plan_type = 'coop', แผนปกติใช้ sp.plan_type = 'no_coop' (ห้ามใช้ LIKE '%COOP%' เด็ดขาด)
  2) หากผู้ใช้ไม่ได้ระบุแผน ให้ใช้ค่าเริ่มต้น (Default) คือแผนปกติ: sp.plan_type = 'no_coop'
  3) หากผู้ใช้ไม่ได้ระบุหลักสูตร ให้ใช้ค่าเริ่มต้น (Default) คือหลักสูตร 'DSBA' (WHERE v.program_id = 'DSBA')
  โดยต้อง JOIN ตาราง study_plan sp ON sp.plan_id = v.plan_id เสมอ เช่น:
  SELECT v.credits FROM v_semester_credits AS v JOIN study_plan AS sp ON sp.plan_id = v.plan_id WHERE v.program_id = 'DSBA' AND sp.plan_type = 'no_coop' AND v.year = 1 AND v.semester = 2
- ถามกฎระเบียบ เกียรตินิยม ภาคทัณฑ์ พ้นสภาพ การทุจริตสอบ การลงทะเบียน ให้ใช้ regulation
- ถามว่าวิชามีกี่หน่วยกิต ให้ใช้ course จากรหัสวิชา code (ตาราง course ไม่มีคอลัมน์ program_id ห้ามใส่ program_id ใน WHERE ของตาราง course) หรือใช้ v_plan
- หากใช้ alias ให้ตาราง (เช่น prerequisite p หรือ course c หรือ v_semester_credits v) ต้องอ้างอิงคอลัมน์ผ่าน alias นั้นเสมอ ห้ามผสมชื่อตารางเดิม เช่น p.requires ห้ามเขียน prerequisite.requires
- สำหรับตาราง prerequisite ให้ระวังทิศทางความสัมพันธ์อย่างเคร่งครัด:
  1) หากถามว่า "วิชา X ต้องผ่าน/เรียนวิชาใดมาก่อน" หรือ "วิชาบังคับก่อนของ X คืออะไร":
     ให้หา requires โดยใช้: SELECT p.requires, c.name_th FROM prerequisite p JOIN course c ON p.requires = c.code WHERE p.code = 'รหัสวิชา X'
  2) หากถามว่า "ถ้าไม่ผ่าน/ติด F วิชา X จะลงวิชาอะไรไม่ได้บ้าง" หรือ "วิชา X เป็นวิชาบังคับก่อนของวิชาใดบ้าง" หรือ "วิชาต่อเนื่องของ X":
     ให้หา code ของวิชาต่อเนื่อง โดยใช้: SELECT p.code, c.name_th FROM prerequisite p JOIN course c ON p.code = c.code WHERE p.requires = 'รหัสวิชา X' (ห้ามใส่ WHERE p.code = 'รหัสวิชา X' เด็ดขาด และห้าม JOIN p.requires = c.code เด็ดขาด)
- ตาราง v_semester_credits เก็บหน่วยกิตของแต่ละปีและเทอมไว้แล้ว (คอลัมน์ credits คือหน่วยกิตของเทอมนั้น) หากถามว่าเทอมไหนเรียนหนักสุดหรือมีหน่วยกิตมากที่สุด ให้ SELECT year, semester, credits, n_courses FROM v_semester_credits ORDER BY credits DESC LIMIT 1 (ห้ามใช้ SUM(credits) หรือ GROUP BY semester เด็ดขาด)
- ห้ามแก้ไขฐานข้อมูล
- ถ้าคำถามมีแค่รหัสวิชา 8 หลัก อย่างเดียว (เช่น 06036100, 06026201) ให้ใช้รหัสวิชานั้นตรง ๆ ใน WHERE (เช่น WHERE code = '06036100') ห้ามแปลงเป็นชื่อวิชาเด็ดขาด โดยใช้ SELECT c.name_th, c.name_en ,c.credits FROM course c WHERE c.code = '06036100' LIMIT 1
- ถามกฎเกียรตินิยมให้เช็กคอลัมน์ topic จากตาราง regulation โดยระบุค่าให้ตรงกับชื่อหัวข้อ (เช่น topic = 'เกียรตินิยมอันดับ 1 เหรียญทอง', topic = 'เกียรตินิยมอันดับ 1', หรือ topic = 'เกียรตินิยมอันดับ 2')
- หากคำถามเป็นการระบุรหัสวิชาเพียวๆ ให้ดึงชื่อวิชาไทย, อังกฤษ และหน่วยกิต โดยใช้: SELECT c.name_th, c.name_en, c.credits FROM course c WHERE c.code = 'รหัสวิชา'

ตัวอย่าง:
คำถาม: หลักสูตรนี้มีกี่หน่วยกิต
SQL: SELECT total_credits FROM program WHERE program_id = 'DSBA' LIMIT 1
คำถาม: หลักสูตรนี้มีหน่วยกิตรวมทั้งหมดเท่าไร
SQL: SELECT total_credits FROM program WHERE program_id = 'DSBA' LIMIT 1
คำถาม: หน่วยกิตรวมตลอดหลักสูตรมีเท่าไร
SQL: SELECT total_credits FROM program WHERE program_id = 'DSBA' LIMIT 1
คำถาม: เทอมไหนเรียนหนักที่สุด
SQL: SELECT v.year, v.semester, v.credits, v.n_courses FROM v_semester_credits AS v JOIN study_plan AS sp ON sp.plan_id = v.plan_id WHERE v.program_id = 'DSBA' AND sp.plan_type = 'no_coop' ORDER BY v.credits DESC LIMIT 1
คำถาม: เทอมไหนมีจำนวนหน่วยกิตรวมให้เรียนหนักที่สุด
SQL: SELECT v.year, v.semester, v.credits, v.n_courses FROM v_semester_credits AS v JOIN study_plan AS sp ON sp.plan_id = v.plan_id WHERE v.program_id = 'DSBA' AND sp.plan_type = 'no_coop' ORDER BY v.credits DESC LIMIT 1
คำถาม: วิชาไหนเป็นวิชาบังคับก่อนให้วิชาอื่นมากที่สุด
SQL: SELECT c.code, c.name_th, COUNT(p.code) AS cnt FROM prerequisite p JOIN course c ON p.requires = c.code GROUP BY p.requires ORDER BY cnt DESC LIMIT 5
คำถาม: วิชาไหนเป็นวิชาบังคับก่อน (Prerequisite) ให้วิชาอื่นมากที่สุด 5 อันดับแรก
SQL: SELECT c.code, c.name_th, COUNT(p.code) AS cnt FROM prerequisite p JOIN course c ON p.requires = c.code GROUP BY p.requires ORDER BY cnt DESC LIMIT 5
คำถาม: วิชา 06036100 ในหลักสูตร BIT มีกี่หน่วยกิต
SQL: SELECT credits FROM course WHERE code = '06036100' LIMIT 1
คำถาม: วิชา 06036100 ในหลักสูตร BIT เรียนชั้นปีที่เท่าไร
SQL: SELECT year FROM plan_item WHERE code = '06036100' AND program_id LIKE 'BIT%' LIMIT 1
คำถาม: 06036100
SQL: SELECT c.name_th, c.name_en, c.credits FROM course c WHERE c.code = '06036100' LIMIT 1
คำถาม: หลักสูตร IT มีกี่หน่วยกิต
SQL: SELECT total_credits FROM program WHERE program_id LIKE 'IT%' LIMIT 1
คำถาม: แผนสหกิจของ IT มีกี่วิชา
SQL: SELECT COUNT(*) FROM v_plan p JOIN study_plan sp ON p.plan_id = sp.plan_id WHERE p.program_id LIKE 'IT%' AND sp.plan_type = 'coop' AND p.is_elective_slot = 0
คำถาม: แผนปกติของ IT ปี 1 เทอม 1 เรียนวิชาอะไรบ้าง
SQL: SELECT p.code, p.name_th FROM v_plan p JOIN study_plan sp ON p.plan_id = sp.plan_id WHERE p.program_id LIKE 'IT%' AND sp.plan_type = 'no_coop' AND p.year = 1 AND p.semester = 1 AND p.is_elective_slot = 0
คำถาม: ปี 1 เทอม 1 เรียนกี่หน่วยกิต
SQL: SELECT v.credits FROM v_semester_credits AS v JOIN study_plan AS sp ON sp.plan_id = v.plan_id WHERE v.program_id = 'DSBA' AND sp.plan_type = 'no_coop' AND v.year = 1 AND v.semester = 1
คำถาม: ปี 1 เทอม 2 เรียนกี่หน่วยกิต
SQL: SELECT v.credits FROM v_semester_credits AS v JOIN study_plan AS sp ON sp.plan_id = v.plan_id WHERE v.program_id = 'DSBA' AND sp.plan_type = 'no_coop' AND v.year = 1 AND v.semester = 2
คำถาม: หลักสูตร IT ปี 1 เทอม 1 เรียนกี่หน่วยกิต
SQL: SELECT v.credits FROM v_semester_credits AS v JOIN study_plan AS sp ON sp.plan_id = v.plan_id WHERE v.program_id LIKE 'IT%' AND sp.plan_type = 'no_coop' AND v.year = 1 AND v.semester = 1
คำถาม: ปี 1 เทอม 1 เรียนกี่วิชา
SQL: SELECT v.n_courses FROM v_semester_credits AS v JOIN study_plan AS sp ON sp.plan_id = v.plan_id WHERE v.program_id = 'DSBA' AND sp.plan_type = 'no_coop' AND v.year = 1 AND v.semester = 1
คำถาม: ปี 1 เทอม 1 เรียนวิชาอะไรบ้าง
SQL: SELECT p.code, p.name_th FROM v_plan AS p JOIN study_plan AS sp ON sp.plan_id = p.plan_id WHERE p.program_id = 'DSBA' AND sp.plan_type = 'no_coop' AND p.year = 1 AND p.semester = 1 AND p.is_elective_slot = 0 LIMIT 10
คำถาม: ต้องเรียนวิชาอะไรมาก่อนจึงจะลงเรียน 06026215 ได้
SQL: SELECT p.requires, c.name_th FROM prerequisite p LEFT JOIN course c ON p.requires = c.code WHERE p.code = '06026215' AND p.kind = 'pre'
คำถาม: ถ้าไม่ผ่านวิชา 06026201 จะลงวิชาอะไรไม่ได้บ้าง
SQL: SELECT p.code, c.name_th FROM prerequisite p LEFT JOIN course c ON p.code = c.code WHERE p.requires = '06026201'
คำถาม: เกียรตินิยมอันดับ 1 เหรียญทองต้องได้เกรดเท่าไร
SQL: SELECT min_gpa, topic, article_no, source_page FROM regulation WHERE category = 'เกณฑ์เกียรตินิยม' AND topic = 'เกียรตินิยมอันดับ 1 เหรียญทอง' LIMIT 1
คำถาม: เกียรตินิยมอันดับ 1 ต้องได้เกรดเท่าไร
SQL: SELECT min_gpa, topic, article_no, source_page FROM regulation WHERE category = 'เกณฑ์เกียรตินิยม' AND topic = 'เกียรตินิยมอันดับ 1' LIMIT 1
คำถาม: เกียรตินิยมอันดับ 2 ต้องได้เกรดเท่าไร
SQL: SELECT min_gpa, topic, article_no, source_page FROM regulation WHERE category = 'เกณฑ์เกียรตินิยม' AND topic = 'เกียรตินิยมอันดับ 2' LIMIT 1
คำถาม: ทุจริตในการสอบจะถูกลงโทษอย่างไร
SQL: SELECT condition_desc, penalty_action, article_no, source_page FROM regulation WHERE category = 'เกณฑ์การทุจริตในการสอบ' LIMIT 1
คำถาม: การทุจริตในการสอบอ้างอิงข้อบังคับข้อใด
SQL: SELECT article_no, source_page FROM regulation WHERE category = 'เกณฑ์การทุจริตในการสอบ' LIMIT 1
คำถาม: นักศึกษาที่ได้ GPA ต่ำกว่าเท่าไรถึงจะถูกภาคทัณฑ์
SQL: SELECT condition_desc, max_gpa, article_no, source_page FROM regulation WHERE category = 'เกณฑ์ภาคทัณฑ์' AND topic LIKE '%ติดภาคทัณฑ์%' LIMIT 1
คำถาม: ลงทะเบียนเรียนภาคปกติได้ต่ำสุดกี่หน่วยกิต
SQL: SELECT min_credits, article_no, source_page FROM regulation WHERE category = 'เกณฑ์การลงทะเบียน' LIMIT 1
คำถาม: ลงทะเบียนเรียนภาคปกติได้สูงสุดกี่หน่วยกิต
SQL: SELECT max_credits, article_no, source_page FROM regulation WHERE category = 'เกณฑ์การลงทะเบียน' LIMIT 1
คำถาม: เกณฑ์การสำเร็จการศึกษาต้องได้ GPA เท่าไร
SQL: SELECT min_gpa, article_no, source_page FROM regulation WHERE category = 'เกณฑ์การสำเร็จการศึกษา' AND min_gpa IS NOT NULL LIMIT 1

คำถาม: {question}
ตอบ JSON ที่มี key ชื่อ sql"""
        sql = str(self._chat(prompt, SQL_SCHEMA).get("sql", "")).strip()
        return re.sub(r"^```(?:sql)?|```$", "", sql, flags=re.MULTILINE).strip()

    def summarize(self, question: str, rows: list[dict[str, Any]]) -> str:
        prompt = f"""ตอบภาษาไทยจากผลฐานข้อมูลเท่านั้น
คำถาม: {question}
ผลฐานข้อมูล: {json.dumps(rows[:40], ensure_ascii=False)}
ตอบ JSON ที่มี key ชื่อ answer และห้ามเพิ่มข้อมูลที่ไม่มีในผล"""
        
        return str(self._chat(prompt, ANSWER_SCHEMA).get("answer", "")).strip()

    def extract_sources(self, database: CurriculumDatabase, question: str, sql: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        seen = set()

        # 1. ตรวจสอบข้อมูลข้อบังคับ (regulations) จาก rows
        for r in rows:
            if any(k in r for k in ("article_no", "condition_desc", "penalty_action", "source_page")):
                title = str(r.get("topic") or r.get("category") or "ข้อบังคับสถาบันฯ").strip()
                art = r.get("article_no")
                spage = r.get("source_page")
                key = f"reg:{title}:{art}"
                if key not in seen:
                    seen.add(key)
                    sources.append({
                        "type": "regulation",
                        "title": title,
                        "article_no": art,
                        "printed_pages": str(spage) if spage else None,
                        "pdf_pages": None,
                    })

        # 2. ตรวจสอบข้อมูลรายวิชา (course) จาก rows หรือ question
        codes_found: list[str] = []
        for r in rows:
            for k in ("code", "requires"):
                val = str(r.get(k) or "").strip()
                if re.match(r"^\d{8}$", val) and val not in codes_found:
                    codes_found.append(val)
            for v in r.values():
                for c in re.findall(r"\b\d{8}\b", str(v)):
                    if c not in codes_found:
                        codes_found.append(c)

        for c in re.findall(r"\b\d{8}\b", question):
            if c not in codes_found:
                codes_found.append(c)

        if codes_found:
            try:
                conn = self.lab8b.open_db(database.path, readonly=True)
                cols = [col[1] for col in conn.execute("PRAGMA table_info(course)").fetchall()]
                for code in codes_found[:6]:
                    row = conn.execute("SELECT * FROM course WHERE code = ?", (code,)).fetchone()
                    if row:
                        name_th = row["name_th"]
                        printed = row["printed_pages"] if "printed_pages" in cols else None
                        pdf_p = row["pdf_pages"] if "pdf_pages" in cols else None
                        key = f"course:{code}"
                        if key not in seen:
                            seen.add(key)
                            sources.append({
                                "type": "course",
                                "code": code,
                                "title": f"{code} {name_th}" if name_th else code,
                                "printed_pages": printed,
                                "pdf_pages": pdf_p,
                            })
                conn.close()
            except Exception:
                pass

        # 3. คำถามเกี่ยวกับโครงสร้างหลักสูตร (program) หรือแผนการเรียน (plan)
        if not sources and any(t in sql.lower() for t in ("from program", "total_credits", "degree", "v_semester_credits", "v_plan", "plan_item")):
            sources.append({
                "type": "program",
                "title": "เล่มหลักสูตร",
                "printed_pages": "หมวดที่ 3",
                "pdf_pages": None,
            })

        return sources

    def ask(self, database: CurriculumDatabase, question: str) -> dict:
        sql = self.make_sql(question)
        sql, rows = database.query_from_model(sql)
        answer = self.summarize(question, rows) if rows else "ไม่พบข้อมูลนี้ในฐานข้อมูลหลักสูตร"
        sources = self.extract_sources(database, question, sql, rows)
        return {"question": question, "sql": sql, "rows": rows, "answer": answer, "sources": sources}
