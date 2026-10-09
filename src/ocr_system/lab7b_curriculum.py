#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 lab7b_curriculum.py
 Lab 7B — สกัดแผนการศึกษาจากเล่มหลักสูตร ด้วย LLM ที่รันบนเครื่องตัวเอง
================================================================================

 วิชา 06026240 การพัฒนาระบบอัจฉริยะ  |  เทคโนโลยีสารสนเทศ สจล.
 --------------------------------------------------------------------------
 ⚠️  ข้อบังคับ: รันแบบออฟไลน์ 100% ไม่มีค่าใช้จ่าย
 --------------------------------------------------------------------------
 แม้เล่มหลักสูตรจะเป็นเอกสารสาธารณะ (ไม่เข้าข่าย PDPA) แต่แล็บนี้กำหนดให้
 ทุกกลุ่มใช้โมเดลที่รันบนเครื่องเท่านั้น ด้วยเหตุผล 3 ข้อ:
   1. นักศึกษาต้องไม่มีค่าใช้จ่าย
   2. ผลลัพธ์ต้องทำซ้ำได้ (API ภายนอกเปลี่ยนโมเดลเงียบ ๆ เมื่อไรก็ได้)
   3. เป็นทักษะที่ใช้ได้จริงเมื่อไปทำงานกับข้อมูลที่ห้ามออกนอกองค์กร

 --------------------------------------------------------------------------
 วิธีใช้
 --------------------------------------------------------------------------
   python3 lab7b_curriculum.py --check

   python3 lab7b_curriculum.py \
       --input data/DSBA_plan.pdf \
       --gt    gt/DSBA_academic_plan_coop.json \
       --pipeline all --out output/

   # เล่มหลักสูตรยาวมาก ให้ระบุเฉพาะหน้าที่เป็นตารางแผนการศึกษา
   python3 lab7b_curriculum.py -i data/DSBA.pdf --pages 42-58 -g gt/x.json

================================================================================
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lab7_metrics as M  # noqa: E402


# ==============================================================================
#  ส่วนที่ 0 — ค่าตั้งต้น
# ==============================================================================

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL_OCR = os.getenv("LAB7_MODEL_OCR", "scb10x/typhoon-ocr1.5-3b")
MODEL_TEXT = os.getenv("LAB7_MODEL_TEXT", "qwen3:4b")
DPI = int(os.getenv("LAB7_DPI", "150"))
REQUEST_TIMEOUT = 900

# ⭐ ค่าเฉพาะของกลุ่ม B
# เล่มหลักสูตรมี 50-150 หน้า ส่งเข้าโมเดลทีเดียวไม่ได้แน่นอน
# เราจึง "แบ่งเป็นก้อน" (chunk) ทีละไม่กี่หน้า แล้วรวมผลทีหลัง
PAGES_PER_CHUNK = int(os.getenv("LAB7_CHUNK", "1"))

# ข้าม pipeline baseline (Tesseract) ทั้งหมด
#     export LAB7_SKIP_BASELINE=1
# ⚠️ ผลที่ตามมา: จะไม่มีเส้นฐานไว้เปรียบเทียบ ทำให้ตอบคำถามท้ายบท
#    ชุดที่ 2 (เปรียบเทียบ pipeline) ไม่ได้ และเสียคะแนนส่วนที่ 3
SKIP_BASELINE = os.getenv("LAB7_SKIP_BASELINE", "").strip() in ("1", "true", "yes")

# ตารางเลขหน้าจริงในไฟล์ PDF สำหรับตารางแผนการศึกษาแต่ละหลักสูตร (ยืนยันตรงกับเล่ม 100%)
PLAN_PAGE_SPECS: dict[str, dict[str, str]] = {
    "DSBA": {
        "no_coop": "26-32",
        "coop": "33-39",
    },
    "BIT": {
        "no_coop": "26-30",
        "coop": "31-35",
    },
    "IT": {
        "no_coop": "32-38",
        "coop": "39-45",
    },
    "AIT": {
        "single": "23-26",
        "no_coop": "23-26",
        "coop": "23-26",
    },
}

# เลขหน้าจริงสำหรับดึงโครงสร้างหลักสูตรแบบสมบูรณ์ (รวมวิชาเฉพาะเลือก/แขนงวิชา) สำหรับ pipeline text
TEXT_PLAN_PAGE_SPECS: dict[str, dict[str, str]] = {
    "DSBA": {
        "no_coop": "22-32",
        "coop": "22-25,33-39",
    },
    "BIT": {
        "no_coop": "22-30",
        "coop": "22-25,31-35",
    },
    "IT": {
        "no_coop": "24-38",
        "coop": "24-31,39-45",
    },
    "AIT": {
        "single": "21-26",
        "no_coop": "21-26",
        "coop": "21-26",
    },
}


# ==============================================================================
#  ส่วนที่ 1 — ตรวจความพร้อม / ยืนยันออฟไลน์
# ==============================================================================


def _need(mod: str, pipname: str = "") -> Any:
    try:
        return __import__(mod)
    except ImportError:
        raise SystemExit(f"\n❌ ไม่พบไลบรารี '{mod}'\n   ติดตั้ง: pip install {pipname or mod}\n")


def assert_offline() -> None:
    """ตรวจว่า Ollama ชี้ไปที่เครื่องตัวเอง — fail closed ถ้าไม่แน่ใจ"""
    allowed = ("127.0.0.1", "localhost", "0.0.0.0", "::1")
    host = OLLAMA_HOST.replace("http://", "").replace("https://", "").split(":")[0]
    if host not in allowed:
        raise SystemExit(
            f"\n❌ OLLAMA_HOST = {OLLAMA_HOST} ไม่ใช่เครื่องภายใน\n"
            f"   แล็บนี้กำหนดให้รันออฟไลน์เท่านั้น  แก้โดย: unset OLLAMA_HOST\n")
    print(f"✓ ยืนยันโหมดออฟไลน์: {OLLAMA_HOST}")


def check_environment() -> bool:
    ok = True
    print("\n" + "=" * 70)
    print("  ตรวจความพร้อมของเครื่อง")
    print("=" * 70)

    if shutil.which("ollama"):
        try:
            v = subprocess.run(["ollama", "--version"], capture_output=True,
                               text=True, timeout=10).stdout.strip()
            print(f"  ✓ พบ Ollama: {v}")
        except Exception:
            print("  ✓ พบ Ollama")
    else:
        print("  ✗ ไม่พบคำสั่ง ollama --> ดูเอกสารแล็บ ส่วนที่ 2")
        ok = False

    try:
        requests = _need("requests")
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        installed = [m["name"] for m in r.json().get("models", [])]
        print(f"  ✓ Ollama service ทำงานที่ {OLLAMA_HOST}")
        for tag, role in [(MODEL_OCR, "อ่านภาพ"), (MODEL_TEXT, "จัด JSON")]:
            hit = any(i == tag or i.split(":")[0] == tag for i in installed)
            print(f"  {'✓' if hit else '✗'} [{role}] {tag}"
                  + ("" if hit else f"   --> ollama pull {tag}"))
            if not hit:
                ok = False
    except Exception as e:
        print(f"  ✗ ต่อ Ollama ไม่ได้: {e}\n    --> สั่ง: ollama serve")
        ok = False

    for mod, pip in [("fitz", "pymupdf"), ("PIL", "pillow"),
                     ("requests", "requests"), ("pdfplumber", "pdfplumber"),
                     ("pythainlp", "pythainlp")]:
        try:
            __import__(mod)
            print(f"  ✓ python: {mod}")
        except ImportError:
            print(f"  ✗ python: {mod} --> pip install {pip}")
            ok = False

    # --- ของที่ไม่จำเป็น — ขาดได้ ไม่ทำให้ --check ตก ---
    #
    # ⚠️ สังเกตว่าส่วนนี้ "ไม่มี ok = False" เลย
    #    สิ่งที่ทำให้ผลตรวจ "ไม่พร้อม" ต้องเป็นสิ่งที่ขาดแล้วรันไม่ได้จริงเท่านั้น
    print("\n  ส่วนเสริม (ขาดได้ ไม่ทำให้ --check ตก):")

    if SKIP_BASELINE:
        print("  ○ tesseract — ข้ามตามค่า LAB7_SKIP_BASELINE=1")
    else:
        has_exe = shutil.which("tesseract") is not None
        try:
            __import__("pytesseract")
            has_lib = True
        except ImportError:
            has_lib = False

        if has_exe and has_lib:
            print("  ✓ tesseract (จาก Lab 5-6) — ใช้กับ pipeline baseline")
        else:
            miss = []
            if not has_lib:
                miss.append("pip install pytesseract")
            if not has_exe:
                miss.append("ติดตั้งตัว engine (ดูเอกสาร Lab 5)")
            print(f"  ✗ tesseract — {' + '.join(miss)}")
            print("      pipeline baseline จะถูกข้ามไป (text และ vlm ยังใช้ได้ตามปกติ)")
            print("      ถ้าไม่ต้องการใช้ baseline เลย:  export LAB7_SKIP_BASELINE=1")

    print("=" * 70)
    print("  พร้อมใช้งาน ✓" if ok else "  ยังไม่พร้อม ✗")
    print("=" * 70 + "\n")
    return ok


# ==============================================================================
#  ส่วนที่ 2 — เตรียม input
# ==============================================================================


def parse_page_range(spec: str, total: int) -> list[int]:
    """
    แปลงข้อความอย่าง "42-58" หรือ "3,7,10-12" เป็น list ของ index (เริ่มที่ 0)

    ทำไมต้องมี? เพราะเล่มหลักสูตรมี 150 หน้า แต่ตารางแผนการศึกษาอยู่แค่ 10-20 หน้า
    การส่งทั้งเล่มเข้าโมเดลคือการเผาเวลาไปกับหน้าที่ไม่เกี่ยวข้อง
    (ในระบบที่จ่ายเงินตาม token นี่คือการเผาเงินด้วย)
    """
    idx: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            idx.update(range(int(a) - 1, int(b)))    # ผู้ใช้พิมพ์เลขหน้าเริ่มที่ 1
        elif part:
            idx.add(int(part) - 1)
    return sorted(i for i in idx if 0 <= i < total)


def load_pages(path: str, page_spec: str | None = None) -> list[bytes]:
    """แปลง PDF เป็นภาพ PNG รายหน้า"""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"❌ ไม่พบไฟล์: {path}")

    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        return [p.read_bytes()]

    fitz = _need("fitz", "pymupdf")
    doc = fitz.open(str(p))
    wanted = parse_page_range(page_spec, len(doc)) if page_spec else range(len(doc))

    if page_spec:
        print(f"  เล่มมี {len(doc)} หน้า — เลือกใช้ {len(list(wanted))} หน้า")

    mat = fitz.Matrix(DPI / 72, DPI / 72)
    pages = []
    for i in wanted:
        pix = doc[i].get_pixmap(matrix=mat)
        pages.append(pix.tobytes("png"))
    doc.close()
    print(f"  แปลงเป็นภาพแล้ว {len(pages)} หน้า @ {DPI} DPI")
    return pages


PUA_MAP = {
    0xf700: 0x0e10,  # ฐ ฐานไม่มีเชิง
    0xf701: 0x0e34,  # สระอิ (บน ป ฝ ฟ ฬ)
    0xf702: 0x0e35,  # สระอี (บน ป ฝ ฟ ฬ)
    0xf703: 0x0e36,  # สระอึ (บน ป ฝ ฟ ฬ)
    0xf704: 0x0e37,  # สระอือ (บน ป ฝ ฟ ฬ)
    0xf705: 0x0e48,  # ไม้เอก
    0xf706: 0x0e49,  # ไม้โท
    0xf707: 0x0e4a,  # ไม้ตรี
    0xf708: 0x0e4b,  # ไม้จัตวา
    0xf709: 0x0e4c,  # การันต์
    0xf70a: 0x0e48,  # ไม้เอก
    0xf70b: 0x0e49,  # ไม้โท
    0xf70c: 0x0e4a,  # ไม้ตรี
    0xf70d: 0x0e4b,  # ไม้จัตวา
    0xf70e: 0x0e4c,  # การันต์
    0xf70f: 0x0e4d,  # นิคหิต
    0xf710: 0x0e31,  # ไม้หันอากาศ (บน ป ฝ ฟ ฬ)
    0xf711: 0x0e34,  # สระอิ
    0xf712: 0x0e47,  # ไม้ไต่คู้ (บน ป ฝ ฟ ฬ)
    0xf713: 0x0e48,  # ไม้เอก ชั้นบน
    0xf714: 0x0e49,  # ไม้โท ชั้นบน
    0xf715: 0x0e4a,  # ไม้ตรี ชั้นบน
    0xf716: 0x0e4b,  # ไม้จัตวา ชั้นบน
    0xf717: 0x0e4c,  # การันต์ ชั้นบน
    0xf718: 0x0e38,  # สระอุ
    0xf719: 0x0e39,  # สระอู
    0xf71a: 0x0e3a,  # พินทุ
}

def clean_thai(s: str) -> str:
    if not s:
        return ""
    # 1. แปลงอักขระฟอนต์ PUA ให้เป็น Unicode ภาษาไทยมาตรฐานตามข้อกำหนดฟอนต์ PDF
    s = s.translate(PUA_MAP)

    # 2. จัดการอักขระควบคุมช่องว่างพิเศษ (Zero-Width Spaces, BOM, Non-Breaking Spaces)
    s = re.sub(r"[\u200b\u200c\u200d\ufeff\xa0]", " ", s)

    # 3. กฎอักขรวิธี Unicode สากล: สระหน้าแทรกก่อนการันต์ (เช่น ...ร์ + เ... -> รเ์ กลายเป็น ร์เ)
    s = re.sub(r"([\u0e40-\u0e44])([\u0e4c])", r"\2\1", s)

    # 4. กฎอักขรวิธี Unicode สากล: สระหน้า + พยัญชนะต้น + ตัวสะกด + วรรณยุกต์ -> ย้ายวรรณยุกต์มาไว้บนพยัญชนะต้น
    # เช่น เ + ส + น + ้ (เสน้) -> เ + ส + ้ + น (เส้น)
    s = re.sub(r"([เแโใไ])([\u0e01-\u0e2e])([งนมดบกยว])([\u0e48-\u0e4b])", r"\1\2\4\3", s)

    # 5. กฎอักขรวิธี Unicode สากล: ตัวสะกด ง/น/ม วางก่อนสระบน -> สลับตัวสะกดไปไว้หลังสระบน
    # เช่น ส + ง + ิ + ่ (สงิ่) -> ส + ิ + ่ + ง (สิ่ง), พ + น + ื + ้ (พนื้) -> พ + ื + ้ + น (พื้น)
    s = re.sub(r"([\u0e01-\u0e2e])([งนม])([\u0e34-\u0e37])([\u0e48-\u0e4b]?)", r"\1\3\4\2", s)

    # 6. กฎอักขรวิธี Unicode สากล: ว สลับกับ สระอิ ใน พิว (เช่น คอมพวิ เตอร์ -> คอมพิวเตอร์)
    s = re.sub(r"พว([\u0e34-\u0e37])", r"พ\1ว", s)

    # 7. กฎอักขรวิธี Unicode สากล: ไม้ไต่คู้พิมพ์หลังตัวสะกด (เ + พยัญชนะต้น + พยัญชนะสะกด + ไม้ไต่คู้ เช่น เปน็ -> เป็น)
    s = re.sub(r"(เ[\u0e01-\u0e2e])([\u0e01-\u0e2e])\u0e47", r"\1" + "\u0e47" + r"\2", s)

    # 8. กฎอักขรวิธี Unicode สากล: สระเอีย (เ + พยัญชนะ + ย + สระอี -> เ + พยัญชนะ + สระอี + ย เช่น เขยี น -> เขียน)
    s = re.sub(r"(เ[\u0e01-\u0e2e])(ย)([\u0e35])([\u0e48-\u0e4b]?)\s*", r"\1\3\4\2", s)

    # 9. กฎอักขรวิธี Unicode สากล: ลบช่องว่างหน้า/หลังสระบน/ล่าง วรรณยุกต์ และการันต์
    s = re.sub(r"([\u0e01-\u0e2e])\s+([\u0e31\u0e34-\u0e3a\u0e48-\u0e4e])", r"\1\2", s)
    s = re.sub(r"([\u0e31\u0e34-\u0e3a\u0e48-\u0e4e])\s+([\u0e01-\u0e2e])", r"\1\2", s)
    s = re.sub(r"\s+([\u0e31\u0e34-\u0e3a\u0e47-\u0e4e])", r"\1", s)

    # 10. กฎอักขรวิธี Unicode สากล: ลบช่องว่างหลังสระหน้า
    s = re.sub(r"([\u0e40-\u0e44])\s+", r"\1", s)

    # 11. จัดเรียงลำดับไบต์ตามมาตรฐานภาษาศาสตร์ภาษาไทย (Canonical Combining Class)
    try:
        from pythainlp.util import normalize as thai_normalize, reorder_vowels, remove_spaces_before_marks
        s = thai_normalize(s)
        s = reorder_vowels(s)
        s = remove_spaces_before_marks(s)
    except Exception:
        pass

    # 12. ยุบช่องว่างซ้ำซ้อน
    return re.sub(r"[ \t]+", " ", s).strip()


def extract_pdf_text(path: str, page_spec: str | None = None) -> str:
    """
    ดึงข้อความจาก PDF โดยตรง (ถ้าเป็น PDF ที่ฝังข้อความไว้ ไม่ใช่ภาพสแกน)
    """
    pdfplumber = _need("pdfplumber")
    out = []
    with pdfplumber.open(path) as pdf:
        wanted = parse_page_range(page_spec, len(pdf.pages)) if page_spec \
            else range(len(pdf.pages))
        for i in wanted:
            # layout=True รักษาระยะห่างแนวนอน ทำให้คอลัมน์ยังเรียงกันอยู่
            t = pdf.pages[i].extract_text(layout=True) or ""
            t = clean_thai(t)
            out.append(f"\n=== หน้า {i + 1} ===\n{t}")
    return "\n".join(out)


def extract_pdf_course_descriptions(pdf_path: str) -> tuple[dict[str, str], dict[str, str], dict[str, list[int]], dict[str, str], dict[str, str]]:
    """
    สกัดวิชาบังคับก่อน (Prerequisite), ชื่อภาษาอังกฤษเต็ม (name_en), ชื่อภาษาไทยเต็ม (name_th),
    หน่วยกิต (credits) และเลขหน้าที่พบในเล่ม (course_pages) จากหมวดคำอธิบายรายวิชาของเล่มหลักสูตร PDF โดยตรง
    """
    p = Path(pdf_path)
    if not p.exists():
        return {}, {}, {}, {}, {}
    if p.is_dir() or p.suffix.lower() != ".pdf":
        candidates = list(p.glob("*.pdf")) + list(p.parent.glob("*.pdf")) + list(p.parent.glob("data/*.pdf"))
        if candidates:
            p = candidates[0]
        else:
            return {}, {}, {}, {}, {}

    fitz = _need("fitz")
    prereqs: dict[str, str] = {}
    en_names: dict[str, str] = {}
    th_names: dict[str, str] = {}
    credits_map: dict[str, str] = {}
    course_pages: dict[str, list[int]] = {}

    try:
        doc = fitz.open(str(p))
        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            page_text = clean_thai(doc[page_idx].get_text())
            lines = [l.strip() for l in page_text.splitlines() if l.strip()]
            for i, line in enumerate(lines):
                # ป้องกันกรณีบรรทัดนี้เป็นเพียงวิชาบังคับก่อนของวิชาอื่นที่อยู่บรรทัดก่อนหน้า
                if i > 0 and any(k in lines[i - 1] for k in ["วิชาบังคับก่อน", "PREREQUISITE", "Prerequisite"]):
                    continue
                if i > 1 and any(k in lines[i - 2] for k in ["วิชาบังคับก่อน", "PREREQUISITE", "Prerequisite"]) and not re.match(r"^\d{8}", lines[i - 1]):
                    continue

                m_code = re.match(r"^(\d{8})(?:\s+(.*))?$", line)
                if not m_code:
                    continue

                code = m_code.group(1)
                inline_name = m_code.group(2) or ""

                if code not in course_pages:
                    course_pages[code] = []
                if page_num not in course_pages[code]:
                    course_pages[code].append(page_num)

                th_parts = []
                en_parts = []

                if inline_name:
                    if re.search(r"[\u0e00-\u0e7f]", inline_name):
                        if not any(sk in inline_name for sk in ["คงอยู่", "เปลี่ยนชื่อเป็น", "ย้ายรายวิชา", "กลุ่มวิชา", "หลักสูตร"]):
                            clean_inline = re.sub(r"\s*\([A-Za-z\s]+.*$", "", inline_name).strip()
                            th_parts.append(clean_inline)
                    elif (re.match(r"^[A-Z0-9\s\-\,\&\/\'\(\)]+$", inline_name) or bool(re.search(r"21st\s+CENTURY", inline_name, re.I))) and any(c.isupper() for c in inline_name):
                        en_parts.append(inline_name)

                idx = i + 1
                seen_prereq_header = False
                en_done = False
                th_done = bool(th_parts)

                while idx < min(len(lines), i + 25):
                    cur = lines[idx]
                    if re.match(r"^(?:\d{8}|[0-9xX]{8})\b", cur):
                        break
                    if any(k in cur.upper() for k in ["ELECTIVE", "FREE ELECTIVE", "GENERAL EDUCATION", "MAJOR ELECTIVE", "หมวดวิชา", "วิชาเลือก", "กลุ่มวิชา", "แผนการเรียน", "รวม", "TOTAL"]):
                        break

                    if "วิชาบังคับก่อน" in cur or "PREREQUISITE" in cur or "Prerequisite" in cur:
                        seen_prereq_header = True
                        en_done = True
                        th_done = True
                        found_pre = [c for c in re.findall(r"\b\d{8}\b", cur) if c != code]
                        if not found_pre and idx + 1 < len(lines):
                            nxt_line = lines[idx + 1]
                            found_pre = [c for c in re.findall(r"\b\d{8}\b", nxt_line) if c != code]
                            if not found_pre and idx + 2 < len(lines):
                                nxt_line2 = lines[idx + 2]
                                found_pre = [c for c in re.findall(r"\b\d{8}\b", nxt_line2) if c != code]

                        context_pre = cur
                        if idx + 1 < len(lines): context_pre += " " + lines[idx + 1]
                        if idx + 2 < len(lines): context_pre += " " + lines[idx + 2]
                        all_found = [c for c in re.findall(r"\b\d{8}\b", context_pre) if c != code]
                        if len(all_found) > 1 and ("หรือ" in context_pre or "OR" in context_pre or "or" in context_pre):
                            join_str = " หรือ "
                        else:
                            join_str = ", "

                        if all_found and code not in prereqs:
                            prereqs[code] = join_str.join(sorted(list(set(all_found))))
                        idx += 1
                        continue

                    m_cred = re.search(r"\b(\d\s*\([\d\s\-xX]+\))", cur)
                    if m_cred:
                        if code not in credits_map:
                            credits_map[code] = m_cred.group(1).replace(" ", "")
                        if en_parts:
                            en_done = True
                        idx += 1
                        continue

                    if seen_prereq_header:
                        idx += 1
                        continue

                    # สกัดชื่อวิชาภาษาอังกฤษ (ต้องเป็นตัวพิมพ์ใหญ่ และไม่ใช่ประโยคคำอธิบายรายวิชา)
                    is_uppercase_en = (
                        re.match(r"^[A-Z0-9\s\-\,\&\/\'\(\)]+$", cur) or
                        bool(re.search(r"21st\s+CENTURY", cur, re.I))
                    ) and any(c.isupper() for c in cur)

                    is_skip = any(cur.startswith(sk) for sk in ["PREREQUISITE", "NONE", "COURSE", "PAGE", "TOTAL", "มคอ", "วท.บ", "ปที่", "ปีที่", "ภาคการศึกษา"])

                    if is_uppercase_en and not is_skip and not en_done:
                        if not cur.endswith("."):
                            en_parts.append(cur)
                        else:
                            en_done = True
                    elif any("\u0e00" <= c <= "\u0e7f" for c in cur):
                        if en_parts:
                            en_done = True
                        if not th_done and not th_parts:
                            if not any(cur.startswith(sk) for sk in ["มคอ.", "วท.บ", "คณะเทคโนโลยี", "คำอธิบายรายวิชา", "กลุ่มวิชา", "ปที่", "ปีที่", "ภาคการศึกษา"]):
                                clean_cur = re.sub(r"^(?:หรือ|และ)\s*", "", cur)
                                clean_cur = re.sub(r"\s*\([A-Za-z\s]+.*$", "", clean_cur).strip()
                                th_parts.append(clean_cur)
                                th_done = True

                    idx += 1

                if en_parts:
                    full_en = " ".join(en_parts).strip()
                    full_en = re.sub(r"\s+", " ", full_en)
                    full_en = re.sub(r"\s*(?:หรือ|OR)\s*$", "", full_en, flags=re.I).strip()
                    if len(full_en) <= 120:
                        if code not in en_names or len(full_en) > len(en_names[code]):
                            en_names[code] = full_en
                if th_parts:
                    full_th = clean_thai(" ".join(th_parts).strip())
                    full_th = re.sub(r"\s+", " ", full_th)
                    if len(full_th) <= 120:
                        if code not in th_names or len(full_th) > len(th_names[code]):
                            th_names[code] = full_th

    except Exception as e:
        print(f"    ⚠ ไม่สามารถสกัดคำอธิบายรายวิชาจาก PDF: {e}")
    return prereqs, en_names, course_pages, th_names, credits_map

# ==============================================================================
#  ส่วนที่ 3 — JSON SCHEMA
# ==============================================================================
#
#  Schema ต้องตรงกับ ground truth (DSBA_academic_plan_coop.json) เป๊ะ ๆ
#
#  ⚠️ ข้อสังเกตจาก ground truth จริง ที่ต้องสะท้อนใน schema:
#
#   1. `year` และ `semester` เป็น "0" ได้ ซึ่งไม่ได้แปลว่าปี 0
#      แต่แปลว่า "วิชาเลือก ที่ยังไม่กำหนดว่าจะลงปีไหน/ภาคไหน"
#      กรณีนี้ต้องกรอก flexible_year_semester แทน เช่น "3/1, 3/2, 4/1"
#
#   2. `prerequisite` เป็น string ไม่ใช่ list  ถ้าไม่มีให้ใส่คำว่า "ไม่มี"
#      (ไม่ใช่ null, ไม่ใช่ [] — ต้องตรงกับ GT)
#
#   3. `credits` เป็น string รูปแบบ "3(3-0-6)"
#      แปลว่า 3 หน่วยกิต = บรรยาย 3 ชม. - ปฏิบัติ 0 ชม. - ศึกษาเอง 6 ชม.
#      บางวิชาเป็น "3(3-0-6) หรือ 3(2-2-5)" ได้ด้วย
#
#   4. `name_en` ใน GT มีอักขระขึ้นบรรทัดใหม่ (\n) ฝังอยู่
#      เพราะชื่อยาวเกินความกว้างคอลัมน์ใน PDF แล้วถูกตัดบรรทัด
#      --> เราจะจัดการด้วย normalization ไม่ใช่บังคับให้โมเดลเดาว่าตัดตรงไหน
# ==============================================================================

VALID_CATEGORIES = {"หมวดวิชาศึกษาทั่วไป", "หมวดวิชาเฉพาะ", "หมวดวิชาเลือกเสรี"}
VALID_TYPES = {"บังคับ", "เลือก"}
CREDIT_RE = re.compile(r"^\d+\([\d\-xX]+\)$")
BLOCK_COURSE_CREDITS = 6

_S = {"type": "string"}
_SN = {"type": ["string", "null"]}

COURSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "program": _SN,          # เช่น "DSBA"
        "plan": _SN,             # เช่น "coop" หรือ "normal"
        "courses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": _S,           # รหัสวิชา 8 หลัก
                    "name_th": _SN,
                    "name_en": _SN,
                    "credits": _SN,       # "3(3-0-6)"
                    "year": {"type": ["integer", "string", "null"]},
                    "semester": {"type": ["integer", "string", "null"]},
                    "category": _SN,      # หมวดวิชาศึกษาทั่วไป / เฉพาะ / เลือกเสรี
                    "type": _SN,          # บังคับ / เลือก
                    "prerequisite": _SN,  # รหัสวิชา หรือคำว่า "ไม่มี"
                    "flexible_year_semester": _SN,
                    "note": _SN,
                    "alt_group": _SN,     # กลุ่มวิชาทางเลือก (Alternative Group) เช่น แขนง หรือ สหกิจ
                },
                "required": [
                    "code",
                    "name_th",
                    "name_en",
                    "credits",
                    "year",
                    "semester",
                    "category",
                    "type",
                    "prerequisite",
                ],
            },
        },
    },
    "required": ["courses"],
}


# ==============================================================================
#  ส่วนที่ 4 — PROMPT
# ==============================================================================

SYSTEM_PROMPT = """You are a precise document extraction system for Thai university curriculum documents.
You transcribe exactly what is printed. You never invent courses that are not in the document.
You never stop early. When a field is absent you output null."""

EXTRACT_PROMPT = """ต่อไปนี้คือข้อความจากเล่มหลักสูตรของสถาบันในประเทศไทย
จงสกัดรายวิชาทั้งหมดออกมาเป็น JSON ตาม schema ที่กำหนดอย่างถูกต้องและครบถ้วน

=== กติกาสำคัญ ===

[1] สกัดทุกวิชาที่ปรากฏ ห้ามข้าม ห้ามหยุดกลางทาง ดูให้ครบทุกหมวด:
    - หมวดวิชาศึกษาทั่วไป
    - หมวดวิชาเฉพาะ (วิชาแกน / บังคับ / เลือก)
    - หมวดวิชาเลือกเสรี
    - รายวิชาสหกิจศึกษา

[2] ปี/ภาคการศึกษา (year / semester):
    - วิชาบังคับที่ระบุปีและภาคชัดเจน -> year = 1..4, semester = 1..3, flexible_year_semester = null
    - วิชาเลือก ที่ลงได้หลายภาค หรือไม่ระบุปี/ภาค -> year = 0, semester = 0 และระบุใน flexible_year_semester เช่น "3/1, 3/2, 4/1"

[3] prerequisite (วิชาบังคับก่อน):
    - ถ้ามี ให้ใส่รหัสวิชา 8 หลัก เช่น "06026200"
    - ถ้าไม่มี ให้ใส่คำว่า "ไม่มี" (ห้ามใส่ null, ห้ามใส่ [])

[4] credits: คัดลอกรูปแบบหน่วยกิต เช่น "3(3-0-6)" หรือ "3(2-2-5)" หรือ "3(3-0-6) หรือ 3(2-2-5)"

[5] category: ต้องระบุในฟิลด์ "category" เสมอ โดยเป็น 1 ใน 3 ค่านี้เท่านั้น:
    - "หมวดวิชาศึกษาทั่วไป" (รหัสขึ้นต้นด้วย 90 หรือ 96 เช่น 9064xxxx)
    - "หมวดวิชาเฉพาะ" (รหัสขึ้นต้นด้วย 06 เช่น 0601xxxx, 0604xxxx, 0606xxxx หรือวิชาเฉพาะของหลักสูตร)
    - "หมวดวิชาเลือกเสรี" (รหัส xxxxxxxx หรือวิชาเลือกเสรี)

[6] type: ต้องระบุในฟิลด์ "type" เสมอ และต้องเป็น "บังคับ" หรือ "เลือก" เท่านั้น (ห้ามใส่ใน note)

[7] name_en (ชื่อวิชาภาษาอังกฤษ) และ name_th (ชื่อวิชาภาษาไทย):
    - คัดลอกชื่อวิชาภาษาไทยใส่ "name_th" และชื่อภาษาอังกฤษใส่ "name_en"
    - หากชื่อวิชาไทยและอังกฤษอยู่ในบรรทัดเดียวกัน เช่น "แคลคูลัส 1 CALCULUS 1" ให้แยก:
      name_th = "แคลคูลัส 1"
      name_en = "CALCULUS 1"
    - ถ้าชื่อถูกตัดขึ้นบรรทัดใหม่ ให้ต่อเป็นบรรทัดเดียวโดยเว้นวรรค 1 ครั้ง (ถ้าไม่มีภาษาอังกฤษให้ใส่ null)

[8] ⭐ แถว "ช่องวิชาเลือก" (Placeholder) เช่น "06026xxx", "060464xx", "9064xxxx", "xxxxxxxx" ถือเป็นข้อมูลจริง ต้องสกัดออกมาด้วย

[9] ⭐ alt_group (กลุ่มวิชาทางเลือก/แขนง/สหกิจ):
    - เมื่อพบหัวข้อกลุ่มวิชาหรือแขนง เช่น "กลุ่มวิชาด้านการพัฒนาซอฟต์แวร์" ให้สกัด alt_group ตามช่องทางเลือก เช่น "alt_track_y2s2_slot0"
    - ถ้ารหัสวิชาคั่นด้วย "หรือ" ให้ใส่ alt_group เช่น "alt_choice_y2s1_06016428"
    - ถ้าเป็นวิชาสหกิจศึกษา ให้ใส่ alt_group เช่น "alt_coop_y4s1"
    - ถ้าไม่มีทางเลือก ให้ใส่ null

[10] ⭐ รูปแบบข้อความและการสกัด:
    - ข้อความจากเอกสารอาจเป็นข้อความปกติ, ตาราง Markdown หรือตาราง HTML (<table><tr><td>...</td></tr></table>)
    - ให้อ่านและสกัดรายวิชาตามโครงสร้างแถว (<tr>) ของตารางอย่างละเอียด:
      * คอลัมน์แรกคือรหัสวิชา (code) เช่น "06046400", "9064xxxx", "xxxxxxxx"
      * ถ้ารหัสวิชามีคำว่า "หรือ" คั่น เช่น "06046443 หรือ 06046444" ให้ใส่ code เป็น "06046443 หรือ 06046444"
      * หากเซลล์รหัสวิชามีหลายรหัสคั่นด้วย <br/> หรือเว้นวรรค (เช่น <td rowspan="3">06036106<br/>06036116<br/>96643021</td>):
        รหัสแต่ละตัวจะตรงกับวิชาในแต่ละแถวตามลำดับ ให้แยกสกัดเป็นรายวิชาละ 1 รหัสวิชา (ห้ามนำหลายรหัสมาใส่รวมกันในฟิลด์เดียว)
      * คอลัมน์ถัดไปคือชื่อวิชา ให้แยก name_th และ name_en
      * คอลัมน์ถัดไปคือหน่วยกิต (credits) เช่น "3(3-0-6)" (ตัดวรรคออก)
      * ปีและภาคการศึกษา ดูจากหัวข้อตาราง เช่น "ปีที่ 1 ภาคการศึกษาที่ 1" -> year = 1, semester = 1
    - ในแต่ละหน้าอาจมีหลายตาราง (เช่น ตารางภาค 1 และตารางภาค 2 หรือตารางวิชาสหกิจศึกษา) ต้องสกัดทุกตารางจนครบถ้วน ห้ามหยุดเมื่อจบตารางแรก
    - ⚠️ สกัดรายวิชาทุกวิชาที่ปรากฏใน "ข้อความจากเอกสาร" ด้านล่าง ห้ามข้ามวิชาใดเด็ดขาด ห้ามหยุดก่อนครบทุกวิชา

=== รูปแบบโครงสร้าง JSON ที่ต้องส่งกลับ (JSON Format) ===
```json
{{
  "program": "<ชื่อหรือรหัสหลักสูตรจากเอกสาร>",
  "plan": "<แผนการศึกษา เช่น normal หรือ coop หรือ null>",
  "courses": [
    {{
      "code": "<รหัสวิชา 8 หลักที่พบในเอกสาร>",
      "name_th": "<ชื่อวิชาภาษาไทยจากเอกสาร>",
      "name_en": "<ชื่อวิชาภาษาอังกฤษจากเอกสาร หรือ null>",
      "credits": "<หน่วยกิต เช่น 3(3-0-6)>",
      "year": 1,
      "semester": 1,
      "category": "<หมวดวิชาศึกษาทั่วไป หรือ หมวดวิชาเฉพาะ หรือ หมวดวิชาเลือกเสรี>",
      "type": "<บังคับ หรือ เลือก>",
      "prerequisite": "<รหัสวิชา หรือ 'ไม่มี'>",
      "flexible_year_semester": null,
      "note": null,
      "alt_group": null
    }}
  ]
}}
```

=== ข้อความจากเอกสาร ===
{document_text}

=== สิ้นสุดข้อความ ===
ตอบเป็น JSON เท่านั้น โดยสกัดทุกวิชาจากข้อความด้านบนให้ครบถ้วน"""

TYPHOON_PROMPT = "Extract all text from the image. Only return the clean Markdown."


# ==============================================================================
#  ส่วนที่ 5 — เรียก Ollama
# ==============================================================================


def ollama_chat(model: str, messages: list[dict], *, fmt: dict | None = None,
                images: list[bytes] | None = None, temperature: float = 0.0,
                retries: int = 2) -> str:
    """เหมือนกับของกลุ่ม A — ดูคำอธิบายละเอียดในเอกสารแล็บ ส่วนที่ 4"""
    requests = _need("requests")

    if images:
        messages = [dict(m) for m in messages]
        messages[-1]["images"] = [base64.b64encode(im).decode() for im in images]

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "temperature": temperature,
            "num_ctx": 8192,
            "num_predict": 4096,
        },
    }
    if fmt is not None:
        payload["format"] = "json"

    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            t0 = time.time()
            r = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload,
                              timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            body = r.json()
            msg = body.get("message", {})
            content = msg.get("content", "")
            if not content.strip() and msg.get("thinking"):
                content = msg["thinking"]
            # eval_count = จำนวน token ที่โมเดลผลิต — ใช้ดูว่าโดนตัดหรือไม่
            n_out = body.get("eval_count", 0)
            print(f"      ({model}: {time.time() - t0:.1f} วิ, "
                  f"{len(content):,} ตัวอักษร, {n_out:,} tokens)")
            if n_out >= payload["options"]["num_predict"] - 8:
                print("      ⚠ ผลลัพธ์อาจถูกตัดเพราะชน num_predict "
                      "--> ลดจำนวนหน้าต่อ chunk หรือเพิ่ม num_predict")
            if not content.strip():
                raise ValueError("โมเดลตอบว่าง")
            return content
        except Exception as e:
            last = e
            if attempt < retries:
                print(f"      ⚠ ลองใหม่ {attempt + 1}: {e}")
                time.sleep(3)
    raise RuntimeError(f"เรียก {model} ไม่สำเร็จ: {last}")


def parse_json(text: str) -> dict:
    t = re.sub(r"<think>.*?</think>", "", text.strip(), flags=re.DOTALL)
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t.strip(), flags=re.MULTILINE)
    starts = [p for p in (t.find("{"), t.find("[")) if p != -1]
    if not starts:
        raise ValueError(f"ไม่พบ JSON:\n{text[:400]}")
    obj, _ = json.JSONDecoder().raw_decode(t[min(starts):])
    return obj


# ==============================================================================
#  ส่วนที่ 6 — การรวมผลจากหลาย chunk
# ==============================================================================


def clean_and_normalize_course(c: dict) -> dict:
    """ทำความสะอาดและเติมเต็มฟิลด์รายวิชาตามกฎมาตรฐานของหลักสูตร"""
    code_raw = str(c.get("code") or "").strip()
    if "หรือ" not in code_raw and ("<br" in code_raw or re.search(r"\s+", code_raw)):
        m_code = re.search(r"(\d{8}|\d{4}[xX]{4}|\d{5}[xX]{3}|\d{6}[xX]{2}|[xX]{6,8})", code_raw)
        if m_code:
            code_raw = m_code.group(1)

    if re.fullmatch(r"[xX]+", code_raw):
        code_raw = "xxxxxxxx"
    elif re.fullmatch(r"9[06]64[xX]+", code_raw):
        code_raw = code_raw[:4] + "xxxx"

    name_th = str(c.get("name_th") or "").strip() if c.get("name_th") is not None else None
    name_en = str(c.get("name_en") or "").strip() if c.get("name_en") is not None else None
    credits_val = str(c.get("credits") or "").strip() if c.get("credits") is not None else None
    year = c.get("year")
    sem = c.get("semester")
    cat = c.get("category")
    ctype = c.get("type")
    prereq = c.get("prerequisite")
    flex = c.get("flexible_year_semester")
    note = c.get("note")

    # 1. จัดการ name_th และ name_en
    if name_th:
        name_th = re.sub(r"<br\s*/?>", " ", name_th)
        name_th = re.sub(r"\s+", " ", name_th).strip()

    if name_en in ("None", "null", ""):
        name_en = None
    elif name_en:
        name_en = re.sub(r"<br\s*/?>", " ", name_en)
        name_en = re.sub(r"\s+", " ", name_en).strip()

    # แยกชื่ออังกฤษออกจาก name_th หาก name_en ยังไม่มี
    if not name_en and name_th:
        m_en_split = re.match(r"^([^\x00-\x7F\n]+.*?)\s+([A-Za-z][A-Za-z0-9\s\(\)\,\.\/\-\&]+)$", name_th)
        if m_en_split:
            name_th = m_en_split.group(1).strip()
            name_en = m_en_split.group(2).strip()

    # 2. จัดการ credits
    if credits_val in ("None", "null", ""):
        credits_val = None
    elif credits_val:
        credits_val = re.sub(r"\s+", "", credits_val)

    # กู้คืนและทำความสะอาดหน่วยกิตที่อาจหลุดไปปนกับ name_th
    if name_th:
        m_leak = re.search(r"\s+(\d+\s*\([\d\-xX\s]+\))$", name_th)
        if m_leak:
            if not credits_val or credits_val in ("None", "null", "") or credits_val == "3(3-0-6)":
                credits_val = re.sub(r"\s+", "", m_leak.group(1))
            name_th = name_th[:m_leak.start()].strip()

    # 3. จัดการ year & semester
    if year is not None and str(year).strip() not in ("None", "null", ""):
        try:
            year = int(year)
        except Exception:
            year = str(year).strip()
    else:
        year = None

    if sem is not None and str(sem).strip() not in ("None", "null", ""):
        try:
            sem = int(sem)
        except Exception:
            sem = str(sem).strip()
    else:
        sem = None

    # 4. จัดการ type
    if not ctype or ctype in ("None", "null", ""):
        if note in ("บังคับ", "เลือก"):
            ctype = note
        elif str(year) == "0" or (name_th and "เลือก" in name_th) or "xxx" in code_raw:
            ctype = "เลือก"
        else:
            ctype = "บังคับ"
    elif ctype not in VALID_TYPES:
        if "เลือก" in str(ctype) or str(year) == "0":
            ctype = "เลือก"
        else:
            ctype = "บังคับ"

    # 5. จัดการ category
    if code_raw.startswith(("9064", "9664")) or (name_th and "ศึกษาทั่วไป" in name_th):
        cat = "หมวดวิชาศึกษาทั่วไป"
    elif code_raw.startswith(("0601", "0602", "0603", "0604", "0606", "060")):
        cat = "หมวดวิชาเฉพาะ"
    elif "เลือกเสรี" in str(name_th or "") or code_raw.startswith("xxxx"):
        cat = "หมวดวิชาเลือกเสรี"
    elif not cat or cat not in VALID_CATEGORIES or cat in ("None", "null", ""):
        cat = "หมวดวิชาเฉพาะ"

    # 6. จัดการ prerequisite
    if isinstance(prereq, list):
        prereq = ", ".join(map(str, prereq))
    if not prereq or str(prereq).strip() in ("None", "null", "", "-"):
        prereq = "ไม่มี"
    else:
        prereq = str(prereq).strip()

    # 7. จัดการ flexible_year_semester
    if str(year) not in ("0", "None") and flex:
        flex = None

    # 8. จัดการ alt_group (กลุ่มวิชาทางเลือก/แขนง/สหกิจ รับค่าที่สกัดจากเอกสารโดยตรง)
    alt_group = c.get("alt_group")

    return {
        "code": code_raw,
        "name_th": name_th,
        "name_en": name_en,
        "credits": credits_val,
        "year": year,
        "semester": sem,
        "category": cat,
        "type": ctype,
        "prerequisite": prereq,
        "flexible_year_semester": flex,
        "note": note,
        "alt_group": alt_group,
        "pdf_pages": c.get("pdf_pages"),
        "printed_pages": c.get("printed_pages"),
    }


def merge_chunks(chunks: list[dict]) -> dict:
    """
    รวมผลจากหลาย chunk เข้าเป็นชุดเดียว พร้อมทำความสะอาดและกรองวิชาซ้ำ
    """
    seen: set[tuple] = set()
    courses: list[dict] = []
    n_dup = 0

    for ch in chunks:
        for c in ch.get("courses") or []:
            norm_c = clean_and_normalize_course(c)

            # ⚠️ ต้องรวม name_th ในกุญแจด้วย ไม่งั้นแถว "06026xxx" ที่มีสองแถว
            #    ในภาคเดียวกัน (วิชาเลือกกลุ่มฯ 1 และ 2) จะถูกลบทิ้งไปหนึ่ง
            key = (
                M.normalize(norm_c.get("code"), "strict"),
                str(norm_c.get("year")),
                str(norm_c.get("semester")),
                M.normalize(norm_c.get("name_th"), "strict"),
            )
            if key in seen:
                n_dup += 1
                continue
            seen.add(key)
            courses.append(norm_c)

    # Deduplicate redundant year=0 entries if a fixed semester entry (year > 0) exists
    fixed_codes = {
        c.get("code")
        for c in courses
        if (int(c.get("year") or 0)) > 0 and "xxx" not in str(c.get("code") or "")
    }

    final_courses = []
    for c in courses:
        code = c.get("code")
        y = int(c.get("year") or 0)
        if y == 0 and code in fixed_codes:
            n_dup += 1
            continue
        final_courses.append(c)

    if n_dup:
        print(f"      กรองวิชาซ้ำออก {n_dup} รายการ (คีย์ = รหัส+ปี+ภาค+ชื่อ)")

    return {
        "program": next((ch.get("program") for ch in chunks if ch.get("program")), None),
        "plan": next((ch.get("plan") for ch in chunks if ch.get("plan")), None),
        "courses": final_courses,
    }


# ==============================================================================
#  ส่วนที่ 7 — PIPELINE A : Tesseract baseline
# ==============================================================================


def pipeline_baseline(pages: list[bytes]) -> dict:
    """OpenCV -> Tesseract -> regex   (เส้นฐานสำหรับเปรียบเทียบ)"""
    try:
        import pytesseract
        from PIL import Image
        import numpy as np
        import cv2
    except ImportError as e:
        print(f"  ⚠ ข้าม baseline: {e}")
        return {}

    text = ""
    for i, png in enumerate(pages):
        img = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        txt = pytesseract.image_to_string(bw, lang="tha+eng", config="--psm 6")
        text += txt + "\n"
        print(f"      Tesseract หน้า {i + 1}: {len(txt):,} ตัวอักษร")
    return _rule_based_parse(text)


def _rule_based_parse(text: str) -> dict:
    """
    regex สำหรับตารางหลักสูตร

    รูปแบบที่คาดหวัง:  <รหัส 8 หลัก> <ชื่อไทย> <ชื่ออังกฤษ> <หน่วยกิต>
    ปัญหาที่ regex แก้ไม่ได้เลย:
      - ชื่อวิชาไทยและอังกฤษอยู่คนละบรรทัด (ตัดบรรทัดตามความกว้างคอลัมน์)
      - บางตารางมีคอลัมน์ "ปี/ภาค" บางตารางไม่มี
      - หัวข้อหมวดวิชาอยู่คนละแถวกับตัววิชา ต้องจำ state ไว้
    --> นี่คือจุดที่ LLM ได้เปรียบชัดเจน เพราะมันเข้าใจ "บริบท" ของทั้งหน้า
    """
    courses: list[dict] = []
    category = None

    cat_re = re.compile(r"(หมวดวิชาศึกษาทั่วไป|หมวดวิชาเฉพาะ|หมวดวิชาเลือกเสรี)")
    # รหัส 8 หลัก + ข้อความ + หน่วยกิตรูปแบบ N(N-N-N)
    row_re = re.compile(r"(\d{8})\s+(.{3,90}?)\s+(\d\([\d\s\-]+\))")

    for line in text.splitlines():
        cm = cat_re.search(line)
        if cm:
            category = cm.group(1)
            continue

        rm = row_re.search(line)
        if rm:
            raw_name = rm.group(2).strip()
            # พยายามแยกชื่อไทยกับชื่ออังกฤษ โดยหาจุดที่เปลี่ยนภาษา
            m2 = re.match(r"([^\x00-\x7F][^A-Z]*)\s*([A-Z][A-Z\s\d\-&,\.]*)?$", raw_name)
            th = (m2.group(1).strip() if m2 else raw_name)
            en = (m2.group(2).strip() if m2 and m2.group(2) else None)
            courses.append({
                "code": rm.group(1),
                "name_th": th,
                "name_en": en,
                "credits": re.sub(r"\s", "", rm.group(3)),
                "year": None, "semester": None,
                "category": category, "type": None,
                "prerequisite": "ไม่มี",
                "flexible_year_semester": None, "note": None,
            })

    print(f"      regex แกะได้ {len(courses)} วิชา")
    return {"program": None, "plan": None, "courses": courses}


# ==============================================================================
#  ส่วนที่ 8 — PIPELINE B : Typhoon-OCR -> text LLM (แบ่ง chunk)
# ==============================================================================


def pipeline_vlm(pages: list[bytes], outdir: Path) -> dict:
    """
    ขั้น 1: Typhoon-OCR อ่านทุกหน้าเป็น Markdown
    ขั้น 2: แบ่ง Markdown เป็นก้อนละ PAGES_PER_CHUNK หน้า
            ส่งเข้า text LLM ทีละก้อน แล้วรวมผล

    ทำไมต้องแบ่งก้อน?
      ถ้าส่งทั้งเล่ม (150 หน้า ~ 200,000 token) เข้าไปทีเดียว:
        - เกิน context window ของโมเดลขนาดเล็ก --> ตัดท้ายทิ้งเงียบ ๆ
        - แม้ context พอ output ก็จะยาวเกิน num_predict --> JSON ขาดกลางคัน
        - ยิ่ง context ยาว โมเดลยิ่ง "ลืมกลาง" (lost in the middle)
          ซึ่งเป็นปรากฏการณ์ที่พบในงานวิจัยหลายชิ้น

      การแบ่งก้อนแลกมาด้วย: โมเดลไม่เห็นภาพรวมทั้งเล่ม
      เช่น อาจไม่รู้ว่าวิชานี้อยู่หมวดไหน ถ้าหัวข้อหมวดอยู่คนละก้อน
      --> ทางแก้ในระบบจริงคือใส่ "overlap" ให้ก้อนซ้อนกัน 1 หน้า
          หรือส่งหัวข้อหมวดที่เจอล่าสุดไปกับก้อนถัดไป (โจทย์ท้าทายข้อ 1)
    """
    md_pages: list[str] = []
    for i, png in enumerate(pages):
        print(f"    [ขั้น 1/2] Typhoon-OCR หน้า {i + 1}/{len(pages)}")
        md = ollama_chat(MODEL_OCR,
                         [{"role": "user", "content": TYPHOON_PROMPT}],
                         images=[png], temperature=0.0)
        md_pages.append(md)

    (outdir / "intermediate_vlm.md").write_text(
        "\n\n---\n\n".join(md_pages), encoding="utf-8")
    print(f"    บันทึก Markdown กลางทาง: {outdir / 'intermediate_vlm.md'}")

    return _text_to_json_chunked(md_pages)


def parse_curriculum_text(text: str, prog_name: str = "DSBA") -> dict:
    """สกัดรายวิชาจากข้อความดิบของ PDF แผนการศึกษาด้วย Table/Text Parser ที่แม่นยำสูง รองรับทุกหลักสูตร"""
    lines = [clean_thai(line.strip()) for line in text.splitlines() if line.strip()]
    courses = []
    current_year = 0
    current_sem = 0
    current_cat = "หมวดวิชาเฉพาะ"
    in_academic_plan = False
    current_track = None
    course_index_in_track = 0

    code_pattern = r"^(\d{8}(?:\s*(?:หรือ|\n)\s*\d{8})?|\d{4}[xX]{4}|\d{5}[xX]{3}|\d{6}[xX]{2}|[xX]{8})"

    i = 0
    while i < len(lines):
        line = lines[i]

        if "3.1.4" in line or "3.3" in line or "แผนการศึกษา" in line:
            in_academic_plan = True

        m_ys = re.search(r"ป[ีิ]ท[ีิ่\s]*(\d+)\s*ภาคการศึกษาท[ีิ่\s]*(\d+)", line)
        if m_ys:
            current_year = int(m_ys.group(1))
            current_sem = int(m_ys.group(2))
            in_academic_plan = True
            current_track = None
            course_index_in_track = 0
            i += 1
            continue

        if "หมวดวิชาศึกษาทั่วไป" in line:
            current_cat = "หมวดวิชาศึกษาทั่วไป"
            current_track = None
            course_index_in_track = 0
        elif "หมวดวิชาเฉพาะ" in line:
            current_cat = "หมวดวิชาเฉพาะ"
            current_track = None
            course_index_in_track = 0
        elif "หมวดวิชาเลือกเสรี" in line or "หมวดวิชาเสรี" in line:
            current_cat = "หมวดวิชาเลือกเสรี"
            current_track = None
            course_index_in_track = 0
        elif line.startswith("รวม") or "รวมหน่วยกิต" in line:
            current_track = None
            course_index_in_track = 0

        # ตรวจจับหัวข้อกลุ่มวิชา/แขนง (Track / Alternative Group) จากเอกสารโดยตรง
        m_trk = re.search(r"^(กลุ[่]มวิชาด[้]าน|แขนงวิชา|กลุ[่]มวิชาเลือก|กลุ[่]มวิชาชีพ)\s*(.+)", line)
        if m_trk:
            current_track = m_trk.group(0).strip()
            course_index_in_track = 0
            i += 1
            continue

        # ข้ามหัวข้อหรือแถวที่ไม่ใช่รหัสวิชา
        if line.startswith(("ELECTIVE", "รหัสวิชา", "หน่วยกิต", "=== หน้า")):
            i += 1
            continue

        # Case 1: Standard single line: code + name_th + credits (DSBA, IT, AIT)
        m_course = re.match(r"^(\d{8}(?:\s*(?:หรือ|\n)\s*\d{8})?|\d{4}[xX]{4}|\d{5}[xX]{3}|\d{6}[xX]{2}|[xX]{8})\s+(.+?)\s+(\d+\s*\([\d\-xX\s]+\)(?:\s*(?:หรือ|,)\s*\d+\s*\([\d\-xX\s]+\))*)$", line)
        if m_course:
            code = m_course.group(1).replace("\n", " ").strip()
            name_th = m_course.group(2).strip()
            credits_val = m_course.group(3).strip()

            en_lines = []
            if re.search(r"\d+\s*\([\d\-xX\s]+\)", name_th):
                # The captured name_th is actually part of credits (e.g. '3(3-0-6) หรือ' in IT)
                credits_val = f"{name_th} {credits_val}".strip()
                name_th = ""
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if re.match(code_pattern, nxt) or re.search(r"ป[ีิ]ท[ีิ่\s]*\d+|หมวดวิชา|รหัสวิชา|หน่วยกิต|รวม\s+\d+|คณะเทคโนโลยี|วท\.บ", nxt):
                        i -= 1
                        break
                    m_cr_ext = re.match(r"^(?:(?:หรือ|,)\s*)?(\d+\s*\([\d\-xX\s]+\))$", nxt.strip())
                    if m_cr_ext or nxt.strip().startswith("หรือ 3("):
                        credits_val = f"{credits_val} {nxt.strip()}".strip()
                        i += 1
                    elif re.search(r"[\u0e00-\u0e7f]", nxt) and not re.search(r"^(?:หมวดวิชา|รหัสวิชา|ชื่อวิชา|หน่วยกิต|รวม|ป[ีิ]ท[ีิ่\s]*\d+|วท\.บ|คณะเทคโนโลยี|ด้วยตนเอง)", nxt):
                        name_th = (name_th + " " + nxt.strip()).strip() if name_th else nxt.strip()
                        i += 1
                    elif re.search(r"^[A-Za-z0-9\s\(\)\,\.\/\-\&]+$", nxt) and re.search(r"[A-Za-z]", nxt):
                        en_lines.append(nxt.strip())
                        i += 1
                    else:
                        break
            else:
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if re.match(code_pattern, nxt):
                        break
                    if re.search(r"ป[ีิ]ท[ีิ่\s]*\d+|หมวดวิชา|รหัสวิชา|หน่วยกิต|รวม\s+\d+|คณะเทคโนโลยี|วท\.บ", nxt):
                        break
                    if re.search(r"^[A-Za-z0-9\s\(\)\,\.\/\-\&]+$", nxt) and re.search(r"[A-Za-z]", nxt):
                        en_lines.append(nxt)
                        i += 1
                    else:
                        break

            name_en = " ".join(en_lines).strip() if en_lines else None
            y = current_year if in_academic_plan else 0
            s = current_sem if in_academic_plan else 0

            course_type = "เลือก" if ("xxx" in code.lower() or "เลือก" in name_th or (y == 0 and s == 0)) else "บังคับ"
            category = current_cat
            if code.startswith(("9064", "9664")):
                category = "หมวดวิชาศึกษาทั่วไป"
            elif code.startswith(("0601", "0602", "0603", "0604", "0606", "060")):
                category = "หมวดวิชาเฉพาะ"
            elif code.lower().startswith("xxxx") or "เสรี" in name_th:
                category = "หมวดวิชาเลือกเสรี"

            alt_group = None
            if current_track:
                alt_group = f"alt_track_y{y}s{s}_slot{course_index_in_track}"
                course_index_in_track += 1
            elif "หรือ" in code:
                alt_group = f"alt_choice_{y}_{s}_{code[:8]}"
            elif "สหกิจ" in str(name_th or "") or "coop" in str(name_en or "").lower():
                alt_group = f"alt_coop_{y}_{s}"

            c_dict = {
                "code": code,
                "name_th": name_th,
                "name_en": name_en,
                "credits": credits_val,
                "year": y,
                "semester": s,
                "category": category,
                "type": course_type,
                "prerequisite": "ไม่มี",
                "flexible_year_semester": None if (y > 0 and s > 0) else "3/1, 3/2, 4/1",
                "note": None,
                "alt_group": alt_group,
            }
            courses.append(clean_and_normalize_course(c_dict))
            continue

        # Case 2: BIT table layout (name_th on line i-1 or i-2, line i is '<code> <credits>')
        m_code_cr = re.match(r"^(\d{8}(?:\s*(?:หรือ|\n)\s*\d{8})?|\d{4}[xX]{4}|\d{5}[xX]{3}|\d{6}[xX]{2}|[xX]{8})\s+(\d+\s*\([\d\-xX\s]+\)(?:\s*(?:หรือ|,)\s*\d+\s*\([\d\-xX\s]+\))*)$", line)
        if m_code_cr and i > 0:
            name_th = ""
            for b in range(1, 4):
                if i - b >= 0:
                    prev_line = lines[i - b]
                    if prev_line.strip() in ("หรือ", "และ"):
                        continue
                    if re.search(r"[\u0e00-\u0e7f]", prev_line) and not re.search(r"^(?:หมวดวิชา(?:ศึกษาทั่วไป|เฉพาะ|เลือกเสรี|เสรี)$|รหัสวิชา|ชื่อวิชา|หน่วยกิต|รวม|ป[ีิ]ท[ีิ่\s]*\d+|มคอ\.|วท\.บ|คณะเทคโนโลยี)|บรรยาย-ปฏิบัต|ศึกษาด้วยตนเอง", prev_line):
                        name_th = prev_line.strip()
                        break
            if name_th:
                code = m_code_cr.group(1).replace("\n", " ").strip()
                credits_val = m_code_cr.group(2).strip()

                en_lines = []
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if re.match(code_pattern, nxt) or re.search(r"ป[ีิ]ท[ีิ่\s]*\d+|หมวดวิชา|รหัสวิชา|หน่วยกิต|รวม\s+\d+|คณะเทคโนโลยี|วท\.บ", nxt):
                        break
                    if re.search(r"[A-Za-z]", nxt) and not re.search(r"[\u0e00-\u0e7f]", nxt):
                        en_lines.append(nxt)
                        i += 1
                    else:
                        break
                name_en = " ".join(en_lines).strip() if en_lines else None
                y = current_year if in_academic_plan else 0
                s = current_sem if in_academic_plan else 0
                course_type = "เลือก" if ("xxx" in code.lower() or "เลือก" in name_th or (y == 0 and s == 0)) else "บังคับ"
                category = current_cat
                if code.startswith(("9064", "9664")):
                    category = "หมวดวิชาศึกษาทั่วไป"
                elif code.startswith(("0601", "0602", "0603", "0604", "0606", "060")):
                    category = "หมวดวิชาเฉพาะ"
                elif code.lower().startswith("xxxx") or "เสรี" in name_th:
                    category = "หมวดวิชาเลือกเสรี"

                alt_group = None
                if current_track:
                    alt_group = f"alt_track_y{y}s{s}_slot{course_index_in_track}"
                    course_index_in_track += 1
                elif "หรือ" in code:
                    alt_group = f"alt_choice_{y}_{s}_{code[:8]}"
                elif "สหกิจ" in str(name_th or "") or "coop" in str(name_en or "").lower():
                    alt_group = f"alt_coop_{y}_{s}"

                c_dict = {
                    "code": code,
                    "name_th": name_th,
                    "name_en": name_en,
                    "credits": credits_val,
                    "year": y,
                    "semester": s,
                    "category": category,
                    "type": course_type,
                    "prerequisite": "ไม่มี",
                    "flexible_year_semester": None if (y > 0 and s > 0) else "3/1, 3/2, 4/1",
                    "note": None,
                    "alt_group": alt_group,
                }
                courses.append(clean_and_normalize_course(c_dict))
                continue

        # Case 3: Electives: '<code> <name_th>' on line i, next lines name_en, next credits
        m_code_th = re.match(r"^(\d{8}|\d{4}[xX]{4}|\d{5}[xX]{3}|\d{6}[xX]{2}|[xX]{8})\s+(.+)$", line)
        if m_code_th:
            code = m_code_th.group(1)
            rem = m_code_th.group(2).strip()
            name_th = ""
            name_en = None
            credits_val = "3(3-0-6)"
            matched_case3 = False

            if rem in ("หรือ", "และ"):
                th_lines = []
                cr_before = None
                for b in range(1, 6):
                    if i - b >= 0:
                        pl = lines[i - b]
                        if re.match(code_pattern, pl):
                            break
                        m_cr_pre = re.match(r"^(\d+\s*\([\d\-xX\s]+\))$", pl.strip())
                        if m_cr_pre and not cr_before:
                            cr_before = m_cr_pre.group(1)
                        elif re.search(r"[\u0e00-\u0e7f]", pl) and not re.search(r"^(?:หมวดวิชา|รหัสวิชา|ชื่อวิชา|หน่วยกิต|รวม|ป[ีิ]ท[ีิ่\s]*\d+|วท\.บ|คณะเทคโนโลยี|ด้วยตนเอง)", pl):
                            th_lines.insert(0, pl.strip())
                name_th = " ".join(th_lines)

                en_lines = []
                cr_after = None
                nxt_idx = i + 1
                while nxt_idx < len(lines):
                    nxt = lines[nxt_idx]
                    if re.match(code_pattern, nxt) or re.search(r"วิชาเลือกเสรี|รหัสวิชา|หมวดวิชา|ป[ีิ]ท[ีิ่\s]*\d+", nxt):
                        break
                    m_cr_post = re.match(r"^(\d+\s*\([\d\-xX\s]+\))$", nxt.strip())
                    if m_cr_post and not cr_after:
                        cr_after = m_cr_post.group(1)
                    elif re.search(r"^[A-Za-z0-9\s\(\)\,\.\/\-\&]+$", nxt) and re.search(r"[A-Za-z]", nxt):
                        en_lines.append(nxt.strip())
                    nxt_idx += 1
                name_en = " ".join(en_lines) if en_lines else None
                credits_val = f"{cr_before} {rem} {cr_after}".strip() if cr_before and cr_after else "3(3-0-6)"
                i = nxt_idx - 1
                matched_case3 = bool(name_th)
            elif not re.search(r"\d+\s*\([\d\-xX\s]+\)$", rem) and re.search(r"[\u0e00-\u0e7f]", rem):
                name_th = rem
                en_lines = []
                credits_val = "3(3-0-6)"
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    m_cr = re.match(r"^(\d+\s*\([\d\-xX\s]+\)(?:\s*(?:หรือ|,)\s*\d+\s*\([\d\-xX\s]+\))*)$", nxt)
                    if m_cr:
                        credits_val = m_cr.group(1).strip()
                        i += 1
                        break
                    if re.match(code_pattern, nxt) or re.search(r"ป[ีิ]ท[ีิ่\s]*\d+|หมวดวิชา|รหัสวิชา|หน่วยกิต|รวม\s+\d+|คณะเทคโนโลยี|วท\.บ", nxt):
                        break
                    if re.search(r"^[A-Z0-9\s\(\)\,\.\/\-\&]+$", nxt) and re.search(r"[A-Za-z]", nxt):
                        en_lines.append(nxt)
                        i += 1
                    else:
                        break
                name_en = " ".join(en_lines).strip() if en_lines else None
                matched_case3 = True

            if matched_case3:
                y = current_year if in_academic_plan else 0
                s = current_sem if in_academic_plan else 0
                course_type = "เลือก" if ("xxx" in code.lower() or "เลือก" in name_th or (y == 0 and s == 0)) else "บังคับ"
                category = current_cat
                if code.startswith(("9064", "9664")):
                    category = "หมวดวิชาศึกษาทั่วไป"
                elif code.startswith(("0601", "0602", "0603", "0604", "0606", "060")):
                    category = "หมวดวิชาเฉพาะ"
                elif code.lower().startswith("xxxx") or "เสรี" in name_th:
                    category = "หมวดวิชาเลือกเสรี"

                alt_group = None
                if current_track:
                    alt_group = f"alt_track_y{y}s{s}_slot{course_index_in_track}"
                    course_index_in_track += 1
                elif "หรือ" in code:
                    alt_group = f"alt_choice_{y}_{s}_{code[:8]}"
                elif "สหกิจ" in str(name_th or "") or "coop" in str(name_en or "").lower():
                    alt_group = f"alt_coop_{y}_{s}"

                c_dict = {
                    "code": code,
                    "name_th": name_th,
                    "name_en": name_en,
                    "credits": credits_val,
                    "year": y,
                    "semester": s,
                    "category": category,
                    "type": course_type,
                    "prerequisite": "ไม่มี",
                    "flexible_year_semester": None if (y > 0 and s > 0) else "3/1, 3/2, 4/1",
                    "note": None,
                    "alt_group": alt_group,
                }
                courses.append(clean_and_normalize_course(c_dict))
                continue

        # Case 4: Code alone on line (IT format): <code>, next line is name_th, etc.
        m_code_only = re.match(r"^(\d{8}(?:\s*(?:หรือ|\n)\s*\d{8})?|\d{4}[xX]{4}|\d{5}[xX]{3}|\d{6}[xX]{2}|[xX]{8})$", line)
        if m_code_only:
            code = m_code_only.group(1).replace("\n", " ").strip()
            name_th = ""
            en_lines = []
            credits_val = "3(3-0-6)"
            i += 1
            while i < len(lines):
                nxt = lines[i]
                m_cr = re.match(r"^(\d+\s*\([\d\-xX\s]+\)(?:\s*(?:หรือ|,)\s*\d+\s*\([\d\-xX\s]+\))*)$", nxt)
                if m_cr:
                    credits_val = m_cr.group(1).strip()
                    i += 1
                    break
                if re.match(code_pattern, nxt) or re.search(r"ปีท\s*ี่\s*\d+|หมวดวิชา|รหัสวิชา|หน่วยกิต|รวม\s+\d+|คณะเทคโนโลยี|วท\.บ", nxt):
                    break
                if re.search(r"[\u0e00-\u0e7f]", nxt):
                    name_th = (name_th + " " + nxt).strip() if name_th else nxt
                    i += 1
                elif re.search(r"[A-Za-z]", nxt):
                    en_lines.append(nxt)
                    i += 1
                else:
                    i += 1
            if name_th:
                name_en = " ".join(en_lines).strip() if en_lines else None
                y = current_year if in_academic_plan else 0
                s = current_sem if in_academic_plan else 0
                course_type = "เลือก" if ("xxx" in code or "เลือก" in name_th or (y == 0 and s == 0)) else "บังคับ"
                category = current_cat
                if code.startswith(("9064", "9664")):
                    category = "หมวดวิชาศึกษาทั่วไป"
                elif code.startswith(("0601", "0602", "0603", "0604", "0606", "060")):
                    category = "หมวดวิชาเฉพาะ"
                elif code.startswith("xxxx") or "เสรี" in name_th:
                    category = "หมวดวิชาเลือกเสรี"

                alt_group = None
                if current_track:
                    alt_group = f"alt_track_y{y}s{s}_slot{course_index_in_track}"
                    course_index_in_track += 1
                elif "หรือ" in code:
                    alt_group = f"alt_choice_{y}_{s}_{code[:8]}"
                elif "สหกิจ" in str(name_th or "") or "coop" in str(name_en or "").lower():
                    alt_group = f"alt_coop_{y}_{s}"

                c_dict = {
                    "code": code,
                    "name_th": name_th,
                    "name_en": name_en,
                    "credits": credits_val,
                    "year": y,
                    "semester": s,
                    "category": category,
                    "type": course_type,
                    "prerequisite": "ไม่มี",
                    "flexible_year_semester": None if (y > 0 and s > 0) else "3/1, 3/2, 4/1",
                    "note": None,
                    "alt_group": alt_group,
                }
                courses.append(clean_and_normalize_course(c_dict))
                continue

        i += 1

    # รวมวิชาทางเลือกสหกิจศึกษาในภาคการศึกษาเดียวกัน
    merged_courses = []
    idx = 0
    while idx < len(courses):
        c = courses[idx]
        if idx + 1 < len(courses):
            c_next = courses[idx + 1]
            if (c.get("alt_group") and c["alt_group"].startswith("alt_coop_") and
                c["alt_group"] == c_next.get("alt_group") and
                c["year"] == c_next["year"] and c["semester"] == c_next["semester"] and
                c["year"] > 0):
                merged_c = dict(c)
                merged_c["code"] = f"{c['code']} หรือ {c_next['code']}"
                merged_c["name_th"] = f"{c['name_th']}\nหรือ\n{c_next['name_th']}"
                merged_c["name_en"] = f"{c.get('name_en') or ''}\n{c_next.get('name_en') or ''}".strip() or None
                merged_courses.append(merged_c)
                idx += 2
                continue
        merged_courses.append(c)
        idx += 1
    courses = merged_courses

    plan = "coop" if prog_name != "AIT" else None
    return {"program": prog_name, "plan": plan, "courses": courses}


def _text_to_json_chunked(md_pages: list[str]) -> dict:
    """แบ่งหน้าเป็นก้อนแบบมี overlap แล้วเรียก text LLM ทีละก้อน พร้อมส่งบริบทหมวดวิชา"""
    # Clean whitespace lines
    cleaned_pages = [
        "\n".join([line.rstrip() for line in page.splitlines() if line.strip()])
        for page in md_pages
    ]

    chunks: list[dict] = []
    step = max(1, PAGES_PER_CHUNK - 1) if PAGES_PER_CHUNK > 1 else 1
    page_indices = []
    i = 0
    while i < len(cleaned_pages):
        end = min(i + PAGES_PER_CHUNK, len(cleaned_pages))
        page_indices.append((i, end))
        if end == len(cleaned_pages):
            break
        i += step

    n_chunks = len(page_indices)
    last_known_category = None

    for ci, (start_idx, end_idx) in enumerate(page_indices):
        part = cleaned_pages[start_idx:end_idx]
        print(f"    [ขั้น 2/2] จัด JSON ก้อนที่ {ci + 1}/{n_chunks} "
              f"(หน้า {start_idx + 1}-{end_idx} จาก {len(cleaned_pages)} หน้า)")
        try:
            raw = ollama_chat(
                MODEL_TEXT,
                [{"role": "system", "content": SYSTEM_PROMPT},
                 {"role": "user", "content": EXTRACT_PROMPT.format(
                     document_text="\n\n".join(part))}],
                fmt=COURSE_SCHEMA,
            )
            d = parse_json(raw)
            if isinstance(d, list):
                d = {"courses": d}
            c_list = d.get("courses") or []
            print(f"      ได้ {len(c_list)} วิชา")
            if c_list:
                for c in reversed(c_list):
                    if c.get("category") and c["category"] in VALID_CATEGORIES:
                        last_known_category = c["category"]
                        break
            chunks.append(d)
        except Exception as e:
            print(f"      ⚠ ก้อนที่ {ci + 1} ใช้ Parser สกัดตรง: {e}")
            parsed = parse_curriculum_text("\n\n".join(part))
            if parsed.get("courses"):
                chunks.append(parsed)

    if not chunks:
        # Fallback to direct parse
        return parse_curriculum_text("\n\n".join(cleaned_pages))

    return merge_chunks(chunks)


def pipeline_text(pdf_path: str, page_spec: str | None, prog_name: str = "DSBA") -> dict:
    """
    ⭐ pipeline พิเศษของกลุ่ม B: ข้าม OCR ไปเลย
    """
    print("    ดึงข้อความจาก PDF โดยตรง (ไม่ผ่าน OCR)...")
    text = extract_pdf_text(pdf_path, page_spec)

    pages_text = re.split(r"\n=== หน้า \d+ ===\n", text)
    pages_text = [p for p in pages_text if p.strip()]
    n_all = len(re.findall(r"=== หน้า \d+ ===", text))
    n_empty = n_all - len(pages_text)

    print(f"    ได้ข้อความ {len(text):,} ตัวอักษร จาก {len(pages_text)}/{n_all} หน้า")

    if not pages_text:
        print("    ⚠ ไม่มีหน้าไหนดึงข้อความได้เลย — เล่มนี้เป็น PDF สแกน")
        print("      ให้ใช้ --pipeline vlm แทน")
        return {}

    if n_empty:
        print(f"    ⚠ มี {n_empty} หน้าที่ดึงข้อความไม่ได้ (น่าจะเป็นหน้าสแกน)")
        print("      วิชาในหน้าเหล่านั้นจะหายไป --> Recall จะต่ำกว่าความจริง")
        print("      ถ้าเล่มมีหน้าสแกนปน ให้ใช้ --pipeline vlm แทน")

    # ใช้ Hybrid Parser ดึงโครงสร้างตารางและรายวิชาโดยตรงอย่างรวดเร็วและแม่นยำสูง
    parsed = parse_curriculum_text(text, prog_name)
    if parsed.get("courses"):
        return merge_chunks([parsed])

    return _text_to_json_chunked(pages_text)



# ==============================================================================
#  ส่วนที่ 10 — ตรวจความสอดคล้องภายใน
# ==============================================================================
#
#  กลุ่ม A ใช้ GPA เป็นตัวตรวจ  แต่หลักสูตรไม่มี GPA
#  เราจึงใช้กฎเชิงโครงสร้าง 5 ข้อแทน — ทุกข้อตรวจได้โดยไม่ต้องมีเฉลย
# ==============================================================================


def _valid_code(code: Any) -> bool:
    """
    ตรวจรูปแบบรหัสวิชา รองรับทั้งรหัสเดี่ยวและรหัสแบบ "เลือกอย่างใดอย่างหนึ่ง"

        "06026240"                -> True
        "06026xxx"                -> True   (ช่องวิชาเลือก)
        "06026259 หรือ 06026260"  -> True   (สหกิจในประเทศ / ต่างประเทศ)
        "หมายเหตุ: คอลัมน์..."     -> False  (แถวขยะจาก Excel)
    """
    raw = str(code or "")
    parts = [x for x in re.split(r"หรือ|/", raw) if x.strip()]
    if not parts:
        return False
    return all(re.fullmatch(r"[0-9x]{8}", M.normalize(x, "strict")) for x in parts)


def verify_internal(data: dict) -> dict:
    """ตรวจ 5 กฎ — เป็นสิ่งที่ทำได้ในระบบจริงที่ไม่มีเฉลย"""
    issues: list[str] = []
    courses = data.get("courses") or []
    # ชุดรหัสทั้งหมด — แตกรหัสแบบ "A หรือ B" ออกเป็นรายตัว
    # เพื่อให้การตรวจ prerequisite (กฎ 5) หาเจอ
    codes: set[str] = set()
    for c in courses:
        for part in re.split(r"หรือ|/", str(c.get("code") or "")):
            n = M.normalize(part, "strict")
            if n:
                codes.add(n)

    # ⚠️ กุญแจนับซ้ำต้องรวม name_th ด้วย ให้ตรงกับ merge_chunks
    #    ถ้าใช้แค่ (รหัส, ปี, ภาค) แถว "06026xxx" ที่มีสองแถวในภาคเดียวกัน
    #    (วิชาเลือกกลุ่มฯ 1 และ 2) จะถูกนับว่าซ้ำทั้งที่เป็นข้อมูลจริง
    dup = Counter((M.normalize(c.get("code"), "strict"),
                   str(c.get("year")), str(c.get("semester")),
                   M.normalize(c.get("name_th"), "strict")) for c in courses)
    credits_by_term: dict[str, int] = defaultdict(int)
    term_group_credits: dict[str, dict[str, int]] = defaultdict(dict)
    has_block_course: set[str] = set()   # ภาคที่มีวิชาก้อนใหญ่ เช่น สหกิจศึกษา

    for c in courses:
        code = c.get("code")

        # --- กฎ 1: รูปแบบรหัสวิชา ---
        # รูปแบบที่ถูกต้องมี 2 แบบ:
        #   ก) รหัสเดี่ยว 8 ตัว เป็นเลขหรือ x ("06026240", "06026xxx", "xxxxxxxx")
        #   ข) ⭐ รหัสแบบ "เลือกอย่างใดอย่างหนึ่ง" คั่นด้วยคำว่า "หรือ"
        #      เช่น "06026259 หรือ 06026260" (สหกิจศึกษาในประเทศ / ต่างประเทศ)
        #      แบบนี้พบจริงในหลักสูตร DSBA แผนสหกิจ ห้ามนับเป็นข้อผิดพลาด
        #
        # ⚠️ ตอนออกแบบกฎนี้ครั้งแรก เรารองรับแค่แบบ ก) แล้วพบว่ามันแจ้งเตือน
        #    ground truth ของจริงทันที  ซึ่งละเมิดหลักการที่เราวางไว้เองว่า
        #    "ถ้ากฎแจ้งเตือน ต้องแปลว่าผิดจริงแน่นอน"
        #    บทเรียน: ต้องทดสอบกฎกับ ground truth ก่อนเสมอ ถ้ากฎจับเฉลยผิด
        #             แปลว่ากฎผิด ไม่ใช่เฉลยผิด
        if not _valid_code(code):
            issues.append(f"รหัสวิชาผิดรูปแบบ: {code!r}")

        # --- กฎ 2: รูปแบบหน่วยกิต ---
        cr = c.get("credits") or ""
        if cr and not CREDIT_RE.match(cr.replace(" ", "")) and "หรือ" not in cr:
            issues.append(f"หน่วยกิตผิดรูปแบบ: {code} -> {cr!r}")

        # --- กฎ 3: ค่าที่เป็นหมวดหมู่ ต้องอยู่ในชุดที่กำหนด ---
        if c.get("category") and c["category"] not in VALID_CATEGORIES:
            issues.append(f"category ไม่ถูกต้อง: {code} -> {c['category']!r}")
        if c.get("type") and c["type"] not in VALID_TYPES:
            issues.append(f"type ไม่ถูกต้อง: {code} -> {c['type']!r}")

        # --- กฎ 4: ความสอดคล้องของ year=0 กับ flexible_year_semester ---
        y, s = str(c.get("year")), str(c.get("semester"))
        if y == "0" and s == "0" and not c.get("flexible_year_semester"):
            issues.append(f"{code}: ปี/ภาค = 0 แต่ไม่ได้ระบุ flexible_year_semester")
        if y not in ("0", "None") and c.get("flexible_year_semester"):
            issues.append(f"{code}: ระบุปีชัดเจนแล้ว ไม่ควรมี flexible_year_semester")

        # --- กฎ 5: prerequisite ต้องอ้างถึงวิชาที่มีอยู่จริง ---
        # เรียกว่า referential integrity — หลักการเดียวกับ foreign key ในฐานข้อมูล
        pre = (c.get("prerequisite") or "").strip()
        if pre and pre != "ไม่มี":
            for pc in re.findall(r"\d{8}", pre):
                if pc not in codes:
                    issues.append(f"{code}: prerequisite {pc} ไม่มีอยู่ในรายการวิชา "
                                  f"--> อาจอ่านรหัสผิด หรืออ่านตกวิชานั้น")

        # --- สะสมหน่วยกิตรายภาค (นับ alt_group เพียงครั้งเดียว) ---
        m = re.match(r"(\d+)\(", cr)
        if m and y not in ("0", "None") and s not in ("0", "None"):
            n_credit = int(m.group(1))
            term = f"{y}/{s}"
            grp = c.get("alt_group") or f"single_{code}_{y}_{s}"
            term_group_credits[term][grp] = max(term_group_credits[term].get(grp, 0), n_credit)
            if n_credit >= BLOCK_COURSE_CREDITS:
                has_block_course.add(term)

    for term, grps in term_group_credits.items():
        credits_by_term[term] = sum(grps.values())

    # --- ตรวจว่าจำนวนหน่วยกิตต่อภาคสมเหตุสมผลไหม ---
    # ระเบียบทั่วไปกำหนดให้ลงได้ 9-22 หน่วยกิตต่อภาค
    # ถ้าน้อยกว่ามาก แปลว่า "อ่านตกวิชา" ในภาคนั้น
    #
    # ⚠️ ข้อยกเว้นสำคัญ: ภาคที่ลงสหกิจศึกษา
    #    แผนสหกิจของ DSBA กำหนดให้ปี 4 ภาค 2 ลงสหกิจศึกษาเพียงวิชาเดียว
    #    6 หน่วยกิต (0-35-0) คือไปทำงานเต็มเวลาทั้งภาค
    #    ถ้าไม่ยกเว้น กฎนี้จะแจ้งเตือน ground truth ของจริงทันที
    for term, tot in sorted(credits_by_term.items()):
        if tot < 9 and term not in has_block_course:
            issues.append(f"ภาค {term} มีแค่ {tot} หน่วยกิต — น่าจะอ่านตกวิชา")
        elif tot > 25:
            issues.append(f"ภาค {term} มีถึง {tot} หน่วยกิต — น่าจะมีวิชาซ้ำ")

    return {
        "ok": len(issues) == 0,
        "n_courses": len(courses),
        "n_duplicate_keys": sum(1 for v in dup.values() if v > 1),
        "credits_by_term": dict(sorted(credits_by_term.items())),
        "total_credits_fixed_terms": sum(credits_by_term.values()),
        "issues": issues,
    }


# ==============================================================================
#  ส่วนที่ 11 — ประเมินผลเทียบ GROUND TRUTH
# ==============================================================================


def clean_gt(gt: dict) -> list[dict]:
    """
    ทำความสะอาด ground truth ก่อนใช้งาน
     ก่อนใช้ ground truth ต้อง "ตรวจ ground truth" เสียก่อน
             และเกณฑ์การกรองต้องแคบที่สุดเท่าที่จะทำได้
    """
    kept, dropped = [], []
    for c in gt.get("courses") or []:
        # เกณฑ์เดียว: ต้องมีชื่อวิชาภาษาไทย  ถ้าไม่มี = ไม่ใช่แถวรายวิชา
        if c.get("name_th"):
            kept.append(c)
        else:
            dropped.append(str(c.get("code"))[:40])
    if dropped:
        print(f"  (กรองแถวที่ไม่ใช่รายวิชาออกจาก ground truth {len(dropped)} แถว)")
    return kept


def key_strict(c: dict) -> str:
    """
    กุญแจเข้ม: รหัส + ปี + ภาค + ชื่อไทย

    ทำไมต้องมีชื่อด้วย? เพราะรหัส placeholder "06026xxx" ปรากฏ 2 แถว
    ในภาคเดียวกัน (วิชาเลือกกลุ่มวิทยาการข้อมูล 1 และ 2)
    ถ้าใช้แค่รหัส+ปี+ภาค ทั้งสองแถวจะชนกัน --> จับคู่ผิดตัว
    """
    return "|".join([
        M.normalize(c.get("code"), "strict"),
        M.normalize(c.get("year"), "strict"),
        M.normalize(c.get("semester"), "strict"),
        M.normalize(c.get("name_th"), "strict"),
    ])


def key_loose(c: dict) -> str:
    """
    กุญแจหลวม: รหัส + ปี + ภาค (ไม่สนชื่อ)

    ใช้ในรอบที่สอง เพื่อเก็บตกกรณีที่โมเดลอ่านชื่อผิดไปนิดหน่อย
    ถ้าไม่มีรอบนี้ วิชาที่อ่านชื่อผิด 1 ตัวอักษรจะถูกนับเป็น
    "ตกแถว 1 + แต่งเกิน 1" ทั้งที่โมเดลอ่านเจอจริง
    --> ทำให้ recall ดูแย่เกินความเป็นจริง
    """
    return "|".join([
        M.normalize(c.get("code"), "strict"),
        M.normalize(c.get("year"), "strict"),
        M.normalize(c.get("semester"), "strict"),
    ])


def evaluate(pred: dict, gt: dict) -> tuple[dict, dict]:
    S = M.FieldStat
    stats: dict[str, M.FieldStat] = {
        "code":      S("รหัสวิชา"),
        "name_th":   S("ชื่อวิชา (ไทย) ⭐"),
        "name_en":   S("ชื่อวิชา (อังกฤษ) ⭐"),
        "credits":   S("หน่วยกิต"),
        "year_sem":  S("ปี/ภาค"),
        "category":  S("หมวดวิชา"),
        "ctype":     S("บังคับ/เลือก"),
        "prereq":    S("วิชาบังคับก่อน"),
        "flexible":  S("ปี/ภาคยืดหยุ่น"),
    }

    g_courses = clean_gt(gt)
    p_courses = [clean_and_normalize_course(c) for c in (pred.get("courses") or [])]

    # จับคู่สองรอบ: เข้มก่อน (รวมชื่อ) แล้วผ่อน (เฉพาะรหัส+ปี+ภาค)
    align = M.align_multipass(g_courses, p_courses, [key_strict, key_loose])

    for g, p in align.matched:
        k = f"{g.get('code')}"

        # --- รหัสวิชา: ไม่วัด WER (เป็นตัวเลข ไม่มีคำ) ---
        stats["code"].add(g.get("code"), p.get("code"), k, track_wer=False)

        # ⭐ ชื่อวิชา: กลุ่ม B วัด WER ได้ เพราะ GT คงช่องว่างไว้
        #    - ภาษาไทย ใช้ pythainlp/newmm ตัดคำ
        #    - ภาษาอังกฤษ ตัดด้วยช่องว่าง
        #    ⚠️ name_en ใน GT มี \n ฝังอยู่ (ชื่อยาวถูกตัดบรรทัดใน PDF)
        #       normalize ระดับ basic ขึ้นไปจะยุบ \n เป็นช่องว่างให้อัตโนมัติ
        stats["name_th"].add(g.get("name_th"), p.get("name_th"), k, track_wer=True)
        stats["name_en"].add(g.get("name_en"), p.get("name_en"), k, track_wer=True)

        stats["credits"].add(g.get("credits"), p.get("credits"), k, track_wer=False)
        stats["year_sem"].add(f"{g.get('year')}/{g.get('semester')}",
                              f"{p.get('year')}/{p.get('semester')}",
                              k, track_wer=False)
        stats["category"].add(g.get("category"), p.get("category"), k, track_wer=False)
        stats["ctype"].add(g.get("type"), p.get("type"), k, track_wer=False)
        stats["prereq"].add(g.get("prerequisite"), p.get("prerequisite"),
                            k, track_wer=False)
        stats["flexible"].add(g.get("flexible_year_semester"),
                              p.get("flexible_year_semester"), k, track_wer=False)

    # --- วิชาที่โมเดลอ่านตก: นับเป็น deletion เต็มจำนวน ---
    # ถ้าไม่นับ โมเดลที่อ่านแค่ 10 วิชาจาก 91 วิชาจะได้ CER ต่ำเตี้ย
    # ทั้งที่ใช้งานจริงไม่ได้เลย
    for g in align.missed:
        k = f"{g.get('code')} [ตกแถว]"
        stats["code"].add(g.get("code"), "", k, track_wer=False)
        stats["name_th"].add(g.get("name_th"), "", k, track_wer=True)
        stats["name_en"].add(g.get("name_en"), "", k, track_wer=True)
        stats["credits"].add(g.get("credits"), "", k, track_wer=False)
        stats["year_sem"].add(f"{g.get('year')}/{g.get('semester')}", "",
                              k, track_wer=False)
        stats["category"].add(g.get("category"), "", k, track_wer=False)
        stats["ctype"].add(g.get("type"), "", k, track_wer=False)

    align_summary = {
        "matched": len(align.matched),
        "missed": len(align.missed),
        "spurious": len(align.spurious),
        "precision": round(align.precision, 4),
        "recall": round(align.recall, 4),
        "f1": round(align.f1, 4),
        "gt_total": len(g_courses),
        "pred_total": len(p_courses),
        "missed_codes": [g.get("code") for g in align.missed][:20],
        "spurious_codes": [p.get("code") for p in align.spurious][:20],
    }
    return stats, align_summary


# ==============================================================================
#  ส่วนที่ 12 — MAIN
# ==============================================================================


def run_pipeline(name: str, pages: list[bytes], outdir: Path,
                 pdf_path: str | None, page_spec: str | None, prog_name: str = "DSBA") -> dict | None:
    print(f"\n{'─' * 70}")
    print(f"  PIPELINE: {name}")
    print(f"{'─' * 70}")
    t0 = time.time()
    try:
        if name == "baseline":
            data = pipeline_baseline(pages)
        elif name == "text":
            if not pdf_path:
                print("  ⚠ pipeline 'text' ใช้ได้กับไฟล์ PDF เท่านั้น")
                return None
            data = pipeline_text(pdf_path, page_spec, prog_name=prog_name)
        elif name == "vlm":
            data = pipeline_vlm(pages, outdir)
        else:
            raise ValueError(name)
    except Exception as e:
        print(f"  ❌ {name} ล้มเหลว: {e}")
        return None

    if not data or not data.get("courses"):
        print(f"  ⚠ {name} ไม่ได้ผลลัพธ์")
        return None

    data["_meta"] = {
        "pipeline": name,
        "elapsed_sec": round(time.time() - t0, 1),
        "models": {"ocr": MODEL_OCR, "text": MODEL_TEXT},
        "dpi": DPI, "pages_per_chunk": PAGES_PER_CHUNK,
    }
    # เสริมข้อมูลวิชาบังคับก่อน (prerequisite), ชื่ออังกฤษ และเลขหน้าอ้างอิงจากเล่ม PDF
    if pdf_path and data.get("courses"):
        prereqs, en_names, course_pages, th_names, credits_map = extract_pdf_course_descriptions(pdf_path)
        enriched_pre = 0
        enriched_en = 0
        enriched_pages = 0
        for c in data.get("courses", []):
            code = c.get("code")
            if code in prereqs and (not c.get("prerequisite") or c.get("prerequisite") == "ไม่มี"):
                c["prerequisite"] = prereqs[code]
                enriched_pre += 1
            elif code and "หรือ" in code:
                parts = [x.strip() for x in re.split(r"หรือ|/", code) if x.strip()]
                sub_pre = [prereqs[p] for p in parts if p in prereqs and prereqs[p] != "ไม่มี"]
                if sub_pre and (not c.get("prerequisite") or c.get("prerequisite") == "ไม่มี"):
                    c["prerequisite"] = " หรือ ".join(sub_pre)
                    enriched_pre += 1
            if code in en_names and not c.get("name_en"):
                c["name_en"] = en_names[code]
                enriched_en += 1
            if code in course_pages:
                pdf_list = sorted(course_pages[code])
                printed_list = [max(1, p - 5) for p in pdf_list]
                c["pdf_pages"] = ";".join(map(str, pdf_list))
                c["printed_pages"] = ";".join(map(str, printed_list))
                enriched_pages += 1
        if enriched_pre or enriched_en or enriched_pages:
            print(f"  ✓ เสริมข้อมูลจากเล่ม PDF: prerequisite {enriched_pre} วิชา, name_en {enriched_en} วิชา, เลขหน้าอ้างอิง {enriched_pages} วิชา")

    path = outdir / f"pred_{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ บันทึก {path}  ({len(data['courses'])} วิชา, "
          f"{data['_meta']['elapsed_sec']} วิ)")
    return data


def enrich_all_curricula_pages() -> None:
    """
    สกัดเลขหน้า (printed_pages, pdf_pages) จากเล่ม PDF ใน data/input/
    และอัปเดตเข้าสู่ไฟล์ pred_text.json ทุกหลักสูตร (DSBA, IT, BIT, AIT)
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    pdf_mapping = {
        "DSBA": repo_root / "data" / "input" / "fulldoc_dsba.pdf",
        "IT": repo_root / "data" / "input" / "fulldoc_it.pdf",
        "BIT": repo_root / "data" / "input" / "fulldoc_BIT.pdf",
        "AIT": repo_root / "data" / "input" / "fulldoc_AIT.pdf",
    }
    target_dirs = [
        repo_root / "lab7_final" / "output",
        repo_root / "work" / "lab7b_run",
    ]

    print("\n" + "=" * 70)
    print("  Lab 7B — สกัดเลขหน้าอ้างอิงจากเล่มหลักสูตร PDF เข้าสู่ pred_text.json")
    print("=" * 70)

    total_updated = 0
    for prog, pdf_path in pdf_mapping.items():
        if not pdf_path.exists():
            print(f"  ⚠ ไม่พบไฟล์ PDF ของ {prog}: {pdf_path}")
            continue

        print(f"\n[+] กำลังสกัดเลขหน้าจาก {pdf_path.name} ({prog})...")
        prereqs, en_names, course_pages, th_names, credits_map = extract_pdf_course_descriptions(str(pdf_path))
        print(f"    ✓ พบรายวิชาที่มีเลขหน้าในเล่ม: {len(course_pages)} วิชา")

        for base_dir in target_dirs:
            pred_file = base_dir / prog / "pred_text.json"
            if not pred_file.exists():
                continue

            try:
                data = json.loads(pred_file.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"    ⚠ อ่านไฟล์ {pred_file} ไม่สำเร็จ: {e}")
                continue

            courses = data.get("courses", [])
            enriched = 0
            for c in courses:
                code = c.get("code")
                if code in course_pages:
                    pdf_list = sorted(course_pages[code])
                    printed_list = [max(1, p - 5) for p in pdf_list]
                    c["pdf_pages"] = ";".join(map(str, pdf_list))
                    c["printed_pages"] = ";".join(map(str, printed_list))
                    enriched += 1
                if code in en_names and not c.get("name_en"):
                    c["name_en"] = en_names[code]
                if code in prereqs and (not c.get("prerequisite") or c.get("prerequisite") == "ไม่มี"):
                    c["prerequisite"] = prereqs[code]

            pred_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"    ✓ อัปเดต {pred_file.relative_to(repo_root)}: เพิ่มเลขหน้า {enriched}/{len(courses)} วิชา")
            total_updated += enriched

    # อัปเดตเลขหน้าเข้าสู่ฐานข้อมูล SQLite (curriculum.db) โดยตรง
    print("\n[+] กำลังบันทึกเลขหน้าเข้าฐานข้อมูล SQLite (curriculum.db)...")
    db_paths = [
        repo_root / "work" / "lab8b_run" / "curriculum.db",
        repo_root / "work" / "lab8b_run" / "combined" / "curriculum.db",
        repo_root / "work" / "lab8b_run" / "DSBA" / "curriculum.db",
        repo_root / "work" / "lab8b_run" / "IT" / "curriculum.db",
        repo_root / "work" / "lab8b_run" / "BIT" / "curriculum.db",
        repo_root / "work" / "lab8b_run" / "AIT" / "curriculum.db",
    ]
    for db_path in db_paths:
        if not db_path.exists():
            continue
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cols = [col[1] for col in cur.execute("PRAGMA table_info(course)").fetchall()]
            if "printed_pages" not in cols:
                cur.execute("ALTER TABLE course ADD COLUMN printed_pages TEXT")
            if "pdf_pages" not in cols:
                cur.execute("ALTER TABLE course ADD COLUMN pdf_pages TEXT")

            # รวบรวมข้อมูลเลขหน้าจาก pred_text.json ที่เพิ่งอัปเดต
            for prog in pdf_mapping.keys():
                pred_file = repo_root / "lab7_final" / "output" / prog / "pred_text.json"
                if pred_file.exists():
                    p_data = json.loads(pred_file.read_text(encoding="utf-8"))
                    for c in p_data.get("courses", []):
                        if c.get("code") and c.get("printed_pages"):
                            cur.execute(
                                "UPDATE course SET printed_pages = ?, pdf_pages = ? WHERE code = ?",
                                (c["printed_pages"], c.get("pdf_pages"), c["code"])
                            )
            conn.commit()
            updated_count = cur.execute(
                "SELECT COUNT(*) FROM course WHERE printed_pages IS NOT NULL AND printed_pages != ''"
            ).fetchone()[0]
            conn.close()
            print(f"    ✓ อัปเดต {db_path.relative_to(repo_root)}: มีเลขหน้ารองรับแล้ว {updated_count} วิชา")
        except Exception as e:
            print(f"    ⚠ อัปเดตฐานข้อมูล {db_path} ไม่สำเร็จ: {e}")

    print("\n" + "=" * 70)
    print(f"  [OK] เสร็จสิ้นการสกัดเลขหน้า Lab 7B เรียบร้อย (รวม {total_updated} รายการ)")
    print("=" * 70)


# ==============================================================================
#  ส่วนที่ 11 — สกัดข้อบังคับการศึกษา (ภาคผนวก ก) จากภาพสแกน PDF ด้วย Typhoon-OCR + Qwen
# ==============================================================================


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


TYPHOON_REGULATION_PROMPT = """Extract all text from the image.

Instructions:
- Only return the clean Markdown.
- Do not include any explanation or extra text.
- You must include all information on the page.

Formatting Rules:
- Tables: Render tables using <table>...</table> in clean HTML format.
- Equations: Render equations using LaTeX syntax with inline ($...$) and block ($$...$$).
- Images/Charts/Diagrams: Wrap any clearly defined visual areas (e.g. charts, diagrams, pictures) in:
  <!-- image -->
  [image description]
  <!-- /image -->
- Page Numbers: Wrap page numbers in <page_number>...</page_number> (e.g., <page_number>14</page_number>).
- Checkboxes: Use ☐ for unchecked and ☑ for checked boxes.
"""

REGULATION_CATEGORIES = [
    {
        "category": "เกณฑ์การลงทะเบียน",
        "description": "เกณฑ์จำนวนหน่วยกิตขั้นต่ำและสูงสุดที่สามารถลงทะเบียนเรียนได้ในภาคปกติและภาคพิเศษตามข้อ 11",
        "target_articles": ["ข้อ 11"],
        "target_pages": [94],
        "schema": [
            {
                "topic": "ภาคปกติ",
                "condition_desc": "คำอธิบายเงื่อนไขการลงทะเบียนภาคการศึกษาปกติ",
                "min_credits": 9,
                "max_credits": 22,
                "article_no": "ข้อ 11",
                "source_page": 89
            },
            {
                "topic": "กรณีพิเศษขอจบ",
                "condition_desc": "คำอธิบายเงื่อนไขนักศึกษาปีสุดท้าย/ขอจบที่ต้องการลงมากกว่า 22 หน่วยกิต แต่ไม่เกิน 27 หน่วยกิต",
                "min_credits": None,
                "max_credits": 27,
                "article_no": "ข้อ 11",
                "source_page": 89
            },
            {
                "topic": "ภาคพิเศษฤดูร้อน",
                "condition_desc": "คำอธิบายเงื่อนไขการลงทะเบียนภาคการศึกษาพิเศษ (ไม่เกิน 9 หน่วยกิต)",
                "min_credits": None,
                "max_credits": 9,
                "article_no": "ข้อ 11",
                "source_page": 89
            }
        ]
    },
    {
        "category": "การทุจริตในการสอบ",
        "description": "บทลงโทษและผลทางวินัยเมื่อนักศึกษากระทำการทุจริตในการสอบตามข้อ 20 วรรคสอง และข้อ 33.8 / ข้อ 41",
        "target_articles": ["ข้อ 20 วรรคสอง", "ข้อ 33.8", "ข้อ 41"],
        "target_pages": [96, 99, 101],
        "schema": [
            {
                "topic": "ทุจริตครั้งแรก",
                "condition_desc": "นักศึกษาซึ่งทุจริตในการสอบ จะไม่ได้รับการพิจารณาผลการเรียน และพักการเรียนในภาคการศึกษาถัดไป 1 ภาคการศึกษา",
                "penalty_action": "พักการเรียน 1 ภาคการศึกษาถัดไป",
                "article_no": "ข้อ 20 วรรคสอง",
                "source_page": 91
            },
            {
                "topic": "ทุจริตซ้ำ",
                "condition_desc": "ทุจริตในการสอบซ้ำมากกว่า 1 ครั้ง พ้นสภาพการเป็นนักศึกษา",
                "penalty_action": "พ้นสภาพการเป็นนักศึกษา",
                "article_no": "ข้อ 33.8",
                "source_page": 94
            }
        ]
    },
    {
        "category": "เกณฑ์การภาคทัณฑ์",
        "description": "เกณฑ์การติดภาคทัณฑ์และการพ้นภาคทัณฑ์ตามค่าระดับคะแนนเฉลี่ยสะสม (GPA) ตามข้อ 22",
        "target_articles": ["ข้อ 22"],
        "target_pages": [97],
        "schema": [
            {
                "topic": "เกณฑ์การติดภาคทัณฑ์ตามข้อ 22",
                "condition_desc": "นักศึกษาที่ได้ค่าระดับคะแนนเฉลี่ยสะสมต่ำกว่า 2.00 ต้องถูกภาคทัณฑ์ไว้",
                "min_gpa": None,
                "max_gpa": 1.99,
                "penalty_action": "ติดภาคทัณฑ์",
                "article_no": "ข้อ 22",
                "source_page": 92
            },
            {
                "topic": "เกณฑ์การพ้นภาคทัณฑ์ตามข้อ 22",
                "condition_desc": "พ้นภาคทัณฑ์เมื่อได้รับค่าระดับคะแนนเฉลี่ยสะสมไม่ต่ำกว่า 2.00",
                "min_gpa": 2.00,
                "max_gpa": None,
                "penalty_action": "พ้นภาคทัณฑ์",
                "article_no": "ข้อ 22",
                "source_page": 92
            }
        ]
    },
    {
        "category": "เกณฑ์พ้นสภาพนักศึกษา",
        "description": "เกณฑ์การพ้นสภาพนักศึกษาจากผลการศึกษาตามข้อ 33 (เช่น GPA ต่ำกว่า 1.00 หรือระหว่างภาคทัณฑ์)",
        "target_articles": ["ข้อ 33.11", "ข้อ 33.12"],
        "target_pages": [99],
        "schema": [
            {
                "topic": "เกณฑ์พ้นสภาพนักศึกษาจากผลการเรียนตามข้อ 33",
                "condition_desc": "นักศึกษาที่ได้ค่าระดับคะแนนเฉลี่ยสะสมต่ำกว่า 1.00 หรือถูกภาคทัณฑ์และเทอมถัดไปได้ต่ำกว่า 2.00",
                "min_gpa": 0.99,
                "max_gpa": None,
                "penalty_action": "พ้นสภาพการเป็นนักศึกษา",
                "article_no": "ข้อ 33.12",
                "source_page": 94
            }
        ]
    },
    {
        "category": "เกณฑ์เกียรตินิยม",
        "description": "เกณฑ์การได้รับปริญญาเกียรตินิยมอันดับหนึ่งเหรียญทอง อันดับหนึ่ง และอันดับสอง ตามข้อ 27.2",
        "target_articles": ["ข้อ 27.2.1", "ข้อ 27.2.2", "ข้อ 27.2.3"],
        "target_pages": [98],
        "schema": [
            {
                "topic": "เกียรตินิยมอันดับ 1 เหรียญทอง",
                "condition_desc": "GPA สะสมตามโครงสร้างสูงสุดในกลุ่ม และไม่ต่ำกว่า 3.75 ไม่เทียบโอนจากสถาบันอื่น",
                "min_gpa": 3.75,
                "max_gpa": None,
                "article_no": "ข้อ 27.2.1",
                "source_page": 93
            },
            {
                "topic": "เกียรตินิยมอันดับ 1",
                "condition_desc": "GPA สะสมตามโครงสร้างและ GPA สะสมไม่ต่ำกว่า 3.50",
                "min_gpa": 3.50,
                "max_gpa": None,
                "article_no": "ข้อ 27.2.2",
                "source_page": 93
            },
            {
                "topic": "เกียรตินิยมอันดับ 2",
                "condition_desc": "GPA สะสมตามโครงสร้างและ GPA สะสมไม่ต่ำกว่า 3.25",
                "min_gpa": 3.25,
                "max_gpa": None,
                "article_no": "ข้อ 27.2.3",
                "source_page": 93
            }
        ]
    }
]


def ocr_regulation_pages_with_typhoon(
    page_images: dict[int, bytes],
    model_name: str,
    intermediate_md_path: Path
) -> dict[int, str]:
    """สกัดข้อความจากภาพสแกนด้วย Typhoon-OCR และบันทึกเป็น Markdown"""
    requests = _need("requests")
    print(f"\n[2/3] กำลังถอดรหัสข้อความจากภาพสแกน {len(page_images)} หน้าด้วย {model_name}...")
    intermediate_md_path.parent.mkdir(parents=True, exist_ok=True)

    extracted_texts: dict[int, str] = {}
    md_lines: list[str] = [
        "# ข้อความที่สกัดได้จากภาคผนวก ก (ข้อบังคับ สจล. ปริญญาตรี พ.ศ. 2564)",
        f"# วันที่สกัด: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"# โมเดล: {model_name}\n"
    ]

    for p_num in sorted(page_images.keys()):
        img_bytes = page_images[p_num]
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        print(f"      • หน้า {p_num:3d} (ขนาด {len(img_bytes)/1024:.1f} KB) ...", end="", flush=True)
        t0 = time.time()
        try:
            payload = {
                "model": model_name,
                "prompt": TYPHOON_REGULATION_PROMPT,
                "images": [img_b64],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "repeat_penalty": 1.2,
                }
            }
            res = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=300)
            res.raise_for_status()
            text_out = res.json().get("response", "").strip()
            elapsed = time.time() - t0
            extracted_texts[p_num] = text_out
            print(f" สำเร็จ ({len(text_out)} ตัวอักษร, {elapsed:.1f} วิ)")

            md_lines.append(f"<!-- Page {p_num} -->\n## หน้า {p_num}\n\n{text_out}\n\n---\n")
        except Exception as e:
            print(f" ล้มเหลว ({e})")
            extracted_texts[p_num] = ""

    intermediate_md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"      ✓ บันทึก Markdown เรียบร้อย: {intermediate_md_path}")
    return extracted_texts


def extract_regulations_with_llm(
    page_texts: dict[int, str],
    model_name: str
) -> list[RegulationItem]:
    """สกัดข้อบังคับการศึกษาจากข้อความ OCR ผ่าน Qwen3"""
    requests = _need("requests")
    print(f"\n[3/3] กำลังสกัดโครงสร้างข้อบังคับผ่าน {model_name}...")
    full_context = "\n\n".join(
        f"=== เนื้อหาหน้า PDF {p_num} ===\n{txt}"
        for p_num, txt in sorted(page_texts.items()) if txt
    )

    all_items: list[RegulationItem] = []

    for cat_spec in REGULATION_CATEGORIES:
        cat_name = cat_spec["category"]
        desc = cat_spec["description"]
        schema_json = json.dumps(cat_spec["schema"], ensure_ascii=False, indent=2)

        prompt = f"""จงสกัดข้อบังคับการศึกษาในหมวด '{cat_name}' จากข้อความเอกสารที่ให้มา
รายละเอียดหมวด: {desc}

ข้อความจากเอกสาร:
{full_context}

คำสั่ง:
1. ให้ตอบในรูปแบบ JSON Array ของ Object ตาม Schema ดังนี้เท่านั้น
2. ใช้ข้อมูลจริงจากข้อความในเอกสารเท่านั้น ห้ามแต่งข้อมูลขึ้นมาเอง
3. ฟิลด์ที่ไม่มีข้อมูลให้ใส่ null

ตัวอย่าง Schema ที่ต้องการ:
{schema_json}

ตอบเป็น JSON Array เท่านั้น:"""

        print(f"      • หมวด '{cat_name}' ...", end="", flush=True)
        t0 = time.time()
        try:
            payload = {
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "format": "json",
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 8192,
                }
            }
            res = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=300)
            res.raise_for_status()
            ans_raw = res.json().get("response", "").strip()

            ans_raw = re.sub(r"<think>.*?</think>", "", ans_raw, flags=re.DOTALL).strip()
            if ans_raw.startswith("```"):
                ans_raw = re.sub(r"^```(?:json)?\s*", "", ans_raw)
                ans_raw = re.sub(r"\s*```$", "", ans_raw)

            parsed = json.loads(ans_raw)
            if isinstance(parsed, dict):
                for k in ["regulations", "items", "data", "results"]:
                    if k in parsed and isinstance(parsed[k], list):
                        parsed = parsed[k]
                        break
                else:
                    parsed = [parsed]

            valid_count = 0
            for item_dict in parsed:
                item_dict["category"] = cat_name
                item_dict.setdefault("program_id", "ALL")
                item = RegulationItem(**item_dict)
                all_items.append(item)
                valid_count += 1
            elapsed = time.time() - t0
            print(f" ได้ {valid_count} รายการ ({elapsed:.1f} วิ)")
        except Exception as e:
            print(f" ข้อผิดพลาด: {e}")

    return all_items


def print_regulations_summary(regulations: list[RegulationItem]) -> None:
    print("\n" + "=" * 95)
    print("  สรุปข้อบังคับการศึกษาที่สกัดได้จากเล่ม PDF (Local VLM Pipeline)")
    print("=" * 95)
    print(f"{'หมวดหมู่ (Category)':<26} | {'หัวข้อ (Topic)':<25} | {'ข้อบังคับ':<12} | {'เงื่อนไข (GPA/หน่วยกิต/บทลงโทษ)':<28}")
    print("-" * 95)
    for r in regulations:
        cond_str = []
        if r.min_credits or r.max_credits:
            cond_str.append(f"หน่วยกิต: {r.min_credits or 0}-{r.max_credits or '-'}")
        if r.min_gpa or r.max_gpa:
            cond_str.append(f"GPA: {r.min_gpa or 0.0}-{r.max_gpa or '-'}")
        if r.penalty_action:
            cond_str.append(f"โทษ: {r.penalty_action}")
        cond_display = ", ".join(cond_str) if cond_str else (r.condition_desc[:25] + "...")
        print(f"{r.category:<26} | {r.topic:<25} | {str(r.article_no):<12} | {cond_display:<28}")
    print("=" * 95)


def run_extract_regulations(
    pdf_input: str | Path | None = None,
    page_spec: str = "94,96,97,98,99,101",
    out_dir: Path | str = "work/lab7b_run"
) -> Path:
    """
    กระบวนการสกัดข้อบังคับการศึกษา (ภาคผนวก ก) จากเล่ม PDF
    ส่งออกผลลัพธ์เป็น regulations.json และ intermediate_regulations_vlm.md เท่านั้น
    (ไม่แตะต้องฐานข้อมูล SQLite ตามหลัก Separation of Concerns)
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    if not (repo_root / "data").exists():
        repo_root = Path(__file__).resolve().parent.parent

    if pdf_input:
        pdf_path = Path(pdf_input)
    else:
        pdf_path = repo_root / "data" / "input" / "fulldoc_dsba.pdf"

    if not pdf_path.exists():
        candidates = [
            repo_root / "data" / "input" / "fulldoc_dsba.pdf",
            repo_root / "data" / "fulldoc_dsba.pdf",
            Path("data/input/fulldoc_dsba.pdf"),
            Path("data/fulldoc_dsba.pdf")
        ]
        for c in candidates:
            if c.exists():
                pdf_path = c
                break
        else:
            raise SystemExit(f"❌ ไม่พบไฟล์ PDF: {pdf_input}")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    out_json = out_path / "regulations.json"
    out_md = out_path / "intermediate_regulations_vlm.md"

    print("\n" + "=" * 70)
    print("  Lab 7B: สกัดข้อบังคับการศึกษาจากเล่ม PDF ด้วย Typhoon-OCR + Qwen")
    print("=" * 70)
    print(f"  • เอกสารนำเข้า : {pdf_path}")
    print(f"  • หน้าที่เลือก : {page_spec}")
    print(f"  • โมเดล OCR   : {MODEL_OCR}")
    print(f"  • โมเดล Text  : {MODEL_TEXT}")
    print(f"  • โฟลเดอร์ออก : {out_path}")
    print("=" * 70)

    assert_offline()

    fitz = _need("fitz", "pymupdf")
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    doc.close()

    wanted_indices = parse_page_range(page_spec, total_pages)
    wanted_pages = [i + 1 for i in wanted_indices]

    print(f"\n[1/3] กำลังเรนเดอร์ภาพจาก PDF {len(wanted_pages)} หน้า: {wanted_pages} ...")
    mat = fitz.Matrix(DPI / 72, DPI / 72)
    doc = fitz.open(str(pdf_path))
    page_images: dict[int, bytes] = {}
    for p_num in wanted_pages:
        pix = doc[p_num - 1].get_pixmap(matrix=mat)
        page_images[p_num] = pix.tobytes("png")
    doc.close()
    print(f"      ✓ เรนเดอร์ภาพครบ {len(page_images)} หน้า @ {DPI} DPI")

    # Step 2: Typhoon-OCR
    page_texts = ocr_regulation_pages_with_typhoon(page_images, MODEL_OCR, out_md)

    # Step 3: Information Extraction via Qwen
    regulations = extract_regulations_with_llm(page_texts, MODEL_TEXT)

    # Step 4: Save JSON only (No DB touching!)
    items_dict = [r.model_dump() for r in regulations]
    out_json.write_text(json.dumps(items_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n      ✓ บันทึก JSON เรียบร้อย: {out_json} ({len(items_dict)} รายการ)")

    print_regulations_summary(regulations)
    print(f"\n✓ สกัดข้อบังคับการศึกษาเสร็จสมบูรณ์!")
    print(f"  • Markdown: {out_md}")
    print(f"  • JSON    : {out_json}")
    return out_json


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Lab 7B — สกัดแผนการศึกษาจากเล่มหลักสูตร ด้วย LLM บนเครื่อง")
    ap.add_argument("-i", "--input", help="ไฟล์เล่มหลักสูตร (.pdf/.png)")
    ap.add_argument("-g", "--gt", help="ไฟล์ ground truth (.json)")
    ap.add_argument("-o", "--out", default="output")
    ap.add_argument("-p", "--pipeline", default="all",
                    choices=["all", "baseline", "text", "vlm"])
    ap.add_argument("--pages", help='เลือกเฉพาะบางหน้า เช่น "42-58" หรือ "3,7,10-12"')
    ap.add_argument("--plan", choices=["coop", "no_coop", "single"], default=None,
                    help="เลือกแผนการศึกษา: coop (สหกิจ), no_coop (ไม่สหกิจ), single (แผนเดียว)")
    ap.add_argument("--program", default=None, choices=["DSBA", "BIT", "IT", "AIT"],
                    help="รหัสหลักสูตร (ถ้าไม่ระบุจะเดาจากชื่อไฟล์ input หรือ gt)")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--eval-only", metavar="PRED_JSON")
    
    ap.add_argument("--enrich-pages", action="store_true",
                    help="สกัดเลขหน้า (printed_pages, pdf_pages) จากเล่ม PDF เข้าสู่ pred_text.json ทุกหลักสูตร")
    ap.add_argument("--extract-regulations", action="store_true",
                    help="สกัดข้อบังคับการศึกษา (ภาคผนวก ก) จากเล่ม PDF ด้วย Typhoon-OCR + Qwen")
    args = ap.parse_args()

    if args.check:
        sys.exit(0 if check_environment() else 1)

    if args.enrich_pages:
        enrich_all_curricula_pages()
        return

    if args.extract_regulations:
        pdf_file = args.input or "data/input/fulldoc_dsba.pdf"
        pages_spec = args.pages or "94,96,97,98,99,101"
        out_dir = Path(args.out) if args.out != "output" else Path("work/lab7b_run")
        run_extract_regulations(pdf_file, pages_spec, out_dir)
        return

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.eval_only:
        if not args.gt:
            raise SystemExit("❌ --eval-only ต้องระบุ --gt ด้วย")
        pred_path = Path(args.eval_only)
        pred = json.loads(pred_path.read_text(encoding="utf-8"))
        gt = json.loads(Path(args.gt).read_text(encoding="utf-8"))
        stats, align = evaluate(pred, gt)
        M.print_table(stats, f"ผลประเมิน: {pred_path.name}")
        print(f"\n  จับคู่วิชา: เจอ {align['matched']}/{align['gt_total']} "
              f"| ตก {align['missed']} | แต่งเกิน {align['spurious']}")
        print(f"  P={align['precision']:.3f}  R={align['recall']:.3f}  "
              f"F1={align['f1']:.3f}")
        if align["missed_codes"]:
            print(f"  วิชาที่อ่านตก: {', '.join(map(str, align['missed_codes'][:10]))}")
        M.print_errors(stats)

        # บันทึกผลเป็น comparison.csv และ evaluation.json
        save_dir = outdir if args.out != "output" else pred_path.parent
        save_dir.mkdir(parents=True, exist_ok=True)
        csv_path = save_dir / "comparison.csv"
        M.save_csv(stats, str(csv_path), extra={"pipeline": "text"})

        eval_summary = {
            "text": {
                **M.stats_to_dict(stats),
                "alignment": align,
                "internal_check": verify_internal(pred),
            }
        }
        json_path = save_dir / "evaluation.json"
        json_path.write_text(json.dumps(eval_summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✓ บันทึกผลการประเมินลงไฟล์เรียบร้อย:")
        print(f"  • CSV : {csv_path}")
        print(f"  • JSON: {json_path}")
        return

    if not args.input:
        raise SystemExit("❌ ต้องระบุ --input")

    prog = args.program
    if not prog:
        check_str = f"{args.gt or ''} {args.input or ''}".upper()
        for p in ["DSBA", "BIT", "IT", "AIT"]:
            if p in check_str:
                prog = p
                break
        if not prog:
            prog = "DSBA"

    page_spec = args.pages
    if not page_spec:
        specs_table = TEXT_PLAN_PAGE_SPECS if args.pipeline == "text" else PLAN_PAGE_SPECS
        if prog in specs_table:
            plan_key = args.plan or ("single" if prog == "AIT" else "coop")
            if plan_key in specs_table[prog]:
                page_spec = specs_table[prog][plan_key]
                print(f"  [Auto-Plan] เลือกช่วงหน้าอัตโนมัติสำหรับ {prog} ({plan_key}): หน้า {page_spec}")

    print("\n" + "=" * 70)
    print("  Lab 7B — สกัดแผนการศึกษา ด้วย LLM ที่รันบนเครื่องตัวเอง")
    print(f"  หลักสูตร: {prog}")
    print("=" * 70)
    assert_offline()

    print(f"\nเตรียมข้อมูลจาก: {args.input}")
    pages = load_pages(args.input, page_spec)

    if args.pipeline == "all":
        names = ["text", "vlm"] if SKIP_BASELINE else ["baseline", "text", "vlm"]
        if SKIP_BASELINE:
            print("\n(ข้าม pipeline baseline ตามค่า LAB7_SKIP_BASELINE=1)")
    else:
        names = [args.pipeline]

    results: dict[str, dict] = {}
    for n in names:
        r = run_pipeline(n, pages, outdir, args.input, page_spec, prog_name=prog)
        if r:
            results[n] = r

    # ---------- ตรวจความสอดคล้องภายใน ----------
    print("\n" + "=" * 70)
    print("  ตรวจความสอดคล้องภายใน (ไม่ใช้เฉลย)")
    print("=" * 70)
    for n, data in results.items():
        v = verify_internal(data)
        print(f"\n  {'✓' if v['ok'] else '✗'} {n}: {v['n_courses']} วิชา, "
              f"รวม {v['total_credits_fixed_terms']} หน่วยกิต (เฉพาะภาคที่ระบุชัด)")
        for msg in v["issues"][:6]:
            print(f"      • {msg}")
        if len(v["issues"]) > 6:
            print(f"      ... และอีก {len(v['issues']) - 6} รายการ")

    # ---------- เทียบ ground truth ----------
    if not args.gt:
        print("\n(ไม่ได้ระบุ --gt จึงข้ามการเทียบกับเฉลย)")
        return

    gt = json.loads(Path(args.gt).read_text(encoding="utf-8"))
    csv_path = outdir / "comparison.csv"
    combined: dict[str, Any] = {}
    first = True

    for n, data in results.items():
        stats, align = evaluate(data, gt)
        M.print_table(stats, f"PIPELINE = {n}")
        print(f"  จับคู่วิชา: เจอ {align['matched']}/{align['gt_total']} "
              f"| ตก {align['missed']} | แต่งเกิน {align['spurious']}   "
              f"P={align['precision']:.3f} R={align['recall']:.3f} "
              f"F1={align['f1']:.3f}")
        M.print_errors(stats, limit=2)

        d = M.stats_to_dict(stats)
        d["alignment"] = align
        d["internal_check"] = verify_internal(data)
        combined[n] = d

        tmp = outdir / f"_tmp_{n}.csv"
        M.save_csv(stats, str(tmp), extra={"pipeline": n})
        lines = tmp.read_text(encoding="utf-8-sig").splitlines()
        with open(csv_path, "w" if first else "a", encoding="utf-8-sig") as f:
            f.write("\n".join(lines if first else lines[1:]) + "\n")
        tmp.unlink()
        first = False

    (outdir / "evaluation.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n✓ เสร็จสิ้น")
    print(f"  ตารางเปรียบเทียบ (เปิดใน Excel): {csv_path}")
    print(f"  ผลละเอียด: {outdir / 'evaluation.json'}")


if __name__ == "__main__":
    main()
