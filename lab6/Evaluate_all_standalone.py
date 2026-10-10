"""
Made by Pawarit Pansing 67070098 (DSBA)
========================================================
Output:
  outputs/eval_field_level.json
  outputs/eval_page_level.csv
  outputs/eval_category_summary.csv
  พิมพ์สรุปผลลง console
=====================================================================
"""

from __future__ import annotations  # ให้ type hint แบบ `str | None` ใช้ได้แม้ Python < 3.10

import json
import re
import csv
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, asdict

_this_dir = Path(__file__).resolve().parent
ROOT = _this_dir.parent if not (_this_dir / "data").exists() and (_this_dir.parent / "data").exists() else _this_dir

# ============================================================
# [inlined from src/ocr_system/field_extraction.py] extract_courses()
# ============================================================

def extract_common_fields(text: str) -> dict:
    """Basic rule-based extraction. Customize regexes for your document type."""
    fields = {}

    email = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    if email:
        fields["email"] = email.group(0)

    date = re.search(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", text)
    if date:
        fields["date"] = date.group(0)

    student_id = re.search(r"\b\d{8,12}\b", text)
    if student_id:
        fields["numeric_id"] = student_id.group(0)

    phone = re.search(r"(?:\+?66|0)\d{8,9}\b", text.replace("-", ""))
    if phone:
        fields["phone"] = phone.group(0)

    return fields


# ---------------------------------------------------------------------------
# Week 4: reformat Lab 3 raw OCR text into the same shape as the course-table
# ground truth files under data/ground_truth/ (e.g. DSBA_academic_plan_*.json)
# ---------------------------------------------------------------------------
#
# doc.pdf turns out to contain FOUR visually different table layouts that all
# need different line-parsing rules:
#
#   1. "Faculty course requirement" tables (single current code per row):
#         90642036   เตรียมความพร้อมสำหรับวิศวกร        1(0-3-0)
#                     PRE-ACTIVITIES FOR ENGINEERS
#
#   2. "Master list" tables under a รหัสวิชา... explanation preamble
#      (also single current code per row, same shape as #1):
#         90964201   ปฏิบัติงานตามทักษะด้านบุคคล...      1(0-2-1)
#                     PRACTICE UNDER PERSONAL AND PROFESSIONAL SKILLS 1
#
#   3. "Code comparison across curriculum revisions" tables — THREE code
#      columns (2557 / 2559 / 2564 editions) per row, where earlier columns
#      may be "-" if the course didn't exist in that edition:
#         -   90591019   90641001   โรงเรียนสร้างเสน่ห์ / CHARM SCHOOL   2(1-2-3)
#      The rightmost non-dash code is the *current* (2564) code and is what
#      should match modern ground-truth files. Earlier codes are kept in
#      `note` rather than discarded, since they're real data, not OCR noise.
#
#   4. "Skill mapping" tables — a course code followed by a row of numeric
#      skill-weight columns instead of a name/credits pair. These rows must
#      be skipped entirely (or they'd corrupt name_th/credits with numbers).
#
# Because we don't have the raw tesseract linearization of this particular
# PDF in hand, the regexes below match on token *shape* (8-digit codes,
# credit parentheses, dash placeholders) rather than on exact column
# ordering, and are deliberately permissive about whitespace between tokens
# so they survive OCR line-wrapping. If real OCR text turns out to
# linearize a row across multiple physical lines, `_looks_like_code_row`
# gives a single place to extend the lookahead.

# --- section detection --------------------------------------------------

# "ตารางเปรียบเทียบรายวิชาหมวดวิชาศึกษาทั่วไป ... " comparison-table header
_COMPARISON_SECTION_RE = re.compile(r"ตารางเปรียบเทียบรายวิชา")

# "รหัสวิชา ฉบับ พ.ศ. 2557 | 2559 | 2564" column header row for the
# comparison table (appears once per page as the table repeats).
_COMPARISON_HEADER_RE = re.compile(r"รหัสวิชา\s*ฉบับ\s*พ\.?ศ\.?")

# "คำอธิบายระบบรหัสวิชา..." — explanation of the code-numbering scheme that
# precedes the master list; not a course, but the master list rows that
# follow it (single-code, e.g. 90964201) should still be parsed normally.
_CODE_SCHEME_EXPLANATION_RE = re.compile(r"คำอธิบายระบบรหัสวิชา")

# "FACULTY COURSE REQUIREMENT" section (also พ.ศ. คณะ... headers like
# "คณะวิศวกรรมศาสตร์"). Parsed the same way as single-code rows; no special
# handling needed beyond recognizing it's not the comparison table.
_FACULTY_SECTION_RE = re.compile(r"FACULTY COURSE REQUIREMENT|กลุ่มวิชาตามเกณฑ์ของคณะ")

# Skill-mapping tables: header row mentions these fixed column groups, or the
# Thai page title that precedes them ("ค่าน้ำหนักของทักษะ...SKILL MAPPING").
_SKILL_MAPPING_HEADER_RE = re.compile(
    r"Problem[-\s]?Solving|Self\s*Management|Working with People|Digital\s*Literacy"
    r"|ค่าน้ำหนักของทักษะ|SKILL\s*MAPPING"
)
# We simply flip back to "normal" parsing whenever we see a line that looks
# like a normal section boundary (headers, comparison headers, faculty
# headers) rather than trying to detect the bottom of the table precisely.
_ANY_SECTION_RESET_RE = re.compile(
    r"^(?:กลุ่มทักษะ|กลุ่มวิชา|คณะ|วิทยาลัย|วิทยาเขต|"
    r"ตารางเปรียบเทียบ|FACULTY COURSE REQUIREMENT|"
    r"คำอธิบายระบบรหัสวิชา|รายชื่อวิชาตามกลุ่ม)"
)

# --- token-level regexes --------------------------------------------------

_DASH_TOKEN_RE = re.compile(r"^-+$")

# A course entry line looks like: "06066101 พื้นฐานทางธุรกิจ... 3 (3-0-6)"
_CODE_LINE_RE = re.compile(r"^(\d{8})\s+(.*)$")

# Up to three leading code-or-dash tokens (comparison-table rows), e.g.:
#   "-  90591019  90641001  โรงเรียนสร้างเสน่ห์ ... 2(1-2-3)"
#   "90303012  90591007  90642063  การพัฒนาสุขภาพ... 3(3-0-6)"
_COMPARISON_ROW_RE = re.compile(
    r"^(?P<c1>-{1,2}|\d{8})\s+(?P<c2>-{1,2}|\d{8})\s+(?P<c3>-{1,2}|\d{8})\s+(?P<rest>.*)$"
)

# Same department-prefix validation used for single-code rows.
_VALID_CODE_PREFIXES = ("06", "90")
_VALID_CODE_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in _VALID_CODE_PREFIXES) + r")\d{6}\b"
)

# Credit strings come out of OCR noisy: "3 (3-0-6)", "3(225)", "3(30-6)",
# "3(2259)" ... This grabs the total credits and the 3 breakdown digits
# wherever they land, ignoring stray characters/extra digits around them.
_CREDIT_RE = re.compile(r"(\d)\s*\(\s*(\d)\D{0,3}(\d)\D{0,3}(\d)\)?")


def _looks_like_skill_row(rest: str) -> bool:
    """A skill-mapping data row: course code followed by mostly-numeric
    tokens (weights) rather than Thai/English course-name text. Detected by
    a high proportion of standalone digit tokens in `rest`."""
    tokens = rest.split()
    if not tokens:
        return False
    numeric_tokens = sum(1 for t in tokens if re.fullmatch(r"\d{1,3}", t))
    return numeric_tokens >= max(3, len(tokens) // 2)


# Section headers such as "2) กลุ่มพื้นฐานวิชาชีพ 33 หน่วยกิต"
_SECTION_HEADER_RE = re.compile(r"^\d+\)\s*(.+?)\s*\d+\s*หน่วยกิต")

_TABLE_HEADER_RE = re.compile(r"^รหัสวิชา")
_PAGE_MARK_RE = re.compile(r"^---\s*Page\s*\d+\s*---$")

# Footer / letterhead lines that sometimes trail onto the last course entry
# because there's no page marker right after them.
_FOOTER_RE = re.compile(r"(วท\s*\.\s*บ|คณะ|สาขาวิชา|มคอ\s*\.?\s*\d)")

# Page numbers / OCR watermark garbage that pollute name_en continuation
# lines (e.g. "151", "เขนนฑฑคคคคคคคฉฉลลล๒๒๒๒๒-----------้-้-").
_PAGE_NUMBER_LINE_RE = re.compile(r"^\d{1,4}$")
_WATERMARK_LINE_RE = re.compile(r"^[^\wก-๙]{6,}$|^[A-Za-z]{4,}$")


def _normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _category_from_header(header_text: str) -> str:
    """Best-effort mapping of a sub-section heading to the coarse GT category."""
    if "ทั่วไป" in header_text:
        return "หมวดวิชาศึกษาทั่วไป"
    return "หมวดวิชาเฉพาะ"


def _find_valid_code(line: str) -> tuple[str, str] | None:
    """Locate a plausible course code at the start of a single-code table row.

    Historically this trusted the first 8 digits on the line no matter what.
    That broke whenever OCR misread a digit in that first token, or a stray
    numeric column landed before the real code. Now we:

      1. Require the line to still start with an 8-digit token.
      2. Validate that token against known department-code prefixes.
      3. If it doesn't validate, search the *rest* of the line for a token
         that does.
    """
    first_m = _CODE_LINE_RE.match(line)
    if not first_m:
        return None

    code, rest = first_m.group(1), first_m.group(2)
    if _VALID_CODE_RE.fullmatch(code):
        return code, rest

    alt = _VALID_CODE_RE.search(rest)
    if alt:
        new_rest = _normalize_ws(rest[: alt.start()] + " " + rest[alt.end():])
        return alt.group(0), new_rest

    return None


def _parse_comparison_row(line: str) -> tuple[str, str, list[str]] | None:
    """Parse a 3-edition code-comparison row.

    Returns (current_code, rest_of_line, superseded_codes) where
    superseded_codes lists any earlier-edition codes found (oldest first),
    or None if the line doesn't match this row shape.

    The *rightmost* valid 8-digit code among the leading columns is treated
    as current, since these tables are laid out oldest-edition-first,
    newest-edition-last (2557 | 2559 | 2564).
    """
    m = _COMPARISON_ROW_RE.match(line)
    if not m:
        return None

    columns = [m.group("c1"), m.group("c2"), m.group("c3")]
    valid_columns = [c for c in columns if _VALID_CODE_RE.fullmatch(c)]
    if not valid_columns:
        return None

    current_code = valid_columns[-1]
    superseded = [c for c in valid_columns[:-1]]
    return current_code, m.group("rest"), superseded


def extract_courses(text: str) -> list[dict]:
    """Parse raw OCR text (Lab 3 output, e.g. sample_ocr.json['text']) into a
    list of course records shaped like the ground-truth files, e.g.:

        {
          "code": "06066101",
          "name_th": "...",
          "name_en": "...",
          "credits": "3(3-0-6)",
          "year": null,
          "semester": null,
          "category": null,
          "type": null,
          "prerequisite": null,
          "flexible_year_semester": null,
          "note": null
        }

    Fields that aren't recoverable from the linear OCR text alone (year,
    semester, type, prerequisite) are left as null rather than guessed.
    `note` is used to record superseded course codes recovered from
    edition-comparison tables (see module docstring, layout #3).
    """
    courses: list[dict] = []
    current: dict | None = None
    name_en_lines: list[str] = []
    current_category: str | None = None
    in_skill_mapping = False

    def flush() -> None:
        nonlocal current, name_en_lines
        if current is not None:
            cleaned = [
                l for l in name_en_lines
                if l.strip()
                and not _PAGE_NUMBER_LINE_RE.match(l.strip())
                and not _WATERMARK_LINE_RE.match(l.strip())
            ]
            current["name_en"] = "\n".join(cleaned) or None
            courses.append(current)
        current = None
        name_en_lines = []

    def start_record(code: str, rest: str, superseded: list[str] | None = None) -> None:
        nonlocal current
        credit_m = _CREDIT_RE.search(rest)
        if credit_m:
            name_th = _normalize_ws(rest[: credit_m.start()])
            credits = f"{credit_m.group(1)}({credit_m.group(2)}-{credit_m.group(3)}-{credit_m.group(4)})"
        else:
            name_th = _normalize_ws(rest)
            credits = None
        note = None
        if superseded:
            note = "superseded codes: " + ", ".join(superseded)
        current = {
            "code": code,
            "name_th": name_th,
            "name_en": None,
            "credits": credits,
            "year": None,
            "semester": None,
            "category": current_category,
            "type": None,
            "prerequisite": None,
            "flexible_year_semester": None,
            "note": note,
        }

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _PAGE_MARK_RE.match(line):
            continue

        # --- section-level state transitions ---------------------------
        if _SKILL_MAPPING_HEADER_RE.search(line):
            flush()
            in_skill_mapping = True
            continue

        if in_skill_mapping:
            # Stay in skip-mode until we clearly leave this table, i.e. we
            # hit a line that looks like the start of a new named section
            # (a new sub-heading, faculty block, or comparison table).
            if _ANY_SECTION_RESET_RE.match(line):
                in_skill_mapping = False
                # fall through to normal processing of this line below
            else:
                continue

        if _COMPARISON_SECTION_RE.search(line) or _COMPARISON_HEADER_RE.search(line):
            flush()
            continue

        if _FACULTY_SECTION_RE.search(line) or _CODE_SCHEME_EXPLANATION_RE.search(line):
            flush()
            continue

        header_m = _SECTION_HEADER_RE.match(line)
        if header_m:
            flush()
            current_category = _category_from_header(header_m.group(1))
            continue

        if _TABLE_HEADER_RE.match(line):
            flush()
            continue

        # --- layout #3: 3-edition code comparison row -------------------
        comparison = _parse_comparison_row(line)
        if comparison:
            flush()
            code, rest, superseded = comparison
            start_record(code, rest, superseded)
            continue

        # --- layout #1/#2: single current-code row -----------------------
        found = _find_valid_code(line)
        if found:
            code, rest = found
            if _looks_like_skill_row(rest):
                # A skill-mapping row slipped through without a header match
                # (e.g. mid-table continuation) — skip it rather than
                # corrupting name_th/credits with numeric weight columns.
                flush()
                continue
            flush()
            start_record(code, rest)
            continue

        if _FOOTER_RE.search(line):
            flush()
            continue

        if current is not None:
            name_en_lines.append(line)

    flush()

    # Dedup: the same course frequently appears in multiple tables (edition
    # comparison, faculty requirement, master list). Keep the first record
    # seen for each code rather than emitting duplicates that inflate the
    # course count and skew evaluation metrics.
    seen: dict[str, dict] = {}
    for c in courses:
        if c["code"] not in seen:
            seen[c["code"]] = c
    return list(seen.values())


def _placeholder_field_extraction_marker():
    pass


# ---------------------------------------------------------------------------
# Ground-truth filtering: keep only OCR content that actually matches GT
# ---------------------------------------------------------------------------
#
# `extract_courses` (above) parses *everything* that looks like a course row
# in the document, which is normally correct (a scanned plan may legitimately
# contain more tables/electives than a single GT file lists). But sometimes
# what's wanted is the opposite view: "of everything OCR read, keep only the
# parts that are actually in this ground-truth file, drop the rest" — e.g. to
# sanity-check OCR quality on just the courses we have an answer key for,
# without noise from unrelated tables/electives on the same page.

_REAL_CODE_RE = re.compile(r"^\d{8}$")


def _is_real_course_code(code: str | None) -> bool:
    if not code:
        return False
    return bool(_REAL_CODE_RE.fullmatch(code.strip()))


def ground_truth_codes(gt_courses: list[dict]) -> set[str]:
    """Set of real (non-placeholder) 8-digit course codes from a GT course list."""
    return {c["code"].strip() for c in gt_courses if _is_real_course_code(c.get("code"))}


def filter_courses_by_ground_truth(courses: list[dict], gt_courses: list[dict]) -> list[dict]:
    """Keep only extracted courses whose code appears in the ground truth."""
    gt_codes = ground_truth_codes(gt_courses)
    return [c for c in courses if c.get("code") in gt_codes]


def filter_text_by_ground_truth(text: str, gt_courses: list[dict]) -> tuple[str, list[dict]]:
    """Parse raw OCR text, then keep only the course entries whose code is in
    the ground truth, rebuilt back into text (in original reading order).

    Returns (filtered_text, filtered_courses).
    """
    all_courses = extract_courses(text)
    filtered = filter_courses_by_ground_truth(all_courses, gt_courses)

    lines = []
    for c in filtered:
        credits = c.get("credits")
        lines.append(f"{c['code']} {c['name_th']} {credits}".strip())
        if c.get("name_en"):
            lines.append(c["name_en"].replace("\n", " "))
    return "\n".join(lines), filtered


def format_extraction_output(courses: list[dict], source_path: str, engine: str | None = None) -> dict:
    """Wrap extracted courses in the same top-level shape used by the GT files
    under data/ground_truth/ so the result can be diffed/evaluated directly."""
    stem = Path(source_path).stem
    return {
        "source": f"OCR extraction ({engine or 'unknown'} engine) of {Path(source_path).name}",
        "description": f"Auto-extracted course list for {stem} (Week 4 lab)",
        "program": None,
        "plan": None,
        "courses": courses,
    }

# ============================================================
# [inlined from src/ocr_system/evaluation.py] evaluate_courses()
# ============================================================

@dataclass
class CourseEvaluationResult:
    """Result of comparing an extractor's course list against ground truth,
    at the level of course codes and credits rather than raw OCR text.

    This is the metric that actually answers "did we recover the courses
    that are supposed to be in this plan", which char/word error rate on
    linearized text cannot answer on its own (see conversation history:
    CER/WER over `prediction["text"]` says nothing about whether individual
    course codes were read correctly).
    """
    file: str
    gt_fixed_course_count: int
    codes_found: int
    codes_missing: list[str]
    code_recall: float
    credits_exact_match: int
    credits_checked: int


_REAL_CODE_RE = re.compile(r"^\d{8}$")


def is_real_course_code(code: str | None) -> bool:
    """True only for an unambiguous, single, fixed 8-digit course code.

    Rejects: None/empty, placeholders containing "x"/"X", combined
    "A หรือ B" entries, footnote rows, and anything not exactly 8 digits.
    """
    if not code:
        return False
    return bool(_REAL_CODE_RE.fullmatch(code.strip()))


def evaluate_courses(gt_courses: list[dict], predicted_courses: list[dict], file_name: str = "") -> dict:
    """Compare an extractor's course list against ground truth at the level
    of course codes and credits.

    This intentionally measures RECALL from the ground-truth side (did we
    find every fixed code the plan requires) rather than precision from the
    extracted side, because prediction files may legitimately contain many
    more courses than a single plan's GT lists (e.g. a full elective
    catalog page scanned for a plan that only fixes 8 of those codes as
    required). Scoring "matched / len(predicted_courses)" in that situation
    conflates "extractor is bad" with "this page covers more than one
    plan", which is a different, unrelated question.
    """
    gt_real = [c for c in gt_courses if is_real_course_code(c.get("code"))]
    gt_by_code = {c["code"]: c for c in gt_real}

    pred_by_code: dict[str, dict] = {}
    for c in predicted_courses:
        code = c.get("code")
        if code and code not in pred_by_code:
            pred_by_code[code] = c

    found_codes = [code for code in gt_by_code if code in pred_by_code]
    missing_codes = [code for code in gt_by_code if code not in pred_by_code]

    credits_checked = 0
    credits_exact_match = 0
    for code in found_codes:
        gt_credits = gt_by_code[code].get("credits")
        pred_credits = pred_by_code[code].get("credits")
        if gt_credits is None:
            continue
        credits_checked += 1
        if gt_credits == pred_credits:
            credits_exact_match += 1

    result = CourseEvaluationResult(
        file=file_name,
        gt_fixed_course_count=len(gt_by_code),
        codes_found=len(found_codes),
        codes_missing=sorted(missing_codes),
        code_recall=(len(found_codes) / len(gt_by_code)) if gt_by_code else 1.0,
        credits_exact_match=credits_exact_match,
        credits_checked=credits_checked,
    )
    return asdict(result)


GT_DIR = ROOT / "data" / "ground_truth"
OUT_DIR = ROOT / "outputs"
OUT_DIR.mkdir(exist_ok=True)

# BUG #1 FIX: ไฟล์ OCR จริงที่มีอยู่ในรีโป (ไม่ใช่ dsba_input_v2_ocr.json ที่ไม่มีอยู่)
OCR_FILES = {
    "AIT": OUT_DIR / "fulldoc_AIT_ocr.json",
    "IT": OUT_DIR / "fulldoc_it_ocr.json",
    "DSBA": OUT_DIR / "fulldoc_dsba_ocr.json",
}

# BUG #10 FIX: ตอนนี้มี ground truth เลขหน้าครบ 3 โปรแกรมแล้ว (ไม่ใช่แค่ DSBA)
PAGE_LEVEL_PROGRAMS = ["AIT", "IT", "DSBA"]


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def normalize(s):
    return re.sub(r"\s+", "", str(s)) if s is not None else ""


def normalize_program(p: str) -> str:
    """BUG #7 FIX: Map_page_all.csv มี program บางแถวเป็นตัวเล็กล้วน
    ("dsba", "it") ปนกับตัวใหญ่ ("AIT", "IT", "DSBA") ให้ upper() ทั้งหมด
    เพื่อให้ตรงกับ key ใน OCR_FILES / PAGE_LEVEL_PROGRAMS เสมอ"""
    return (p or "").strip().upper()


def thai_am_fix(s: str) -> str:
    """BUG #3 FIX: normalize decomposed Thai SARA AM (นิคหิต+สระอา, U+0E4D
    U+0E32) to precomposed SARA AM (U+0E33). Standard unicodedata.normalize
    does NOT fix this - Thai SARA AM has no canonical decomposition in the
    Unicode standard, so it must be done manually."""
    if s is None:
        return s
    return s.replace("\u0e4d\u0e32", "\u0e33")


THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def thai_digits_fix(s: str) -> str:
    """BUG #4 FIX: source มคอ.2 documents write numbers in Thai numerals
    (e.g. '๒.๐๐' for '2.00'). Convert to Arabic numerals before comparing,
    since ground truth values are stored in Arabic numerals."""
    if s is None:
        return s
    return s.translate(THAI_DIGITS)


def printed_page_number(text: str) -> str | None:
    """บรรทัดแรกของแต่ละหน้า OCR มักเป็นเลขหน้าจริงที่พิมพ์อยู่ในเอกสาร.

    BUG #2 FIX: เดิมต้องการทั้งบรรทัดเป็นตัวเลขล้วนๆ (^\\d{1,4}$) แต่บาง
    เอกสาร (เช่น AIT) OCR รวมเลขหน้ากับข้อความหัวเรื่องไว้บรรทัดเดียวกัน
    เช่น "1 รายละเอียดหลักสูตร..." เปลี่ยนมาจับ "เลขนำหน้าบรรทัด" แทน
    """
    for line in text.strip().split("\n"):
        line = line.strip()
        if line:
            m = re.match(r"^(\d{1,4})\b", line)
            return m.group(1) if m else None
    return None


def load_ocr(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    # BUG #3 + #4 FIX: normalize สำ และเลขไทย ตั้งแต่ตอนโหลด ก่อนใช้ที่อื่นต่อ
    full_text = thai_digits_fix(thai_am_fix(doc["text"]))
    pages = {
        p["page"]: thai_digits_fix(thai_am_fix(p["text"]))
        for p in doc["pages"]
    }
    printed = {pg: printed_page_number(t) for pg, t in pages.items()}
    return full_text, pages, printed


def find_printed_pages(needle: str, ocr_pages: dict, ocr_printed: dict) -> set[str]:
    """คืนเลขหน้าจริงที่พิมพ์ (ไม่ใช่เลขหน้า OCR 1..N) ที่พบ needle อยู่ในเนื้อหา"""
    found = set()
    for pg, txt in ocr_pages.items():
        if needle in txt:
            p = ocr_printed.get(pg)
            if p:
                found.add(p)
    return found


def resolve_gt_pages(pages_str: str, ocr_printed: dict) -> set[str]:
    """BUG #8 FIX: Map_page_all.csv คอลัมน์ pages มีข้อมูล 2 แบบปนกันได้ใน
    เซลล์เดียวกัน:
      - เลขหน้าที่พิมพ์จริงในเอกสาร (ใช้ตรงๆ) เช่น "18", "26"
      - เลขหน้า OCR แบบ raw (index หน้าตามลำดับไฟล์ OCR JSON ไม่ใช่เลขหน้าที่
        พิมพ์จริง) นำหน้าด้วย "ocr" เช่น "ocr328" -> ต้อง lookup ocr_printed
        ของโปรแกรมนั้นเพื่อแปลงเป็นเลขหน้าที่พิมพ์จริงก่อน จึงจะเทียบกับ
        predicted_pages (ซึ่งมาจาก printed_page_number() เสมอ) ได้ถูกต้อง
    token ที่แปลงไม่ได้ (ไม่มีใน ocr_printed) จะถูกข้าม
    """
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
            # ถ้า lookup ไม่เจอ ข้ามไปเงียบๆ (หน้านั้นอาจไม่ถูก OCR อ่านเลขหน้าออก)
        else:
            result.add(tok)
    return result


# BUG #5 FIX: หมวด GT ("เกณฑ์การลงทะเบียน") มักไม่ตรงกับคำในเอกสารจริงตรงๆ
# ("การลงทะเบียนเรียน" ไม่มี "เกณฑ์" นำหน้า) ลองตัดคำนำหน้าเหล่านี้ออกแล้ว
# ค้นซ้ำเป็น fallback
STRIP_PREFIXES = ["เกณฑ์การ", "เกณฑ์"]


def find_category_pages(category: str, ocr_pages: dict, ocr_printed: dict) -> set[str]:
    category = thai_am_fix(category)
    candidates = [category]
    for pre in STRIP_PREFIXES:
        if category.startswith(pre):
            rest = category[len(pre):]
            if rest and rest not in candidates:
                candidates.append(rest)
    found = set()
    for needle in candidates:
        found |= find_printed_pages(needle, ocr_pages, ocr_printed)
    return found


def page_category_alias(cat_name: str, prog: str) -> str:
    """BUG #9 FIX: field-level ใช้ key เช่น "DSBA - หมวดศึกษาทั่วไป" แต่
    source_gt ฝั่ง Map_page_all.csv เป็น "หมวดศึกษาทั่วไป (general_education)"
    เฉยๆ (ไม่มี prefix โปรแกรม) แปลงชื่อให้ตรงกันก่อนจับคู่ในขั้น
    Category Level summary"""
    if cat_name.endswith("หมวดศึกษาทั่วไป"):
        return "หมวดศึกษาทั่วไป"
    return cat_name


# ------------------------------------------------------------------
# load OCR for all 3 programs (BUG #1 + #6 FIX: loop instead of hardcode)
# ------------------------------------------------------------------

ocr_by_program = {}
for prog, path in OCR_FILES.items():
    if not path.exists():
        print(f"[warn] ไม่พบ {path} - ข้าม {prog}")
        continue
    full_text, pages, printed = load_ocr(path)
    predicted_courses = extract_courses(full_text)
    ocr_by_program[prog] = {
        "full_text": full_text,
        "pages": pages,
        "printed": printed,
        "predicted_courses": predicted_courses,
    }
    print(f"[extract_courses] {prog}: พบรายวิชาทั้งหมด {len(predicted_courses)} รายการจาก OCR text")


# ==========================================================
# 1) FIELD LEVEL — รายวิชา (ใช้ evaluate_courses ของ Lab เดิม)
# ==========================================================

COURSE_GT_FILES = {
    "AIT": {
        "AIT": GT_DIR / "AIT" / "AIT_academic_plan.json",
    },
    "IT": {
        "IT coop": GT_DIR / "IT" / "IT_academic_plan_coop.json",
        "IT no_coop": GT_DIR / "IT" / "IT_academic_plan_no_coop.json",
    },
    "DSBA": {
        "DSBA coop": GT_DIR / "DSBA" / "DSBA_academic_plan_coop.json",
        "DSBA no_coop": GT_DIR / "DSBA" / "DSBA_academic_plan_no_coop.json",
    },
}
GENERAL_ED_GT = GT_DIR / "general_education_ground_truth.json"

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
        field_level_courses[prog][name] = evaluate_courses(
            gt["courses"], predicted_courses, file_name=name
        )
    if GENERAL_ED_GT.exists():
        with open(GENERAL_ED_GT, "r", encoding="utf-8") as f:
            gened_gt = json.load(f)
        field_level_courses[prog][f"{prog} - หมวดศึกษาทั่วไป"] = evaluate_courses(
            gened_gt["courses"], predicted_courses, file_name=f"{prog} - หมวดศึกษาทั่วไป"
        )

# ----- ข้อบังคับ: field level = ค่าตัวเลข (GPA/หน่วยกิต) เทียบกับข้อความในหน้าที่ค้นเจอ -----
rules_path = GT_DIR / "rules_ground_truth.json"
field_level_rules = defaultdict(list)
if rules_path.exists():
    with open(rules_path, "r", encoding="utf-8") as f:
        rules_gt = json.load(f)["programs"]

    # BUG #6 FIX: loop ทุกโปรแกรม ไม่ hardcode แค่ "DSBA"
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


# ==========================================================
# 2) PAGE LEVEL — เทียบเลขหน้าที่ pipeline เจอ กับหน้าจริง
#    v2: ครบ 3 โปรแกรม (AIT / IT / DSBA) จาก Map_page_all.csv
#    (BUG #10 FIX - เดิมมีแค่ DSBA)
# ==========================================================

page_level_rows = []
map_page_path = GT_DIR / "Map_page_all.csv"

if not map_page_path.exists():
    print(f"[warn] ไม่พบ {map_page_path} - ข้าม Page Level evaluation ทั้งหมด")
else:
    with open(map_page_path, "r", encoding="utf-8-sig", newline="") as f:
        all_map_rows = list(csv.DictReader(f))

    # BUG #7 FIX: normalize program casing ("dsba"/"it" -> "DSBA"/"IT") ตอนโหลด
    for row in all_map_rows:
        row["program"] = normalize_program(row["program"])

    for prog in PAGE_LEVEL_PROGRAMS:
        if prog not in ocr_by_program:
            print(f"[warn] ไม่มี OCR ของ {prog} - ข้าม Page Level evaluation ของโปรแกรมนี้")
            continue

        ocr_pages = ocr_by_program[prog]["pages"]
        ocr_printed = ocr_by_program[prog]["printed"]

        map_rows = [r for r in all_map_rows if r["program"] == prog]
        if not map_rows:
            print(f"[warn] ไม่พบแถว ground truth เลขหน้าของ {prog} ใน {map_page_path.name}")
            continue

        for row in map_rows:
            category = row["source_gt"]
            code = row["code"].strip()
            name_th_gt = row["name_th"].strip().split("\n")[0]  # เผื่อบางแถวมีหลายบรรทัด (เช่น รหัสวิชาเลือก xxx)

            if not row["pages"].strip():
                continue  # แถวที่ยังไม่มี ground truth เลขหน้า ข้ามไป ไม่นับเป็น error

            # BUG #8 FIX: แปลง token "ocrN" -> เลขหน้าที่พิมพ์จริง ก่อนเทียบ
            gt_pages = resolve_gt_pages(row["pages"], ocr_printed)
            if not gt_pages:
                continue

            is_course = bool(re.fullmatch(r"\d{8}", code))
            needle = code if is_course else name_th_gt  # ข้อบังคับ/รายวิชาที่ไม่มีรหัส ค้นด้วยชื่อ
            needle = thai_am_fix(needle)  # BUG #3 FIX applied here too

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


# ==========================================================
# 3) CATEGORY LEVEL — สรุปรวมแยกตามหมวด, ครบทั้ง AIT / IT / DSBA
#    v2: page-level columns เติมได้ครบทั้ง 3 โปรแกรมแล้ว (ไม่ใช่แค่ DSBA)
# ==========================================================

category_summary = []

for prog in ["AIT", "IT", "DSBA"]:
    if prog not in ocr_by_program:
        continue

    # ---- แถวของแผนวิชา + หมวดศึกษาทั่วไป (จาก field_level_courses) ----
    for cat_name, result in field_level_courses.get(prog, {}).items():
        # BUG #9 FIX: แปลง cat_name ให้ตรงกับ source_gt ฝั่ง CSV ก่อนกรอง
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

    # ---- แถวของข้อบังคับ (จาก field_level_rules) ----
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
for prog, plans in field_level_courses.items():
    for name, result in plans.items():
        print(f"[{prog}] {name:24s} code_recall={result['code_recall']:.3f} "
              f"({result['codes_found']}/{result['gt_fixed_course_count']})  "
              f"credits_match={result['credits_exact_match']}/{result['credits_checked']}")

print()
for prog, rows in field_level_rules.items():
    checked = [r for r in rows if r["match"] is not None]
    acc = sum(1 for r in checked if r["match"]) / len(checked) if checked else 0
    print(f"[{prog}] {'ข้อบังคับ (ค่าตัวเลข)':24s} accuracy={acc:.3f} (n={len(checked)})")

if page_level_rows:
    print()
    print("=" * 70)
    print("PAGE LEVEL (AIT / IT / DSBA)")
    print("=" * 70)
    for prog in PAGE_LEVEL_PROGRAMS:
        rows = [r for r in page_level_rows if r["program"] == prog]
        if not rows:
            continue
        n = len(rows)
        print(f"[{prog}] n={n}  "
              f"precision={sum(r['precision'] for r in rows)/n:.3f}  "
              f"recall={sum(r['recall'] for r in rows)/n:.3f}  "
              f"f1={sum(r['f1'] for r in rows)/n:.3f}  "
              f"exact_match={sum(1 for r in rows if r['exact_match'])/n:.3f}")
    n = len(page_level_rows)
    print(f"[ALL]  n={n}  "
          f"precision={sum(r['precision'] for r in page_level_rows)/n:.3f}  "
          f"recall={sum(r['recall'] for r in page_level_rows)/n:.3f}  "
          f"f1={sum(r['f1'] for r in page_level_rows)/n:.3f}  "
          f"exact_match={sum(1 for r in page_level_rows if r['exact_match'])/n:.3f}")

if category_summary:
    print()
    print("=" * 70)
    print("CATEGORY LEVEL SUMMARY (AIT / IT / DSBA)")
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
print("บันทึกผลลัพธ์แล้วที่ outputs/eval_field_level.json, eval_page_level.csv, eval_category_summary.csv")
