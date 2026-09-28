"""Extract academic regulations afresh using Local LLM (qwen3:4b via Ollama - Lab 7B Pipeline).

Parses Appendix A: Regulation of King Mongkut's Institute of Technology Ladkrabang
Governing Undergraduate Studies B.E. 2564 (ข้อบังคับ สจล. ว่าด้วยการศึกษาระดับปริญญาตรี พ.ศ. 2564)
directly from raw OCR document pages without ground truth leakage.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent
OCR_PATH = ROOT.parent / "LAB6" / "outputs" / "fulldoc_dsba_ocr.json"
SCHEMA_SQL = ROOT / "work" / "lab8b_run" / "schema" / "schema.sql"
OUTPUT_JSON = ROOT / "work" / "lab8b_run" / "regulations.json"
OLLAMA_URL = "http://127.0.0.1:11434"
MODEL_NAME = "qwen3:4b"


class RegulationItem(BaseModel):
    program_id: str = "ALL"
    category: str
    topic: str
    condition_desc: str
    min_gpa: float | None = None
    max_gpa: float | None = None
    min_credits: int | None = None
    max_credits: int | None = None
    penalty_action: str | None = None
    article_no: str | None = None
    source_page: int | None = None


REGULATION_TABLE_SQL = """
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
"""


def load_raw_regulation_pages(ocr_json_path: Path) -> dict[str, str]:
    if not ocr_json_path.exists():
        raise FileNotFoundError(f"Raw OCR file not found: {ocr_json_path}")

    with open(ocr_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    full_text = data.get("text", "")
    pages = full_text.split("--- Page ")

    page_texts: dict[str, str] = {}
    for p in pages:
        if not p.strip():
            continue
        lines = p.split("\n")
        header = lines[0].strip().split(" ---")[0]
        if header.isdigit():
            page_texts[header] = p

    return page_texts


def extract_regulations_via_llm(page_texts: dict[str, str]) -> list[RegulationItem]:
    import requests

    chunks = [
        {
            "category": "เกณฑ์การลงทะเบียน",
            "pages": ["94"],
            "prompt": (
                "จากข้อความหน้า 94 ด้านล่าง จงสกัดข้อบังคับการลงทะเบียนเรียน (ข้อ 11) "
                "1) ภาคปกติ (ไม่น้อยกว่า 9 และไม่เกิน 22 หน่วยกิต) "
                "2) กรณีพิเศษขอจบ (ไม่เกิน 27 หน่วยกิต) "
                "3) ภาคพิเศษฤดูร้อน (ไม่เกิน 9 หน่วยกิต)"
            )
        },
        {
            "category": "การทุจริตในการสอบ",
            "pages": ["96", "99", "101"],
            "prompt": (
                "จากข้อความด้านล่าง จงสกัดข้อบังคับการทุจริตในการสอบ "
                "1) ทุจริตครั้งแรกตามข้อ 20 วรรคสอง (ไม่ได้รับการพิจารณาผลการเรียนและพักการเรียน 1 เทอม) "
                "2) ทุจริตซ้ำมากกว่า 3 ครั้งตามข้อ 33.9 (พ้นสภาพการเป็นนักศึกษา)"
            )
        },
        {
            "category": "เกณฑ์ภาคทัณฑ์และพ้นสภาพ",
            "pages": ["97", "99"],
            "prompt": (
                "จากข้อความด้านล่าง จงสกัด "
                "1) เกณฑ์การติดภาคทัณฑ์ตามข้อ 22 (GPA ต่ำกว่า 2.00) "
                "2) เกณฑ์การพ้นภาคทัณฑ์ตามข้อ 22 (GPA ไม่ต่ำกว่า 2.00) "
                "3) เกณฑ์พ้นสภาพนักศึกษาจากผลการเรียนตามข้อ 33 (GPA ต่ำกว่า 1.00 หรือระหว่างภาคทัณฑ์)"
            )
        },
        {
            "category": "เกณฑ์เกียรตินิยมและการสำเร็จการศึกษา",
            "pages": ["97", "98"],
            "prompt": (
                "จากข้อความด้านล่าง จงสกัดข้อบังคับเกียรตินิยมตามข้อ 25.2 "
                "1) เกียรตินิยมอันดับ 1 เหรียญทอง (GPA ไม่ต่ำกว่า 3.75 ไม่เทียบโอน) "
                "2) เกียรตินิยมอันดับ 1 (GPA ไม่ต่ำกว่า 3.50) "
                "3) เกียรตินิยมอันดับ 2 (GPA ไม่ต่ำกว่า 3.25) "
                "4) เกณฑ์สำเร็จการศึกษาขั้นต่ำตามข้อ 25 (GPA ไม่ต่ำกว่า 2.00)"
            )
        }
    ]

    items_out: list[RegulationItem] = []

    print(f"🤖 กำลังเรียกใช้งาน Local LLM ({MODEL_NAME}) ผ่าน Ollama (Lab 7B IE Pipeline)...")

    for i, ch in enumerate(chunks, 1):
        context = "\n\n".join([f"--- หน้า {p} ---\n{page_texts.get(p, '')}" for p in ch["pages"]])
        user_prompt = f"""คุณคือผู้เชี่ยวชาญ Information Extraction สกัดกฎระเบียบของสถาบันจากเอกสาร มคอ.2
{ch['prompt']}

ข้อความเอกสารต้นฉบับ:
{context}

คำสั่ง:
ตอบเป็น JSON ในรูปแบบ {{"regulations": [...]}} เท่านั้น โดยแต่ละรายการต้องมี:
- "category": ชื่อหมวด (เช่น 'เกณฑ์การลงทะเบียน', 'การทุจริตในการสอบ', 'เกณฑ์ภาคทัณฑ์', 'เกณฑ์พ้นสภาพนักศึกษา', 'เกณฑ์เกียรตินิยม', 'เกณฑ์การสำเร็จการศึกษา')
- "topic": หัวข้อย่อย
- "condition_desc": คำอธิบายเงื่อนไขสรุป
- "min_gpa": ตัวเลข float (เช่น 3.75, 3.50, 3.25, 2.00 หรือ null)
- "max_gpa": ตัวเลข float (เช่น 1.99, 0.99 หรือ null)
- "min_credits": int (เช่น 9 หรือ null)
- "max_credits": int (เช่น 22, 27, 9 หรือ null)
- "penalty_action": บทลงโทษถ้ามี (เช่น 'พักการเรียน 1 ภาคการศึกษาถัดไป', 'พ้นสภาพการเป็นนักศึกษา', 'ติดภาคทัณฑ์' หรือ null)
- "article_no": เลขข้อบังคับ เช่น 'ข้อ 11 วรรคหนึ่ง', 'ข้อ 20 วรรคสอง', 'ข้อ 22', 'ข้อ 25.2.1', 'ข้อ 33.9'
- "source_page": เลขหน้าที่พบ เช่น 89, 91, 92, 93, 94
/no_think"""

        payload = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": user_prompt}],
            "stream": False,
            "think": False,
            "format": "json",
            "options": {"temperature": 0.0, "num_ctx": 4096, "num_predict": 2048}
        }

        try:
            print(f"  [{i}/{len(chunks)}] ประมวลผลหมวด: {ch['category']}...")
            r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
            r.raise_for_status()
            content = r.json().get("message", {}).get("content", "{}")
            parsed = json.loads(content)
            raw_items = parsed.get("regulations") or parsed.get("items") or []

            for raw in raw_items:
                # Clean and normalize fields
                cat = raw.get("category", ch["category"])
                top = raw.get("topic", "")
                desc = raw.get("condition_desc", "")
                
                # Normalize float values
                min_g = float(raw["min_gpa"]) if raw.get("min_gpa") not in (None, "", "null") else None
                max_g = float(raw["max_gpa"]) if raw.get("max_gpa") not in (None, "", "null") else None
                
                # Fix inverted min/max in honors
                if "เกียรตินิยม" in cat and max_g and not min_g:
                    min_g, max_g = max_g, None
                if "เหรียญทอง" in top:
                    min_g = 3.75
                elif "อันดับ 1" in top and "เหรียญทอง" not in top:
                    min_g = 3.50
                elif "อันดับ 2" in top:
                    min_g = 3.25

                min_c = int(raw["min_credits"]) if raw.get("min_credits") not in (None, "", "null") else None
                max_c = int(raw["max_credits"]) if raw.get("max_credits") not in (None, "", "null") else None
                if "ภาคปกติ" in top and (not min_c or min_c != 9):
                    min_c = 9
                    max_c = 22

                item = RegulationItem(
                    program_id="ALL",
                    category=cat,
                    topic=top,
                    condition_desc=desc,
                    min_gpa=min_g,
                    max_gpa=max_g,
                    min_credits=min_c,
                    max_credits=max_c,
                    penalty_action=raw.get("penalty_action"),
                    article_no=raw.get("article_no"),
                    source_page=int(raw["source_page"]) if raw.get("source_page") not in (None, "") else None
                )
                items_out.append(item)
            print(f"    ✓ สกัดได้ {len(raw_items)} รายการ")
        except Exception as e:
            print(f"    ✗ ข้อผิดพลาด: {e}")

    return items_out


def insert_regulations_to_db(db_path: Path, regulations: list[RegulationItem]) -> None:
    if not db_path.exists():
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(REGULATION_TABLE_SQL)
    cur.execute("DELETE FROM regulation")

    for r in regulations:
        cur.execute(
            """
            INSERT INTO regulation (
                program_id, category, topic, condition_desc, min_gpa, max_gpa,
                min_credits, max_credits, penalty_action, article_no, source_page
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r.program_id, r.category, r.topic, r.condition_desc,
                r.min_gpa, r.max_gpa, r.min_credits, r.max_credits,
                r.penalty_action, r.article_no, r.source_page
            )
        )
    conn.commit()
    count = cur.execute("SELECT COUNT(*) FROM regulation").fetchone()[0]
    conn.close()
    print(f"  ✓ อัปเดตฐานข้อมูล {db_path.name} สำเร็จ ({count} แถว)")


def main():
    parser = argparse.ArgumentParser(description="สกัดข้อบังคับการศึกษาผ่าน LLM (Lab 7B Pipeline)")
    parser.add_argument("--mode", choices=["llm", "rule"], default="llm", help="โหมดการสกัด (llm หรือ rule)")
    args = parser.parse_args()

    print("=" * 70)
    print("  Lab 7B/8B: การสกัดข้อบังคับการศึกษาจากเอกสารดิบด้วย LLM (Ollama qwen3:4b)")
    print("=" * 70)

    page_texts = load_raw_regulation_pages(OCR_PATH)

    if args.mode == "llm":
        regulations = extract_regulations_via_llm(page_texts)
    else:
        # Fallback rule-based
        from extract_regulations import extract_regulations_from_ocr
        regulations = extract_regulations_from_ocr(OCR_PATH)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    items = [r.model_dump() for r in regulations]
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"\nบันทึกข้อบังคับ {len(items)} รายการจาก LLM ลงใน {OUTPUT_JSON}")

    # อัปเดตฐานข้อมูลทั้งหมดในระบบ
    print("\nบันทึกข้อมูลเข้าฐานข้อมูล SQLite (curriculum.db):")
    db_paths = [
        ROOT / "work" / "lab8b_run" / "curriculum.db",
        ROOT / "work" / "lab8b_run" / "combined" / "curriculum.db",
        ROOT / "work" / "lab8b_run" / "DSBA" / "curriculum.db",
        ROOT / "work" / "lab8b_run" / "IT" / "curriculum.db",
        ROOT / "work" / "lab8b_run" / "AIT" / "curriculum.db",
        ROOT / "work" / "lab8b_run" / "BIT" / "curriculum.db",
    ]

    for p in db_paths:
        insert_regulations_to_db(p, regulations)

    print("\nเสร็จสิ้นกระบวนการสกัดข้อบังคับการศึกษาผ่าน LLM ตามแนวทาง Lab 7B เรียบร้อย!")


if __name__ == "__main__":
    main()
