"""Run the Lab 7B -> Lab 8B multi-curriculum workflow on Windows, macOS, or Linux.

This script automates the complete pipeline:
  1. (Optional) Run Lab 7B extraction
  2. Generate SQLite schema and JSON Schema
  3. Import and transform Lab 7B outputs for 4 curricula (DSBA, BIT, IT, AIT)
  4. Load curricula and institutional regulations into SQLite
  5. Run 7-rule consistency verification
  6. (Optional) Run gold question evaluation benchmark
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LAB7 = ROOT / "src" / "ocr_system" / "lab7b_curriculum.py"
LAB8 = ROOT / "src" / "ocr_system" / "lab8b_curriculum_db.py"
LAB7_OUT = ROOT / "work" / "lab7b_run"
LAB8_OUT = ROOT / "work" / "lab8b_run"

PROGRAMS = {
    "DSBA": {
        "program_id": "DSBA",
        "name_th": "วิทยาการข้อมูลและการวิเคราะห์เชิงธุรกิจ (สหกิจศึกษา)",
        "name_en": "Data Science and Business Analytics (DSBA)",
        "degree": "วท.บ. (วิทยาการข้อมูลและการวิเคราะห์เชิงธุรกิจ)",
        "total_credits": 132,
        "years": 4,
        "input_candidates": [
            ROOT / "work" / "lab7b_run" / "DSBA" / "pred_text.json",
            ROOT / "lab7_final" / "output" / "DSBA" / "pred_text.json",
            ROOT / "work" / "lab7b_run" / "pred_vlm.json",
            ROOT / "work" / "lab7b_run" / "pred_markdown.json",
        ],
        "gold_qa": ROOT / "data" / "QA" / "gold_questions_DSBA.json",
    },
    "BIT": {
        "program_id": "BIT",
        "name_th": "เทคโนโลยีสารสนเทศทางธุรกิจ (สหกิจศึกษา)",
        "name_en": "Business Information Technology (BIT)",
        "degree": "วท.บ. (เทคโนโลยีสารสนเทศทางธุรกิจ)",
        "total_credits": 126,
        "years": 4,
        "input_candidates": [
            ROOT / "work" / "lab7b_run" / "BIT" / "pred_text.json",
            ROOT / "lab7_final" / "output" / "BIT" / "pred_text.json",
        ],
        "gold_qa": ROOT / "data" / "QA" / "gold_questions_combined.json",
    },
    "IT": {
        "program_id": "IT",
        "name_th": "เทคโนโลยีสารสนเทศ (สหกิจศึกษา)",
        "name_en": "Information Technology (IT)",
        "degree": "วท.บ. (เทคโนโลยีสารสนเทศ)",
        "total_credits": 129,
        "years": 4,
        "input_candidates": [
            ROOT / "work" / "lab7b_run" / "IT" / "pred_text.json",
            ROOT / "lab7_final" / "output" / "IT" / "pred_text.json",
        ],
        "gold_qa": ROOT / "data" / "QA" / "gold_questions_combined.json",
    },
    "AIT": {
        "program_id": "AIT",
        "name_th": "เทคโนโลยีปัญญาประดิษฐ์",
        "name_en": "Artificial Intelligence Technology (AIT)",
        "degree": "วท.บ. (เทคโนโลยีปัญญาประดิษฐ์)",
        "total_credits": 120,
        "years": 4,
        "input_candidates": [
            ROOT / "work" / "lab7b_run" / "AIT" / "pred_text.json",
            ROOT / "lab7_final" / "output" / "AIT" / "pred_text.json",
        ],
        "gold_qa": ROOT / "data" / "QA" / "gold_questions_combined.json",
    },
}

REGULATION_CANDIDATES = [
    ROOT / "work" / "lab7b_run" / "regulations" / "regulations.json",
    ROOT / "work" / "lab8b_run" / "regulations.json",
    ROOT / "work" / "lab7b_run" / "regulations.json",
]


def run(*args: object) -> None:
    """Run command with project root as working directory."""
    cmd = [sys.executable, *(str(x) for x in args)]
    print(f"\n>> {' '.join(str(x) for x in cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def find_first_existing(candidates: list[Path]) -> Path | None:
    """Return the first existing path from candidates."""
    for p in candidates:
        if p.exists():
            return p
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-End Automation Script for Lab 8B (Supports 4 Curricula)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--program",
        choices=["all", "DSBA", "BIT", "IT", "AIT"],
        default="all",
        help="หลักสูตรที่ต้องการประมวลผล ('all' สำหรับทุกหลักสูตร 4 สาขา)",
    )
    parser.add_argument(
        "--skip-lab7",
        action="store_true",
        help="ข้ามการรัน Lab 7B (ใช้ผลลัพธ์ JSON ที่มีอยู่แล้ว)",
    )
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="ข้ามขั้นตอนการประเมินผล Text-to-SQL (ประหยัดเวลา/ไม่ต้องรัน Ollama)",
    )
    parser.add_argument(
        "--model",
        default="qwen3:4b",
        help="Ollama model สำหรับขั้นตอนประเมินผล",
    )
    parser.add_argument(
        "--database",
        "-d",
        default="work/lab8b_run/curriculum.db",
        help="ที่อยู่ไฟล์ฐานข้อมูล SQLite ผลลัพธ์",
    )
    args = parser.parse_args()

    os.environ.update({
        "PYTHONUTF8": "1",
        "LAB7_CHUNK": "1",
        "LAB7B_NUM_CTX": "4096",
        "LAB7B_NUM_PREDICT": "2000",
        "LAB7B_OCR_NUM_CTX": "4096",
        "LAB7B_OCR_NUM_PREDICT": "1200",
    })

    LAB7_OUT.mkdir(parents=True, exist_ok=True)
    LAB8_OUT.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("  Lab 8B Automation Pipeline (ISD 2026)")
    print(f"  Target Program: {args.program}")
    print(f"  Target Database: {args.database}")
    print("=" * 72)

    # -------------------------------------------------------------------------
    # 1. รัน Lab 7B (ถ้าไม่ได้ระบุ --skip-lab7)
    # -------------------------------------------------------------------------
    if not args.skip_lab7:
        sample_input = ROOT / "data" / "input_C"
        sample_gt = ROOT / "data" / "ground_truth_C" / "DSBA_academic_plan_coop.json"
        if sample_input.exists() and sample_gt.exists():
            print("\n[Step 1/5] รัน Lab 7B VLM extraction...")
            run(LAB7, "-i", sample_input, "-g", sample_gt, "-p", "vlm", "-o", LAB7_OUT)
        else:
            print("\n[Step 1/5] ข้ามการรัน Lab 7B เนื่องจากใช้ผลการสกัดที่มีอยู่แล้วในระบบ")
    else:
        print("\n[Step 1/5] ข้ามการรัน Lab 7B ตามตัวเลือก --skip-lab7")

    # -------------------------------------------------------------------------
    # 2. เขียน Schema & DDL
    # -------------------------------------------------------------------------
    print("\n[Step 2/5] สร้าง SQLite DDL และ JSON Schema...")
    run(LAB8, "schema", "-o", LAB8_OUT / "schema")

    # -------------------------------------------------------------------------
    # 3. นำเข้าข้อมูลรายวิชา (import-lab7b) และโหลดลง SQLite (load)
    # -------------------------------------------------------------------------
    target_progs = list(PROGRAMS.keys()) if args.program == "all" else [args.program]
    db_path = Path(args.database)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n[Step 3/5] นำเข้าข้อมูลหลักสูตร: {', '.join(target_progs)}...")

    is_first = True
    for prog_key in target_progs:
        meta = PROGRAMS[prog_key]
        pred_file = find_first_existing(meta["input_candidates"])
        if not pred_file:
            print(f"  [!] ไม่พบไฟล์ผลลัพธ์ของ {prog_key} ข้ามการนำเข้า")
            continue

        prog_out_dir = LAB8_OUT / prog_key
        prog_out_dir.mkdir(parents=True, exist_ok=True)
        curriculum_json = prog_out_dir / "curriculum.json"

        # แปลงผลลัพธ์ Lab 7B เป็นโครงสร้าง Lab 8B
        run(
            LAB8,
            "import-lab7b",
            "-i",
            pred_file,
            "-o",
            curriculum_json,
            "--program-id",
            meta["program_id"],
            "--program-name",
            meta["name_th"],
            "--name-en",
            meta["name_en"],
            "--degree",
            meta["degree"],
            "--total-credits",
            meta["total_credits"],
            "--years",
            meta["years"],
        )

        # โหลดลงฐานข้อมูลหลัก
        load_args = [LAB8, "load", "-i", curriculum_json, "-d", db_path]
        if is_first:
            load_args.append("--replace")
            is_first = False
        run(*load_args)

    # โหลดกฎระเบียบข้อบังคับสถาบันฯ
    reg_file = find_first_existing(REGULATION_CANDIDATES)
    if reg_file:
        print(f"\n  [+] โหลดข้อบังคับสถาบันฯ จาก {reg_file}...")
        run(LAB8, "load-regulations", "-i", reg_file, "-d", db_path)
    else:
        print("  [!] ไม่พบไฟล์ regulations.json ข้ามการโหลดข้อบังคับ")

    # -------------------------------------------------------------------------
    # 4. ตรวจสอบความสอดคล้อง 7 ข้อ (verify)
    # -------------------------------------------------------------------------
    print("\n[Step 4/5] ตรวจสอบความสอดคล้องของฐานข้อมูล (Consistency Verification 7 กฎ)...")
    verify_out = LAB8_OUT / "verify.json"
    verify_cmd = [LAB8, "verify", "-d", db_path, "-o", verify_out]
    if args.program != "all":
        verify_cmd.extend(["--program-id", args.program])
    run(*verify_cmd)

    # -------------------------------------------------------------------------
    # 5. ประเมินผลชุดคำถามทอง (eval)
    # -------------------------------------------------------------------------
    if not args.skip_eval:
        print("\n[Step 5/5] ประเมินผล Text-to-SQL ด้วยชุดคำถามทอง...")
        if args.program == "all":
            gold_file = ROOT / "data" / "QA" / "gold_questions_combined.json"
        else:
            gold_file = PROGRAMS[args.program]["gold_qa"]

        if not gold_file.exists():
            # Fallback to local gold_questions.json if present
            local_gold = LAB8_OUT / "gold_questions.json"
            if local_gold.exists():
                gold_file = local_gold

        if gold_file and gold_file.exists():
            eval_out = LAB8_OUT / "eval_result.json"
            run(
                LAB8,
                "eval",
                "-d",
                db_path,
                "-q",
                gold_file,
                "-o",
                eval_out,
                "--model",
                args.model,
            )
        else:
            print(f"  [!] ไม่พบชุดคำถามทอง {gold_file} ข้ามการประเมินผล")
    else:
        print("\n[Step 5/5] ข้ามการประเมินผลตามตัวเลือก --skip-eval")

    print("\n" + "=" * 72)
    print(f"  ดำเนินการเสร็จสิ้นเรียบร้อย: {db_path}")
    print("=" * 72)


if __name__ == "__main__":
    main()
