"""
Lab 9 - Step 1: Extraction Evaluation (การสกัดข้อมูลและ OCR)
- Field-level Precision / Recall
"""

import json
import sys
from pathlib import Path

# ป้องกัน UnicodeEncodeError บน Windows CMD/PowerShell
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ให้สามารถเรียกโมดูลจากโฟลเดอร์รากได้
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.ocr_system.lab7b_curriculum import evaluate


PROGRAMS = [
    {
        "id": "DSBA",
        "name": "Data Science and Business Analytics",
        "pred": ROOT_DIR / "work/lab7b_run/DSBA/pred_text.json",
        "gt": ROOT_DIR / "data/ground_truth/DSBA/DSBA_academic_plan_coop.json",
    },
    {
        "id": "IT",
        "name": "Information Technology",
        "pred": ROOT_DIR / "work/lab7b_run/IT/pred_text.json",
        "gt": ROOT_DIR / "data/ground_truth/IT/IT_academic_plan_coop.json",
    },
    {
        "id": "BIT",
        "name": "Business Information Technology",
        "pred": ROOT_DIR / "work/lab7b_run/BIT/pred_text.json",
        "gt": ROOT_DIR / "data/ground_truth/BIT/BIT_academic_plan_coop.json",
    },
    {
        "id": "AIT",
        "name": "Artificial Intelligence Technology",
        "pred": ROOT_DIR / "work/lab7b_run/AIT/pred_text.json",
        "gt": ROOT_DIR / "data/ground_truth/AIT/AIT_academic_plan.json",
    },
]


def run_extraction_evaluation() -> dict:
    """รันการประเมินผลการสกัดเทียบ Ground Truth ครบทั้ง 4 หลักสูตร"""
    results = {}
    print("\n" + "=" * 76)
    print("  [Step 1] การประเมินผลการสกัดข้อมูล (Extraction & OCR Evaluation)")
    print("=" * 76)
    print(f"  {'หลักสูตร':<8} | {'GT':<5} | {'สกัดได้':<8} | {'จับคู่':<6} | {'ตก(FN)':<6} | {'เกิน(FP)':<8} | {'Precision':<9} | {'Recall':<8} | {'F1-Score':<8}")
    print("  " + "-" * 74)

    total_gt = 0
    total_pred = 0
    total_matched = 0
    total_missed = 0
    total_spurious = 0

    for prog in PROGRAMS:
        p_id = prog["id"]
        pred_path = prog["pred"]
        gt_path = prog["gt"]

        if not pred_path.exists() or not gt_path.exists():
            print(f"  {p_id:<8} | ❌ ไม่พบไฟล์ผลการสกัดหรือ Ground Truth")
            continue

        pred = json.loads(pred_path.read_text(encoding="utf-8"))
        gt = json.loads(gt_path.read_text(encoding="utf-8"))

        stats, align = evaluate(pred, gt)
        results[p_id] = {
            "name": prog["name"],
            "gt_total": align["gt_total"],
            "pred_total": align["pred_total"],
            "matched": align["matched"],
            "missed": align["missed"],
            "spurious": align["spurious"],
            "precision": round(align["precision"], 4),
            "recall": round(align["recall"], 4),
            "f1": round(align["f1"], 4),
            "missed_codes": align.get("missed_codes", []),
            "spurious_codes": align.get("spurious_codes", []),
        }

        total_gt += align["gt_total"]
        total_pred += align["pred_total"]
        total_matched += align["matched"]
        total_missed += align["missed"]
        total_spurious += align["spurious"]

        print(
            f"  {p_id:<8} | {align['gt_total']:<5} | {align['pred_total']:<8} | {align['matched']:<6} | "
            f"{align['missed']:<6} | {align['spurious']:<8} | {align['precision']*100:>7.1f}% | "
            f"{align['recall']*100:>6.1f}% | {align['f1']*100:>7.1f}%"
        )

    # คำนวณ Macro Average
    n = len(results)
    if n > 0:
        macro_p = sum(r["precision"] for r in results.values()) / n
        macro_r = sum(r["recall"] for r in results.values()) / n
        macro_f1 = sum(r["f1"] for r in results.values()) / n
        print("  " + "-" * 74)
        print(
            f"  {'เฉลี่ยรวม':<8} | {total_gt:<5} | {total_pred:<8} | {total_matched:<6} | "
            f"{total_missed:<6} | {total_spurious:<8} | {macro_p*100:>7.1f}% | "
            f"{macro_r*100:>6.1f}% | {macro_f1*100:>7.1f}%"
        )
        print("=" * 76)
        print("  💡 การตีความตาม Chapter 9:")
        print("     - Recall สูง = สกัดวิชาได้ครบ ไม่ตกหล่นไปจากฐานข้อมูล")
        print("     - Precision สูง = ไม่สร้าง 'วิชาผี' (Ghost courses) แปลกปลอมเข้าสู่ระบบ\n")

    # บันทึกผลลัพธ์ลง reports/
    out_dir = ROOT_DIR / "lab9" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "step1_extraction_metrics.json"
    out_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    return results


if __name__ == "__main__":
    run_extraction_evaluation()
