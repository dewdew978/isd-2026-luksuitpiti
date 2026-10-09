"""
Lab 9 - Step 2: Schema & Consistency Evaluation 
วัดคุณภาพของผลลัพธ์ที่มีโครงสร้าง (Schema pass rate, Consistency rules)
"ถ้ำซ่อมแล้วยังไม่ผ่าน = ต้อง abstain อย่าปล่อยข้อมูลที่ไม่ผ่านลงฐานข้อมูล"
"""

import json
import sqlite3
import sys
from pathlib import Path

# ป้องกัน UnicodeEncodeError บน Windows CMD/PowerShell
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.ocr_system.lab8b_curriculum_db import verify_db


DATABASES = [
    {
        "id": "UNIFIED_ALL",
        "name": "ฐานข้อมูลรวม 4 หลักสูตร (Main DB)",
        "path": ROOT_DIR / "work/lab8b_run/curriculum.db",
    },
    {
        "id": "DSBA",
        "name": "ฐานข้อมูลเดี่ยว DSBA",
        "path": ROOT_DIR / "work/lab8b_run/DSBA/curriculum.db",
    },
    {
        "id": "BIT",
        "name": "ฐานข้อมูลเดี่ยว BIT",
        "path": ROOT_DIR / "work/lab8b_run/BIT/curriculum.db",
    },
    {
        "id": "IT",
        "name": "ฐานข้อมูลเดี่ยว IT",
        "path": ROOT_DIR / "work/lab8b_run/IT/curriculum.db",
    },
    {
        "id": "AIT",
        "name": "ฐานข้อมูลเดี่ยว AIT",
        "path": ROOT_DIR / "work/lab8b_run/AIT/curriculum.db",
    },
]


def run_schema_evaluation() -> dict:
    """ตรวจสอบความสอดคล้องและสถิติข้อมูลในฐานข้อมูล SQLite"""
    print("\n" + "=" * 76)
    print("  [Step 2] การตรวจสอบ Schema & ความสอดคล้อง (Consistency Verification)")
    print("=" * 76)

    all_results = {}

    for item in DATABASES:
        db_id = item["id"]
        db_path = item["path"]

        if not db_path.exists():
            print(f"  [{db_id}] ❌ ไม่พบไฟล์ฐานข้อมูล: {db_path.name}")
            continue

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # นับสถิติตารางสำคัญตามสถาปัตยกรรม Option 2
        counts = {}
        for tbl in ["program", "study_plan", "course", "plan_item", "elective_slot", "prerequisite", "regulation"]:
            try:
                counts[tbl] = cur.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            except sqlite3.OperationalError:
                counts[tbl] = 0

        # รันการตรวจความสอดคล้อง 7 ข้อ (CHK1 - CHK7)
        checks = verify_db(conn)
        n_pass = sum(1 for c in checks if c["ok"])
        n_total = len(checks)
        pass_rate = (n_pass / n_total) * 100 if n_total > 0 else 0

        all_results[db_id] = {
            "name": item["name"],
            "path": str(db_path.relative_to(ROOT_DIR)),
            "counts": counts,
            "checks": checks,
            "passed_checks": n_pass,
            "total_checks": n_total,
            "pass_rate": round(pass_rate, 2),
        }

        print(f"\n  📁 {item['name']} ({db_path.name}):")
        print(f"     สถิติข้อมูล: {counts.get('course', 0)} วิชา | {counts.get('plan_item', 0)} แผน | "
              f"{counts.get('elective_slot', 0)} วิชาเลือก | {counts.get('prerequisite', 0)} Prereq | "
              f"{counts.get('regulation', 0)} ข้อบังคับ")
        print(f"     ผลการตรวจความสอดคล้อง: ผ่าน {n_pass}/{n_total} ข้อ ({pass_rate:.1f}%)")

        for c in checks:
            mark = "✅" if c["ok"] else "❌"
            print(f"       {mark} [{c['id']}] {c['name']}")

        conn.close()

    print("\n" + "=" * 76)
    print("  💡 การตีความ:")
    print("     - Schema Pass Rate 100% = ข้อมูลถูกต้องตาม Pydantic / RDBMS Constraints")
    print("     - Consistency Checks ผ่านครบ = ป้องกันข้อมูลไม่สมบูรณ์หลุดเข้าสู่ฐานข้อมูลจริง\n")

    # บันทึกผลลัพธ์
    out_dir = ROOT_DIR / "lab9" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "step2_schema_verification.json"
    out_file.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")

    return all_results


if __name__ == "__main__":
    run_schema_evaluation()
