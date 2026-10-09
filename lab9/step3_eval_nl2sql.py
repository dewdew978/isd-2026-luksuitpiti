"""
Lab 9 - Step 3: NL to SQL & Retrieval Evaluation (การค้นคืนและการแปลงภาษาธรรมชาติเป็น SQL)

"""

import argparse
import json
import sqlite3
import sys
import time
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


def analyze_eval_data(eval_data: list) -> dict:
    """วิเคราะห์ผลการรัน NL to SQL และคำนวณ Metrics เชิงลึก"""
    total = len(eval_data)
    if total == 0:
        return {}

    n_correct = sum(1 for q in eval_data if q.get("correct"))
    n_valid_sql = sum(1 for q in eval_data if not q.get("error"))

    # วิเคราะห์สาเหตุที่ผิดพลาด (Error Diagnosis)
    error_types = {"syntax_error": 0, "empty_rows": 0, "wrong_value": 0, "other": 0}
    wrong_cases = []

    for q in eval_data:
        if not q.get("correct"):
            err = q.get("error")
            why = q.get("why", "")
            if err:
                error_types["syntax_error"] += 1
            elif "ได้ 0 แถว" in why or "ไม่พบ" in why:
                error_types["empty_rows"] += 1
            elif "ไม่ตรง" in why or "ไม่พบค่า" in why:
                error_types["wrong_value"] += 1
            else:
                error_types["other"] += 1

            wrong_cases.append({
                "question": q.get("question"),
                "expect": q.get("expect"),
                "sql": q.get("sql"),
                "why": q.get("why"),
            })

    return {
        "total_questions": total,
        "correct_answers": n_correct,
        "execution_accuracy": round((n_correct / total) * 100, 2),
        "valid_sql_count": n_valid_sql,
        "valid_sql_rate": round((n_valid_sql / total) * 100, 2),
        "error_distribution": error_types,
        "wrong_cases_sample": wrong_cases[:5],
    }


def run_nl2sql_evaluation(live: bool = True, limit: int | None = None, model: str = "qwen3:4b") -> dict:
    """รันการประเมินผล Text-to-SQL จากการรันสดผ่าน Ollama หรือผลลัพธ์ที่บันทึกไว้"""
    print("\n" + "=" * 76)
    print("  [Step 3] การประเมินผล Text-to-SQL (NL2SQL Benchmark - 180 Gold Questions)")
    print("=" * 76)

    main_eval_file = ROOT_DIR / "work/lab8b_run/eval_result.json"

    if live:
        from src.ocr_system.lab8b_curriculum_db import ask, open_db, score_one
        db_path = ROOT_DIR / "work/lab8b_run/curriculum.db"
        q_path = ROOT_DIR / "work/lab8b_run/gold_questions.json"
        conn = open_db(str(db_path), readonly=True)
        questions = json.loads(q_path.read_text(encoding="utf-8"))
        target_questions = questions[:limit] if limit else questions

        print(f"  ⚡ โหมด Live Evaluation: รันคำถามสดผ่าน Ollama ({model}) จำนวน {len(target_questions)} ข้อ...")
        print(f"  {'ข้อ':<8} | {'ผล':<4} | {'เวลา':<6} | {'คำถาม':<28} | {'SQL Query'}")
        print("  " + "-" * 74)

        eval_data = []
        for i, q in enumerate(target_questions, 1):
            t0 = time.time()
            got = ask(conn, q["question"], verbose=False)
            ok, why = score_one(q["expect"], got)
            sec = round(time.time() - t0, 2)
            eval_data.append({
                **q,
                "sql": got["sql"],
                "n_rows": len(got["rows"]),
                "error": got["error"],
                "answer": got["answer"],
                "correct": ok,
                "why": why,
                "seconds": sec,
            })
            status_icon = "✅" if ok else "❌"
            sql_preview = (got["sql"] or "None").replace("\n", " ").strip()
            if len(sql_preview) > 36:
                sql_preview = sql_preview[:33] + "..."
            q_preview = q["question"]
            if len(q_preview) > 26:
                q_preview = q_preview[:24] + ".."
            print(f"  [{i:>3}/{len(target_questions)}] | {status_icon:<2} | {sec:4.1f}s | {q_preview:<28} | {sql_preview}")

        conn.close()

        # บันทึกผลลัพธ์
        reports_dir = ROOT_DIR / "lab9" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        live_file = reports_dir / "live_eval_result.json"
        live_file.write_text(json.dumps(eval_data, ensure_ascii=False, indent=2), encoding="utf-8")
        if not limit or limit >= len(questions):
            main_eval_file.write_text(json.dumps(eval_data, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        if not main_eval_file.exists():
            print("  ❌ ไม่พบไฟล์ work/lab8b_run/eval_result.json")
            return {}
        eval_data = json.loads(main_eval_file.read_text(encoding="utf-8"))

    # วิเคราะห์ฐานข้อมูลกลาง (Main DB)
    summary_main = analyze_eval_data(eval_data)

    print(f"\n  📊 สรุปผลบนฐานข้อมูลรวม (Unified Main Database - {len(eval_data)} ข้อ):")
    print(f"     • Valid SQL Rate:          {summary_main['valid_sql_rate']:.1f}% ({summary_main['valid_sql_count']}/{summary_main['total_questions']})")
    print(f"     • Execution Accuracy (SQL): {summary_main['execution_accuracy']:.1f}% ({summary_main['correct_answers']}/{summary_main['total_questions']})")

    # วิเคราะห์เปรียบเทียบฐานข้อมูลเดี่ยว 4 สาขา (Isolated DBs)
    program_results = {}
    print(f"\n  📊 ผลการประเมินแยกตามสาขาวิชา (Isolated Databases):")
    print(f"  {'สาขาวิชา':<8} | {'จำนวนข้อ':<8} | {'Valid SQL':<11} | {'Execution Accuracy':<20}")
    print("  " + "-" * 56)

    for p_id in ["BIT", "IT", "DSBA", "AIT"]:
        p_eval_file = ROOT_DIR / f"work/lab8b_run/{p_id}/eval_result.json"
        if p_eval_file.exists():
            p_data = json.loads(p_eval_file.read_text(encoding="utf-8"))
            p_sum = analyze_eval_data(p_data)
            program_results[p_id] = p_sum
            print(f"  {p_id:<8} | {p_sum['total_questions']:<8} | {p_sum['valid_sql_rate']:>9.1f}% | {p_sum['execution_accuracy']:>18.1f}%")

    print("=" * 76)
    print("  💡 การตีความ:")
    print("     - Valid SQL Rate 100% = ไวยากรณ์ถูกต้อง ไม่พังตอนรัน")
    print("     - Execution Accuracy สูง = โมเดลแปลงเจตนาเป็น WHERE, JOIN และ GROUP BY ได้ตรงจริง\n")

    # บันทึกผลลัพธ์
    out_dir = ROOT_DIR / "lab9" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "step3_nl2sql_benchmark.json"
    full_report = {
        "main_database": summary_main,
        "programs": program_results,
    }
    out_file.write_text(json.dumps(full_report, ensure_ascii=False, indent=2), encoding="utf-8")

    return full_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lab 9 Step 3: NL2SQL Evaluation")
    parser.add_argument("--cached", action="store_true", help="ใช้ผลลัพธ์ที่บันทึกไว้แทนการรันสด")
    parser.add_argument("--limit", type=int, default=None, help="จำกัดจำนวนข้อที่จะทดสอบสด (เช่น --limit 10)")
    parser.add_argument("--model", default="qwen3:4b", help="โมเดล Ollama")
    args = parser.parse_args()

    is_live = not args.cached
    run_nl2sql_evaluation(live=is_live, limit=args.limit, model=args.model)
