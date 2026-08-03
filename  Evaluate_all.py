"""
Evaluate_all.py
================
รัน dataset จาก Lab ที่ผ่านมาทั้งหมด แล้วประเมินผล pipeline 3 ระดับ:

  1. Field Level    - code recall + credits exact-match ของแต่ละแผน/หมวดวิชา
                       (ใช้ evaluate_courses() จาก src/ocr_system/evaluation.py ตรงๆ
                        ไม่เขียน metric ใหม่ซ้ำ)
  2. Page Level     - เทียบเลขหน้าที่ pipeline ค้นเจอ กับเลขหน้าจริงตาม ground truth
                       (ยังไม่มี module นี้ใน src/ocr_system เดิม จึงเพิ่มไว้ในไฟล์นี้)
  3. Category Level - สรุปผลรวมแยกตามหมวด: DSBA coop, DSBA no_coop,
                       หมวดศึกษาทั่วไป, ข้อบังคับ

รันจาก root ของ repo:
    python Evaluate_all.py

Input ที่ต้องมี:
  outputs/dsba_input_v2_ocr.json                 (ผล OCR จาก Lab 3, มีอยู่แล้ว)
  data/ground_truth/DSBA_academic_plan_coop.json
  data/ground_truth/DSBA_academic_plan_no_coop.json
  data/ground_truth/general_education_ground_truth.json
  data/ground_truth/rules_ground_truth.json
  data/ground_truth/Map_page_luksuitpiti.csv     (ground truth เลขหน้า — ถ้าไม่มีไฟล์นี้
                                                    จะข้าม Page Level ไปโดยอัตโนมัติ)

Output:
  outputs/eval_field_level.json
  outputs/eval_page_level.csv
  outputs/eval_category_summary.csv
  พิมพ์สรุปผลลง console
"""

import json
import re
import csv
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))  # ให้ import ได้แม้ยังไม่ได้ pip install -e .

from ocr_system.evaluation import evaluate_courses  # noqa: E402
from ocr_system.field_extraction import extract_courses  # noqa: E402

GT_DIR = ROOT / "data" / "ground_truth"
OUT_DIR = ROOT / "outputs"
OUT_DIR.mkdir(exist_ok=True)

OCR_JSON = OUT_DIR / "dsba_input_v2_ocr.json"


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def normalize(s):
    return re.sub(r"\s+", "", str(s)) if s is not None else ""


def printed_page_number(text: str) -> str | None:
    """บรรทัดแรกของแต่ละหน้า OCR มักเป็นเลขหน้าจริงที่พิมพ์อยู่ในเอกสาร"""
    for line in text.strip().split("\n"):
        line = line.strip()
        if line:
            m = re.match(r"^\d{1,4}$", line)
            return m.group() if m else None
    return None


def load_ocr(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    pages = {p["page"]: p["text"] for p in doc["pages"]}
    printed = {pg: printed_page_number(t) for pg, t in pages.items()}
    return doc, pages, printed


def find_printed_pages(needle: str, ocr_pages: dict, ocr_printed: dict) -> set[str]:
    """คืนเลขหน้าจริงที่พิมพ์ (ไม่ใช่เลขหน้า OCR 1..N) ที่พบ needle อยู่ในเนื้อหา"""
    found = set()
    for pg, txt in ocr_pages.items():
        if needle in txt:
            p = ocr_printed.get(pg)
            if p:
                found.add(p)
    return found


# ------------------------------------------------------------------
# load OCR (Lab 3 output, already produced)
# ------------------------------------------------------------------

ocr_doc, ocr_pages, ocr_printed = load_ocr(OCR_JSON)
predicted_courses = extract_courses(ocr_doc["text"])
print(f"[extract_courses] พบรายวิชาทั้งหมด {len(predicted_courses)} รายการจาก OCR text")


# ==========================================================
# 1) FIELD LEVEL — รายวิชา (ใช้ evaluate_courses ของ Lab เดิม)
# ==========================================================

course_gt_files = {
    "DSBA coop": GT_DIR / "DSBA_academic_plan_coop.json",
    "DSBA no_coop": GT_DIR / "DSBA_academic_plan_no_coop.json",
    "หมวดศึกษาทั่วไป": GT_DIR / "general_education_ground_truth.json",
}

field_level_courses = {}
for name, path in course_gt_files.items():
    if not path.exists():
        print(f"[warn] ไม่พบ {path} - ข้าม field level ของ {name}")
        continue
    with open(path, "r", encoding="utf-8") as f:
        gt = json.load(f)
    field_level_courses[name] = evaluate_courses(gt["courses"], predicted_courses, file_name=name)

# ----- ข้อบังคับ: field level = ค่าตัวเลข (GPA/หน่วยกิต) เทียบกับข้อความในหน้าที่ค้นเจอ -----
rules_path = GT_DIR / "rules_ground_truth.json"
field_level_rules = []
if rules_path.exists():
    with open(rules_path, "r", encoding="utf-8") as f:
        rules_gt = json.load(f)["programs"]
    for crit in rules_gt.get("DSBA", []):
        category = crit["category"]
        pred_pages = find_printed_pages(category, ocr_pages, ocr_printed)
        combined_txt = normalize("".join(
            txt for pg, txt in ocr_pages.items() if ocr_printed.get(pg) in pred_pages
        ))
        for val in crit.get("values", []):
            if val["value"] is None:
                continue
            val_norm = normalize(str(val["value"]).lstrip("<>=").strip())
            match = (val_norm in combined_txt) if val_norm else None
            field_level_rules.append({
                "category": category,
                "field": val["label"],
                "ground_truth": val["value"],
                "match": match,
            })
else:
    print(f"[warn] ไม่พบ {rules_path} - ข้าม field level ของข้อบังคับ")


# ==========================================================
# 2) PAGE LEVEL — เทียบเลขหน้าที่ pipeline เจอ กับหน้าจริง
# ==========================================================

page_level_rows = []
map_page_path = GT_DIR / "Map_page_luksuitpiti.csv"
if map_page_path.exists():
    with open(map_page_path, "r", encoding="utf-8-sig", newline="") as f:
        map_rows = list(csv.DictReader(f))

    for row in map_rows:
        category = row["source_gt"]
        code = row["code"].strip()
        name_th_gt = row["name_th"].strip()
        gt_pages = set(p.strip() for p in row["pages"].split(";") if p.strip())

        is_course = bool(re.fullmatch(r"\d{8}", code))
        needle = code if is_course else name_th_gt  # ข้อบังคับค้นด้วยชื่อหมวด (เลขไทย OCR ไม่น่าเชื่อถือ)

        pred_pages = find_printed_pages(needle, ocr_pages, ocr_printed)

        tp = len(pred_pages & gt_pages)
        precision = tp / len(pred_pages) if pred_pages else 0.0
        recall = tp / len(gt_pages) if gt_pages else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        page_level_rows.append({
            "category": category,
            "code": code,
            "name_th": name_th_gt,
            "gt_pages": ";".join(sorted(gt_pages)),
            "predicted_pages": ";".join(sorted(pred_pages)),
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "exact_match": pred_pages == gt_pages,
        })
else:
    print(f"[warn] ไม่พบ {map_page_path} - ข้าม Page Level evaluation ทั้งหมด "
          f"(ต้องมีไฟล์ ground truth เลขหน้าก่อนถึงจะประเมินระดับนี้ได้)")


# ==========================================================
# 3) CATEGORY LEVEL — สรุปรวมแยกตามหมวด
# ==========================================================

category_summary = []
if page_level_rows:
    cats = sorted(set(r["category"] for r in page_level_rows))
    for cat in cats:
        rows = [r for r in page_level_rows if r["category"] == cat]
        n = len(rows)
        avg_p = sum(r["precision"] for r in rows) / n
        avg_r = sum(r["recall"] for r in rows) / n
        avg_f1 = sum(r["f1"] for r in rows) / n
        exact_rate = sum(1 for r in rows if r["exact_match"]) / n

        # field accuracy ต่อ category: ถ้าตรงกับ course_gt_files ใช้ code_recall,
        # ถ้าเป็นข้อบังคับใช้สัดส่วน match ของ field_level_rules
        field_acc = None
        matched_course_key = next((k for k in field_level_courses if cat.startswith(k)), None)
        if matched_course_key:
            field_acc = field_level_courses[matched_course_key]["code_recall"]
        elif cat.startswith("ข้อบังคับ") and field_level_rules:
            checked = [r for r in field_level_rules if r["match"] is not None]
            field_acc = sum(1 for r in checked if r["match"]) / len(checked) if checked else None

        category_summary.append({
            "category": cat,
            "n_items": n,
            "page_avg_precision": round(avg_p, 3),
            "page_avg_recall": round(avg_r, 3),
            "page_avg_f1": round(avg_f1, 3),
            "page_exact_match_rate": round(exact_rate, 3),
            "field_accuracy": round(field_acc, 3) if field_acc is not None else "N/A",
        })


# ==========================================================
# save + print
# ==========================================================

with open(OUT_DIR / "eval_field_level.json", "w", encoding="utf-8") as f:
    json.dump({
        "courses": field_level_courses,
        "rules": field_level_rules,
    }, f, ensure_ascii=False, indent=2)

if page_level_rows:
    with open(OUT_DIR / "eval_page_level.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(page_level_rows[0].keys()))
        w.writeheader()
        w.writerows(page_level_rows)

if category_summary:
    with open(OUT_DIR / "eval_category_summary.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(category_summary[0].keys()))
        w.writeheader()
        w.writerows(category_summary)

print()
print("=" * 70)
print("FIELD LEVEL (evaluate_courses จาก src/ocr_system/evaluation.py)")
print("=" * 70)
for name, result in field_level_courses.items():
    print(f"{name:20s} code_recall={result['code_recall']:.3f} "
          f"({result['codes_found']}/{result['gt_fixed_course_count']})  "
          f"credits_match={result['credits_exact_match']}/{result['credits_checked']}")
if field_level_rules:
    checked = [r for r in field_level_rules if r["match"] is not None]
    acc = sum(1 for r in checked if r["match"]) / len(checked) if checked else 0
    print(f"{'ข้อบังคับ (ค่าตัวเลข)':20s} accuracy={acc:.3f} (n={len(checked)})")

if page_level_rows:
    print()
    print("=" * 70)
    print("PAGE LEVEL")
    print("=" * 70)
    n = len(page_level_rows)
    print(f"n={n}  "
          f"precision={sum(r['precision'] for r in page_level_rows)/n:.3f}  "
          f"recall={sum(r['recall'] for r in page_level_rows)/n:.3f}  "
          f"f1={sum(r['f1'] for r in page_level_rows)/n:.3f}  "
          f"exact_match={sum(1 for r in page_level_rows if r['exact_match'])/n:.3f}")

if category_summary:
    print()
    print("=" * 70)
    print("CATEGORY LEVEL SUMMARY")
    print("=" * 70)
    header = f"{'Category':40s} {'n':>4s} {'F1':>6s} {'Exact':>6s} {'FieldAcc':>9s}"
    print(header)
    print("-" * len(header))
    for s in category_summary:
        print(f"{s['category']:40s} {s['n_items']:>4d} {s['page_avg_f1']:>6.3f} "
              f"{s['page_exact_match_rate']:>6.3f} {str(s['field_accuracy']):>9s}")

print()
print("บันทึกผลลัพธ์แล้วที่ outputs/eval_field_level.json, eval_page_level.csv, eval_category_summary.csv")