#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remap_pages.py — สคริปต์สแกนและแมปตำแหน่งเลขหน้าของรายวิชาอัตโนมัติ
จากไฟล์ Full OCR (outputs/fulldoc_*_ocr.json) และ Course Lists จาก OCR (outputs/OCR filtered/)
ปราศจากการใช้ Ground Truth (Zero Data Leakage) 100%

ผลลัพธ์:
  บันทึกเป็นไฟล์ data/map/Map_page_all.csv
  มีทั้งเลขหน้าตามไฟล์ PDF จริง (pdf_pages) และเลขหน้าที่พิมพ์บนเล่ม (printed_pages)
"""

import csv
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# กำหนด Path สัมพัทธ์จากตำแหน่ง Root ของโปรเจกต์
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
FILTERED_DIR = OUTPUTS_DIR / "OCR filtered"
OUT_CSV = SCRIPT_DIR / "Map_page_all.csv"

# การตั้งค่าสำหรับแต่ละหลักสูตร (อ้างอิงจาก OCR Filtered และ Full OCR เท่านั้น ปราศจาก Ground Truth)
PROGRAMS = [
    {
        "program": "DSBA",
        "ocr_file": OUTPUTS_DIR / "fulldoc_dsba_ocr.json",
        "filtered_files": [
            FILTERED_DIR / "DSBA_coop_filtered.json",
            FILTERED_DIR / "DSBA_no_coop_filtered.json",
        ],
        "pdf_offset": 5, # หน้าคำนำ/สารบัญโรมัน 5 หน้า
    },
    {
        "program": "IT",
        "ocr_file": OUTPUTS_DIR / "fulldoc_it_ocr.json",
        "filtered_files": [
            FILTERED_DIR / "IT_coop_filtered.json",
            FILTERED_DIR / "IT_no_coop_filtered.json",
        ],
        "pdf_offset": 5,
    },
    {
        "program": "BIT",
        "ocr_file": OUTPUTS_DIR / "fulldoc_BIT_ocr.json",
        "filtered_files": [
            FILTERED_DIR / "BIT_coop_filtered.json",
            FILTERED_DIR / "BIT_no_coop_filtered.json",
        ],
        "pdf_offset": 5,
    },
    {
        "program": "AIT",
        "ocr_file": OUTPUTS_DIR / "fulldoc_AIT_ocr.json",
        "filtered_files": [
            FILTERED_DIR / "AIT_filtered.json",
        ],
        "pdf_offset": 5,
    },
]


def run_remapping():
    print("=" * 70)
    print("  เริ่มกระบวนการสแกนและแมปเลขหน้าของรายวิชา (Pure OCR Page Remapping)")
    print("  แหล่งข้อมูล: outputs/OCR filtered/ และ outputs/fulldoc_*_ocr.json (ไม่ใช้ Ground Truth)")
    print("=" * 70)

    results = []
    summary_stats = {}

    for prog in PROGRAMS:
        p_name = prog["program"]
        print(f"\n[+] กำลังประมวลผลหลักสูตร: {p_name}")

        courses_map = {}

        # โหลดรายวิชาจาก Filtered OCR Files (Pure OCR Output)
        for fl_path in prog["filtered_files"]:
            if fl_path.exists():
                try:
                    with open(fl_path, "r", encoding="utf-8") as f:
                        d = json.load(f)
                        for c in d.get("courses", []):
                            code = str(c.get("code", "")).strip()
                            if re.match(r"^\d{8}$", code) and code not in courses_map:
                                courses_map[code] = {
                                    "code": code,
                                    "name_th": c.get("name_th", ""),
                                    "name_en": c.get("name_en", ""),
                                    "credits": c.get("credits", ""),
                                    "year": c.get("year", ""),
                                    "semester": c.get("semester", ""),
                                }
                except Exception as e:
                    print(f"    ข้อผิดพลาดในการอ่าน Filtered {fl_path.name}: {e}")

        print(f"    พบรายวิชาจาก OCR ที่ต้องแมป: {len(courses_map)} วิชา")

        # 3. โหลดข้อความจากไฟล์ OCR เต็ม
        ocr_file = prog["ocr_file"]
        if not ocr_file.exists():
            print(f"    [!] ไม่พบไฟล์ OCR: {ocr_file}")
            continue

        with open(ocr_file, "r", encoding="utf-8") as f:
            ocr_data = json.load(f)

        pages = ocr_data.get("pages", [])
        print(f"    กำลังสแกนข้อความในเอกสาร OCR ทั้งหมด: {len(pages)} หน้า...")

        page_texts = [(p.get("page"), p.get("text", "")) for p in pages]
        offset = prog["pdf_offset"]
        mapped_count = 0

        for code, info in sorted(courses_map.items()):
            found_pdf_pages = []
            found_printed_pages = []

            for page_num, text in page_texts:
                if code in text:
                    found_pdf_pages.append(page_num)
                    printed_num = max(1, page_num - offset)
                    found_printed_pages.append(printed_num)

            if found_pdf_pages:
                mapped_count += 1

            results.append({
                "program": p_name,
                "code": code,
                "name_th": info["name_th"],
                "name_en": info["name_en"],
                "year": info["year"],
                "semester": info["semester"],
                "credits": info["credits"],
                "pdf_pages": ";".join(map(str, found_pdf_pages)),
                "printed_pages": ";".join(map(str, found_printed_pages)),
                "match_count": len(found_pdf_pages),
            })

        summary_stats[p_name] = {
            "total": len(courses_map),
            "mapped": mapped_count,
            "coverage": f"{(mapped_count / len(courses_map) * 100):.1f}%" if courses_map else "0%",
        }

    # บันทึกเป็น CSV
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "program",
                "code",
                "name_th",
                "name_en",
                "year",
                "semester",
                "credits",
                "pdf_pages",
                "printed_pages",
                "match_count",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    print("\n" + "=" * 70)
    print("  สรุปผลการแมปเลขหน้า (Remapping Summary)")
    print("=" * 70)
    for p_name, s in summary_stats.items():
        print(f"  [{p_name}] ทั้งหมด: {s['total']:>2} วิชา | ตรวจพบใน OCR: {s['mapped']:>2} วิชา (ความครอบคลุม {s['coverage']})")
    print(f"\n[OK] บันทึกไฟล์ผลลัพธ์เรียบร้อย: {OUT_CSV}")
    print(f"[OK] รวมทั้งหมด {len(results)} รายการ")
    print("=" * 70)


if __name__ == "__main__":
    run_remapping()
