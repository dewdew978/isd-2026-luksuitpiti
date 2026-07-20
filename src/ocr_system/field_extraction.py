import re
from pathlib import Path


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
_WATERMARK_LINE_RE = re.compile(r"^[^\wก-๙]{6,}$|^(?:[A-Za-z]{1,3}){4,}$")


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