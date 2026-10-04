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
- ถามหน่วยกิตรายเทอมให้ใช้ v_semester_credits
- ถามรายวิชาตามแผนให้ใช้ v_plan
- ถามกฎระเบียบ เกียรตินิยม ภาคทัณฑ์ พ้นสภาพ การทุจริตสอบ การลงทะเบียน ให้ใช้ regulation
- ถามว่าวิชามีกี่หน่วยกิต ให้ใช้ course จากรหัสวิชา code (ตาราง course ไม่มีคอลัมน์ program_id ห้ามใส่ program_id ใน WHERE ของตาราง course) หรือใช้ v_plan
- หากคำถามไม่ได้ระบุชื่อหลักสูตร (เช่น IT, DSBA, BIT, AIT) ห้ามใส่เงื่อนไข program_id หรือ subquery หา program เด็ดขาด
- หากใช้ alias ให้ตาราง (เช่น prerequisite p หรือ course c) ต้องอ้างอิงคอลัมน์ผ่าน alias นั้นเสมอ ห้ามผสมชื่อตารางเดิม เช่น p.requires ห้ามเขียน prerequisite.requires
- สำหรับตาราง prerequisite ให้ระวังทิศทางความสัมพันธ์อย่างเคร่งครัด:
  1) หากถามว่า "วิชา X ต้องผ่าน/เรียนวิชาใดมาก่อน" หรือ "วิชาบังคับก่อนของ X คืออะไร":
     ให้หา requires โดยใช้: SELECT p.requires, c.name_th FROM prerequisite p JOIN course c ON p.requires = c.code WHERE p.code = 'รหัสวิชา X'
  2) หากถามว่า "ถ้าไม่ผ่าน/ติด F วิชา X จะลงวิชาอะไรไม่ได้บ้าง" หรือ "วิชา X เป็นวิชาบังคับก่อนของวิชาใดบ้าง" หรือ "วิชาต่อเนื่องของ X":
     ให้หา code ของวิชาต่อเนื่อง โดยใช้: SELECT p.code, c.name_th FROM prerequisite p JOIN course c ON p.code = c.code WHERE p.requires = 'รหัสวิชา X' (ห้ามใส่ WHERE p.code = 'รหัสวิชา X' เด็ดขาด และห้าม JOIN p.requires = c.code เด็ดขาด)
- ตาราง v_semester_credits เก็บหน่วยกิตของแต่ละปีและเทอมไว้แล้ว (คอลัมน์ credits คือหน่วยกิตของเทอมนั้น) หากถามว่าเทอมไหนเรียนหนักสุดหรือมีหน่วยกิตมากที่สุด ให้ SELECT year, semester, credits, n_courses FROM v_semester_credits ORDER BY credits DESC LIMIT 1 (ห้ามใช้ SUM(credits) หรือ GROUP BY semester เด็ดขาด)
- ห้ามแก้ไขฐานข้อมูล

ตัวอย่าง:
คำถาม: หลักสูตรนี้มีกี่หน่วยกิต
SQL: SELECT total_credits FROM program LIMIT 1
คำถาม: เทอมไหนเรียนหนักที่สุด
SQL: SELECT year, semester, credits, n_courses FROM v_semester_credits ORDER BY credits DESC LIMIT 1
คำถาม: เทอมไหนมีจำนวนหน่วยกิตรวมให้เรียนหนักที่สุด
SQL: SELECT year, semester, credits, n_courses FROM v_semester_credits ORDER BY credits DESC LIMIT 1
คำถาม: วิชาไหนเป็นวิชาบังคับก่อนให้วิชาอื่นมากที่สุด
SQL: SELECT c.code, c.name_th, COUNT(p.code) AS cnt FROM prerequisite p JOIN course c ON p.requires = c.code GROUP BY p.requires ORDER BY cnt DESC LIMIT 5
คำถาม: วิชาไหนเป็นวิชาบังคับก่อน (Prerequisite) ให้วิชาอื่นมากที่สุด 5 อันดับแรก
SQL: SELECT c.code, c.name_th, COUNT(p.code) AS cnt FROM prerequisite p JOIN course c ON p.requires = c.code GROUP BY p.requires ORDER BY cnt DESC LIMIT 5
คำถาม: วิชา 06036100 ในหลักสูตร BIT มีกี่หน่วยกิต
SQL: SELECT credits FROM course WHERE code = '06036100' LIMIT 1
คำถาม: วิชา 06036100 ในหลักสูตร BIT เรียนชั้นปีที่เท่าไร
SQL: SELECT year FROM plan_item WHERE code = '06036100' AND program_id LIKE 'BIT%' LIMIT 1
คำถาม: หลักสูตร IT มีกี่หน่วยกิต
SQL: SELECT total_credits FROM program WHERE program_id LIKE 'IT%' LIMIT 1
คำถาม: ปี 1 เทอม 1 เรียนกี่หน่วยกิต
SQL: SELECT credits FROM v_semester_credits WHERE year = 1 AND semester = 1 LIMIT 1
คำถาม: หลักสูตร IT ปี 1 เทอม 1 เรียนกี่หน่วยกิต
SQL: SELECT credits FROM v_semester_credits WHERE program_id LIKE 'IT%' AND year = 1 AND semester = 1 LIMIT 1
คำถาม: ปี 1 เทอม 1 เรียนกี่วิชา
SQL: SELECT n_courses FROM v_semester_credits WHERE year = 1 AND semester = 1 LIMIT 1
คำถาม: ปี 1 เทอม 1 เรียนวิชาอะไรบ้าง
SQL: SELECT code, name_th FROM v_plan WHERE year = 1 AND semester = 1 LIMIT 10
คำถาม: ต้องเรียนวิชาอะไรมาก่อนจึงจะลงเรียน 06026215 ได้
SQL: SELECT p.requires, c.name_th FROM prerequisite p LEFT JOIN course c ON p.requires = c.code WHERE p.code = '06026215' AND p.kind = 'pre'
คำถาม: วิชา 06016317 เป็นวิชาบังคับก่อนของวิชาใดบ้าง
SQL: SELECT p.code, c.name_th FROM prerequisite p LEFT JOIN course c ON p.code = c.code WHERE p.requires = '06016317'
คำถาม: ถ้าไม่ผ่านวิชา 06016317 จะลงวิชาอะไรไม่ได้บ้าง
SQL: SELECT p.code, c.name_th FROM prerequisite p LEFT JOIN course c ON p.code = c.code WHERE p.requires = '06016317'
คำถาม: ถ้าติด F วิชา 06016317 จะส่งผลกระทบต่อวิชาใดบ้าง
SQL: SELECT p.code, c.name_th FROM prerequisite p LEFT JOIN course c ON p.code = c.code WHERE p.requires = '06016317'
คำถาม: ถ้าไม่ผ่านวิชา 06026201 จะลงวิชาอะไรไม่ได้บ้าง
SQL: SELECT p.code, c.name_th FROM prerequisite p LEFT JOIN course c ON p.code = c.code WHERE p.requires = '06026201'
คำถาม: เกียรตินิยมอันดับ 1 เหรียญทองต้องได้เกรดเท่าไร
SQL: SELECT min_gpa FROM regulation WHERE category = 'เกณฑ์เกียรตินิยม' AND topic LIKE '%เหรียญทอง%' LIMIT 1
คำถาม: เกียรตินิยมอันดับ 1 ต้องได้เกรดเท่าไร
SQL: SELECT min_gpa FROM regulation WHERE category = 'เกณฑ์เกียรตินิยม' AND topic = 'เกียรตินิยมอันดับ 1' LIMIT 1
คำถาม: ทุจริตในการสอบจะถูกลงโทษอย่างไร
SQL: SELECT condition_desc, penalty_action, article_no FROM regulation WHERE category = 'เกณฑ์การทุจริตในการสอบ' LIMIT 1
คำถาม: การทุจริตในการสอบอ้างอิงข้อบังคับข้อใด
SQL: SELECT article_no FROM regulation WHERE category = 'เกณฑ์การทุจริตในการสอบ' LIMIT 1
คำถาม: นักศึกษาที่ได้ GPA ต่ำกว่าเท่าไรถึงจะถูกภาคทัณฑ์
SQL: SELECT condition_desc, max_gpa FROM regulation WHERE category = 'เกณฑ์ภาคทัณฑ์' AND topic LIKE '%ติดภาคทัณฑ์%' LIMIT 1
คำถาม: ลงทะเบียนเรียนภาคปกติได้ต่ำสุดกี่หน่วยกิต
SQL: SELECT min_credits FROM regulation WHERE category = 'เกณฑ์การลงทะเบียน' LIMIT 1
คำถาม: ลงทะเบียนเรียนภาคปกติได้สูงสุดกี่หน่วยกิต
SQL: SELECT max_credits FROM regulation WHERE category = 'เกณฑ์การลงทะเบียน' LIMIT 1
คำถาม: เกณฑ์การสำเร็จการศึกษาต้องได้ GPA เท่าไร
SQL: SELECT min_gpa FROM regulation WHERE category = 'เกณฑ์การสำเร็จการศึกษา' AND min_gpa IS NOT NULL LIMIT 1

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

    def ask(self, database: CurriculumDatabase, question: str) -> dict:
        sql, rows = database.query_from_model(self.make_sql(question))
        answer = self.summarize(question, rows) if rows else "ไม่พบข้อมูลนี้ในฐานข้อมูลหลักสูตร"
        return {"question": question, "sql": sql, "rows": rows, "answer": answer}
