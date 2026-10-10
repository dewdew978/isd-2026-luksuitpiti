"""
Lab 6: Evaluation Pipeline (Field Level, Page Level, Category Level)
=====================================================================
เชื่อมโยงและรับช่วงต่อจากโมดูลของ Lab 4:
  - src.ocr_system.field_extraction (extract_courses)
  - src.ocr_system.evaluation (evaluate_courses)

รองรับครบทั้ง 4 หลักสูตร: AIT / IT / DSBA / BIT
บันทึกผลการประเมินลงใน:
  - lab6/outputs/eval_field_level.json
  - lab6/outputs/eval_page_level.csv
  - lab6/outputs/eval_category_summary.csv
=====================================================================
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# เพิ่ม Root ของโปรเจกต์เข้า sys.path เพื่อให้ import จาก src ได้อย่างถูกต้อง
LAB6_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = LAB6_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# นำเข้าโมดูลจาก Lab 4
from src.ocr_system.field_extraction import extract_courses
from src.ocr_system.evaluation import evaluate_courses

# เส้นทางไฟล์และโฟลเดอร์
DATA_DIR = PROJECT_ROOT / "data" / "ground_truth"
OCR_INPUT_DIR = PROJECT_ROOT / "outputs"
LAB6_OUT_DIR = LAB6_DIR / "outputs"
LAB6_OUT_DIR.mkdir(parents=True, exist_ok=True)

# รองรับครบทั้ง 4 หลักสูตร
OCR_FILES = {
    "AIT": OCR_INPUT_DIR / "fulldoc_AIT_ocr.json",
    "IT": OCR_INPUT_DIR / "fulldoc_it_ocr.json",
    "DSBA": OCR_INPUT_DIR / "fulldoc_dsba_ocr.json",
    "BIT": OCR_INPUT_DIR / "fulldoc_BIT_ocr.json",
}

PAGE_LEVEL_PROGRAMS = ["AIT", "IT", "DSBA", "BIT"]

# ------------------------------------------------------------------
# ฟังก์ชันช่วย (Preprocessing & Page Extraction Helpers)
# ------------------------------------------------------------------

def normalize(s: str | None) -> str:
    return re.sub(r"\s+", "", str(s)) if s is not None else ""


def normalize_program(p: str) -> str:
    return (p or "").strip().upper()


def thai_am_fix(s: str | None) -> str | None:
    """Normalize decomposed Thai SARA AM (นิคหิต+สระอา) ให้เป็น precomposed SARA AM (สระอำ)"""
    if s is None:
        return None
    return s.replace("\u0e4d\u0e32", "\u0e33")


THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def thai_digits_fix(s: str | None) -> str | None:
    """แปลงตัวเลขไทยเป็นเลขอารบิกเพื่อให้เทียบกับ Ground Truth ได้อย่างถูกต้อง"""
    if s is None:
        return None
    return s.translate(THAI_DIGITS)


def printed_page_number(text: str) -> str | None:
    """ดึงเลขหน้าที่พิมพ์จริงจากบรรทัดแรกของหน้า OCR"""
    for line in text.strip().split("\n"):
        line = line.strip()
        if line:
            m = re.match(r"^(\d{1,4})\b", line)
            return m.group(1) if m else None
    return None


def load_ocr(path: Path) -> tuple[str, dict[int, str], dict[int, str | None]]:
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    full_text = thai_digits_fix(thai_am_fix(doc["text"])) or ""
    pages = {
        p["page"]: thai_digits_fix(thai_am_fix(p["text"])) or ""
        for p in doc["pages"]
    }
    printed = {pg: printed_page_number(t) for pg, t in pages.items()}
    return full_text, pages, printed


def find_printed_pages(needle: str, ocr_pages: dict[int, str], ocr_printed: dict[int, str | None]) -> set[str]:
    """ค้นหาเลขหน้าที่พิมพ์จริงที่พบคำค้นหา (needle)"""
    found = set()
    for pg, txt in ocr_pages.items():
        if needle in txt:
            p = ocr_printed.get(pg)
            if p:
                found.add(p)
    return found


def resolve_gt_pages(pages_str: str, ocr_printed: dict[int, str | None]) -> set[str]:
    """แปลงเลขหน้าจาก Ground Truth (รวมกรณี token เช่น 'ocr328' -> เลขหน้าที่พิมพ์จริง)"""
    result = set()
    for tok in pages_str.split(";"):
        tok = tok.strip()
        if not tok:
            continue
        m = re.fullmatch(r"ocr(\d+)", tok, flags=re.IGNORECASE)
        if m:
            ocr_pg_key = int(m.group(1))
            printed = ocr_printed.get(ocr_pg_key)
            if printed:
                result.add(printed)
        else:
            result.add(tok)
    return result


STRIP_PREFIXES = ["เกณฑ์การ", "เกณฑ์"]


def find_category_pages(category: str, ocr_pages: dict[int, str], ocr_printed: dict[int, str | None]) -> set[str]:
    cat = thai_am_fix(category) or ""
    candidates = [cat]
    for pre in STRIP_PREFIXES:
        if cat.startswith(pre):
            rest = cat[len(pre):]
            if rest and rest not in candidates:
                candidates.append(rest)
    found = set()
    for needle in candidates:
        found |= find_printed_pages(needle, ocr_pages, ocr_printed)
    return found


def page_category_alias(cat_name: str, prog: str) -> str:
    if cat_name.endswith("หมวดศึกษาทั่วไป"):
        return "หมวดศึกษาทั่วไป"
    return cat_name


def main():
    print("=" * 70)
    print("LAB 6: EVALUATION PIPELINE (AIT / IT / DSBA / BIT)")
    print("Continuing from Lab 4 Modules")
    print("=" * 70)

    # ------------------------------------------------------------------
    # ขั้นที่ 1: โหลดเอกสาร OCR ดิบ และสกัดข้อมูลรายวิชาผ่าน Lab 4 extract_courses()
    # ------------------------------------------------------------------
    ocr_by_program = {}
    for prog, path in OCR_FILES.items():
        if not path.exists():
            print(f"[warn] ไม่พบ {path} - ข้าม {prog}")
            continue
        full_text, pages, printed = load_ocr(path)
        # เรียกใช้ฟังก์ชัน extract_courses() จาก Lab 4 โดยตรง
        predicted_courses = extract_courses(full_text)
        ocr_by_program[prog] = {
            "full_text": full_text,
            "pages": pages,
            "printed": printed,
            "predicted_courses": predicted_courses,
        }
        print(f"[Lab 4 extract_courses] {prog:4s}: สกัดได้ {len(predicted_courses):3d} รายวิชา จากข้อความ OCR เต็มเล่ม")

    # ------------------------------------------------------------------
    # ขั้นที่ 2: FIELD LEVEL EVALUATION
    # ------------------------------------------------------------------
    COURSE_GT_FILES = {
        "AIT": {
            "AIT": DATA_DIR / "AIT" / "AIT_academic_plan.json",
        },
        "IT": {
            "IT coop": DATA_DIR / "IT" / "IT_academic_plan_coop.json",
            "IT no_coop": DATA_DIR / "IT" / "IT_academic_plan_no_coop.json",
        },
        "DSBA": {
            "DSBA coop": DATA_DIR / "DSBA" / "DSBA_academic_plan_coop.json",
            "DSBA no_coop": DATA_DIR / "DSBA" / "DSBA_academic_plan_no_coop.json",
        },
        "BIT": {
            "BIT coop": DATA_DIR / "BIT" / "BIT_academic_plan_coop.json",
            "BIT no_coop": DATA_DIR / "BIT" / "BIT_academic_plan_no_coop.json",
        },
    }
    GENERAL_ED_GT = DATA_DIR / "general_education_ground_truth.json"

    field_level_courses = defaultdict(dict)
    for prog, plans in COURSE_GT_FILES.items():
        if prog not in ocr_by_program:
            continue
        predicted_courses = ocr_by_program[prog]["predicted_courses"]
        for name, path in plans.items():
            if not path.exists():
                print(f"[warn] ไม่พบ {path} - ข้าม field level ของ {name}")
                continue
            with open(path, "r", encoding="utf-8") as f:
                gt = json.load(f)
            # เรียกใช้ฟังก์ชัน evaluate_courses() จาก Lab 4 โดยตรง
            field_level_courses[prog][name] = evaluate_courses(
                gt["courses"], predicted_courses, file_name=name
            )

        if GENERAL_ED_GT.exists():
            with open(GENERAL_ED_GT, "r", encoding="utf-8") as f:
                gened_gt = json.load(f)
            # หมายเหตุ: หลักสูตร BIT ใช้รหัสหมวดศึกษาทั่วไป 96xxxxxx ซึ่งเทียบเท่า 90xxxxxx ใน GT
            eval_courses_for_gened = predicted_courses
            if prog == "BIT":
                eval_courses_for_gened = [
                    {**c, "code": ("90" + c["code"][2:]) if c["code"].startswith("96") else c["code"]}
                    for c in predicted_courses
                ]
            field_level_courses[prog][f"{prog} - หมวดศึกษาทั่วไป"] = evaluate_courses(
                gened_gt["courses"], eval_courses_for_gened, file_name=f"{prog} - หมวดศึกษาทั่วไป"
            )

    # ประเมินค่าตัวเลขในข้อบังคับ (rules)
    rules_path = DATA_DIR / "rules_ground_truth.json"
    field_level_rules = defaultdict(list)
    if rules_path.exists():
        with open(rules_path, "r", encoding="utf-8") as f:
            rules_gt = json.load(f)["programs"]

        for prog in ocr_by_program:
            ocr_pages = ocr_by_program[prog]["pages"]
            ocr_printed = ocr_by_program[prog]["printed"]
            for crit in rules_gt.get(prog, []):
                category = crit["category"]
                pred_pages = find_category_pages(category, ocr_pages, ocr_printed)
                combined_txt = normalize("".join(
                    txt for pg, txt in ocr_pages.items() if ocr_printed.get(pg) in pred_pages
                ))
                for val in crit.get("values", []):
                    if val["value"] is None:
                        continue
                    val_norm = normalize(thai_am_fix(str(val["value"])).lstrip("<>=").strip())
                    match = (val_norm in combined_txt) if val_norm else None
                    field_level_rules[prog].append({
                        "category": category,
                        "field": val["label"],
                        "ground_truth": val["value"],
                        "match": match,
                    })
    else:
        print(f"[warn] ไม่พบ {rules_path} - ข้าม field level ของข้อบังคับ")

    # ------------------------------------------------------------------
    # ขั้นที่ 3: PAGE LEVEL EVALUATION (Map_page_all.csv)
    # ------------------------------------------------------------------
    page_level_rows = []
    map_page_path = DATA_DIR / "Map_page_all.csv"

    if not map_page_path.exists():
        print(f"[warn] ไม่พบ {map_page_path} - ข้าม Page Level evaluation")
    else:
        with open(map_page_path, "r", encoding="utf-8-sig", newline="") as f:
            all_map_rows = list(csv.DictReader(f))

        for row in all_map_rows:
            row["program"] = normalize_program(row["program"])

        for prog in PAGE_LEVEL_PROGRAMS:
            if prog not in ocr_by_program:
                continue

            ocr_pages = ocr_by_program[prog]["pages"]
            ocr_printed = ocr_by_program[prog]["printed"]

            map_rows = [r for r in all_map_rows if r["program"] == prog]
            if not map_rows:
                # กรณี BIT ที่ยังไม่มีแถวใน Map_page_all.csv
                continue

            for row in map_rows:
                category = row["source_gt"]
                code = row["code"].strip()
                name_th_gt = row["name_th"].strip().split("\n")[0]

                if not row["pages"].strip():
                    continue

                gt_pages = resolve_gt_pages(row["pages"], ocr_printed)
                if not gt_pages:
                    continue

                is_course = bool(re.fullmatch(r"\d{8}", code))
                needle = code if is_course else name_th_gt
                needle = thai_am_fix(needle) or ""

                pred_pages = find_printed_pages(needle, ocr_pages, ocr_printed)

                tp = len(pred_pages & gt_pages)
                precision = tp / len(pred_pages) if pred_pages else 0.0
                recall = tp / len(gt_pages) if gt_pages else 0.0
                f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

                page_level_rows.append({
                    "program": prog,
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

    # ------------------------------------------------------------------
    # ขั้นที่ 4: CATEGORY LEVEL SUMMARY
    # ------------------------------------------------------------------
    category_summary = []

    for prog in ["AIT", "IT", "DSBA", "BIT"]:
        if prog not in ocr_by_program:
            continue

        for cat_name, result in field_level_courses.get(prog, {}).items():
            alias = page_category_alias(cat_name, prog)
            page_rows = [
                r for r in page_level_rows
                if r["program"] == prog and r["category"].startswith(alias)
            ]
            row = {
                "program": prog,
                "category": cat_name,
                "n_gt_courses": result["gt_fixed_course_count"],
                "code_recall": round(result["code_recall"], 3),
                "credits_exact_match": result["credits_exact_match"],
                "credits_checked": result["credits_checked"],
                "field_accuracy": "",
                "page_avg_precision": "",
                "page_avg_recall": "",
                "page_avg_f1": "",
                "page_exact_match_rate": "",
                "n_page_items": "",
            }
            if page_rows:
                n = len(page_rows)
                row["page_avg_precision"] = round(sum(r["precision"] for r in page_rows) / n, 3)
                row["page_avg_recall"] = round(sum(r["recall"] for r in page_rows) / n, 3)
                row["page_avg_f1"] = round(sum(r["f1"] for r in page_rows) / n, 3)
                row["page_exact_match_rate"] = round(sum(1 for r in page_rows if r["exact_match"]) / n, 3)
                row["n_page_items"] = n
            category_summary.append(row)

        rules_rows = field_level_rules.get(prog, [])
        if rules_rows:
            checked = [r for r in rules_rows if r["match"] is not None]
            acc = sum(1 for r in checked if r["match"]) / len(checked) if checked else None
            n_gt = len(rules_rows)

            page_rows = [r for r in page_level_rows if r["program"] == prog and r["category"].startswith("ข้อบังคับ")]
            row = {
                "program": prog,
                "category": "ข้อบังคับ",
                "n_gt_courses": n_gt,
                "code_recall": "N/A",
                "credits_exact_match": 0,
                "credits_checked": n_gt,
                "field_accuracy": round(acc, 3) if acc is not None else "N/A",
                "page_avg_precision": "",
                "page_avg_recall": "",
                "page_avg_f1": "",
                "page_exact_match_rate": "",
                "n_page_items": "",
            }
            if page_rows:
                n = len(page_rows)
                row["page_avg_precision"] = round(sum(r["precision"] for r in page_rows) / n, 3)
                row["page_avg_recall"] = round(sum(r["recall"] for r in page_rows) / n, 3)
                row["page_avg_f1"] = round(sum(r["f1"] for r in page_rows) / n, 3)
                row["page_exact_match_rate"] = round(sum(1 for r in page_rows if r["exact_match"]) / n, 3)
                row["n_page_items"] = n
            category_summary.append(row)

    # ------------------------------------------------------------------
    # ขั้นที่ 5: บันทึกผลลง lab6/outputs/
    # ------------------------------------------------------------------
    out_field = LAB6_OUT_DIR / "eval_field_level.json"
    out_page = LAB6_OUT_DIR / "eval_page_level.csv"
    out_cat = LAB6_OUT_DIR / "eval_category_summary.csv"

    with open(out_field, "w", encoding="utf-8") as f:
        json.dump({
            "courses": field_level_courses,
            "rules": field_level_rules,
        }, f, ensure_ascii=False, indent=2)

    if page_level_rows:
        with open(out_page, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(page_level_rows[0].keys()))
            w.writeheader()
            w.writerows(page_level_rows)

    if category_summary:
        with open(out_cat, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(category_summary[0].keys()))
            w.writeheader()
            w.writerows(category_summary)

    # ------------------------------------------------------------------
    # พิมพ์ผลสรุป
    # ------------------------------------------------------------------
    print()
    print("=" * 70)
    print("1) FIELD LEVEL EVALUATION (via Lab 4 evaluate_courses)")
    print("=" * 70)
    for prog, plans in field_level_courses.items():
        for name, result in plans.items():
            print(f"[{prog:4s}] {name:24s} code_recall={result['code_recall']:.3f} "
                  f"({result['codes_found']:3d}/{result['gt_fixed_course_count']:3d})  "
                  f"credits_match={result['credits_exact_match']:3d}/{result['credits_checked']:3d}")

    print()
    for prog, rows in field_level_rules.items():
        checked = [r for r in rows if r["match"] is not None]
        acc = sum(1 for r in checked if r["match"]) / len(checked) if checked else 0
        print(f"[{prog:4s}] {'ข้อบังคับ (ค่าตัวเลข)':24s} accuracy={acc:.3f} (n={len(checked)})")

    if page_level_rows:
        print()
        print("=" * 70)
        print("2) PAGE LEVEL EVALUATION (Map_page_all.csv)")
        print("=" * 70)
        for prog in PAGE_LEVEL_PROGRAMS:
            rows = [r for r in page_level_rows if r["program"] == prog]
            if not rows:
                continue
            n = len(rows)
            print(f"[{prog:4s}] n={n:3d}  "
                  f"precision={sum(r['precision'] for r in rows)/n:.3f}  "
                  f"recall={sum(r['recall'] for r in rows)/n:.3f}  "
                  f"f1={sum(r['f1'] for r in rows)/n:.3f}  "
                  f"exact_match={sum(1 for r in rows if r['exact_match'])/n:.3f}")
        n = len(page_level_rows)
        print(f"[ALL ] n={n:3d}  "
              f"precision={sum(r['precision'] for r in page_level_rows)/n:.3f}  "
              f"recall={sum(r['recall'] for r in page_level_rows)/n:.3f}  "
              f"f1={sum(r['f1'] for r in page_level_rows)/n:.3f}  "
              f"exact_match={sum(1 for r in page_level_rows if r['exact_match'])/n:.3f}")

    if category_summary:
        print()
        print("=" * 70)
        print("3) CATEGORY LEVEL SUMMARY")
        print("=" * 70)
        header = f"{'Program':6s} {'Category':32s} {'CodeRecall':>10s} {'FieldAcc':>9s} {'PageF1':>8s}"
        print(header)
        print("-" * len(header))
        for s in category_summary:
            cr = s["code_recall"] if isinstance(s["code_recall"], str) else f"{s['code_recall']:.3f}"
            fa = s["field_accuracy"] if isinstance(s["field_accuracy"], str) else f"{s['field_accuracy']:.3f}"
            pf1 = s["page_avg_f1"] if s["page_avg_f1"] != "" else "-"
            print(f"{s['program']:6s} {s['category']:32s} {cr:>10s} {fa:>9s} {str(pf1):>8s}")

    print()
    print(f"บันทึกผลลัพธ์แล้วที่ {LAB6_OUT_DIR.relative_to(PROJECT_ROOT)}/")
    print(f"  - {out_field.name}")
    print(f"  - {out_page.name}")
    print(f"  - {out_cat.name}")


if __name__ == "__main__":
    main()
