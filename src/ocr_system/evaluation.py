import json
import re
from pathlib import Path
from dataclasses import dataclass, asdict
from jiwer import wer
import Levenshtein


@dataclass
class EvaluationResult:
    file: str
    cer: float
    wer: float
    exact_match: bool
    reference_chars: int
    prediction_chars: int


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


def normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def char_error_rate(reference: str, prediction: str) -> float:
    ref = normalize_text(reference).replace(" ", "")
    hyp = normalize_text(prediction).replace(" ", "")
    if not ref:
        return 0.0 if not hyp else 1.0
    return Levenshtein.distance(ref, hyp) / len(ref)


def evaluate_text(reference: str, prediction: str, file_name: str = "") -> EvaluationResult:
    ref = normalize_text(reference)
    hyp = normalize_text(prediction)
    return EvaluationResult(
        file=file_name,
        cer=char_error_rate(ref, hyp),
        wer=wer(ref, hyp) if ref else (0.0 if not hyp else 1.0),
        exact_match=ref == hyp,
        reference_chars=len(ref),
        prediction_chars=len(hyp),
    )


# ---------------------------------------------------------------------------
# Ground-truth course filtering
# ---------------------------------------------------------------------------
#
# GT course-plan files (e.g. DSBA_academic_plan_coop.json) mix two kinds of
# rows that must NOT be treated as "codes an extractor should have found":
#
#   1. Placeholder / elective slots with no fixed code, e.g. "90644xxx",
#      "9064xxxx", "06026xxx", "xxxxxxxx", or combined choices like
#      "06026259 หรือ 06026260". These represent "pick a course from this
#      group" rather than a specific course, so no single extracted code can
#      ever satisfy them.
#   2. Stray non-course rows, e.g. a trailing spreadsheet footnote that got
#      exported as if it were a course record (a `code` field containing a
#      long Thai sentence rather than a course number).
#
# Comparing an extractor's output against these rows always fails and tells
# you nothing about extraction quality, so they're filtered out before any
# comparison happens.

_REAL_CODE_RE = re.compile(r"^\d{8}$")


def is_real_course_code(code: str | None) -> bool:
    """True only for an unambiguous, single, fixed 8-digit course code.

    Rejects: None/empty, placeholders containing "x"/"X", combined
    "A หรือ B" entries, footnote rows, and anything not exactly 8 digits.
    """
    if not code:
        return False
    return bool(_REAL_CODE_RE.fullmatch(code.strip()))


def load_ground_truth_courses(ground_truth_json: str | Path) -> list[dict]:
    """Load a GT course-plan file and return only rows with a real, fixed
    course code — i.e. the set of codes an extractor could plausibly be
    scored against."""
    with Path(ground_truth_json).open("r", encoding="utf-8") as f:
        data = json.load(f)
    courses = data["courses"] if isinstance(data, dict) and "courses" in data else data
    return [c for c in courses if is_real_course_code(c.get("code"))]


# ---------------------------------------------------------------------------
# Reference-text construction (for the CER/WER text-diff path)
# ---------------------------------------------------------------------------

def build_reference_text_from_courses(courses: list[dict], prediction_text: str | None = None) -> str:
    """Build a reference transcript from GT course rows, ordered to match
    the order courses actually appear in the scanned page (when
    `prediction_text` is given), so CER/WER measures OCR quality rather than
    penalizing correct text that's merely in a different order.

    Only rows with a real, fixed code are considered — placeholder/footnote
    rows can't be located in `prediction_text` and would otherwise be
    silently (and confusingly) dropped from the reference with no signal
    that anything was skipped.
    """
    real_courses = [c for c in courses if is_real_course_code(c.get("code"))]

    matched = []
    for c in real_courses:
        code = c["code"]
        name_th = c.get("name_th")
        if not name_th:
            continue
        if prediction_text is not None:
            pos = prediction_text.find(code)
            if pos == -1:
                continue  # course not found on the scanned page/prediction
            matched.append((pos, c))
        else:
            matched.append((0, c))

    # Order by where each course actually appears in the page, not by plan
    # order, since OCR text follows reading order.
    matched.sort(key=lambda x: x[0])

    lines = []
    for _, c in matched:
        credits = c.get("credits")
        name_en = c.get("name_en")
        lines.append(f"{c['code']} {c['name_th']} {credits}".strip())
        if name_en:
            lines.append(name_en.replace("\n", " "))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Course-level evaluation (code recall / credits accuracy)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def evaluate_from_files(ground_truth_json: str | Path, prediction_json: str | Path) -> dict:
    """Evaluate a prediction file against a ground-truth course-plan file.

    Dispatches to one of two evaluation modes depending on what the
    prediction file actually contains:

      - If it has a top-level "courses" list (the shape produced by
        `extract.extract_courses` / `format_extraction_output`), run the
        course-level comparison (`evaluate_courses`): code recall +
        credits accuracy against the GT's fixed (non-placeholder) codes.
        This is the metric that matches how this pipeline's extractor is
        actually structured, and doesn't require a "text"/"source_path"
        field that the extractor doesn't produce.

      - Otherwise, fall back to the original raw-OCR-text CER/WER path,
        which expects {"text": ..., "source_path": ...} and a GT file keyed
        by filename (or a "courses" GT to build a reference transcript
        from).
    """
    with Path(ground_truth_json).open("r", encoding="utf-8") as f:
        ground_truth = json.load(f)
    with Path(prediction_json).open("r", encoding="utf-8") as f:
        prediction = json.load(f)

    file_name = Path(prediction.get("source_path", prediction_json)).name

    # --- Course-level path (matches this project's extractor output) -----
    if isinstance(prediction, dict) and "courses" in prediction:
        if not (isinstance(ground_truth, dict) and "courses" in ground_truth):
            raise ValueError(
                "Prediction file has a 'courses' list but ground truth "
                "file does not — course-level evaluation needs a GT file "
                "shaped like data/ground_truth/*.json."
            )
        gt_courses = ground_truth["courses"]
        return evaluate_courses(gt_courses, prediction["courses"], file_name=file_name)

    # --- Legacy text-based CER/WER path -----------------------------------
    if "text" not in prediction:
        raise KeyError(
            "Prediction file has neither 'courses' nor 'text' — nothing to evaluate."
        )

    prediction_text = prediction["text"]

    if isinstance(ground_truth, dict) and "courses" in ground_truth:
        if "pages" in prediction and isinstance(prediction["pages"], list):
            gt_codes = {c["code"] for c in ground_truth["courses"] if is_real_course_code(c.get("code"))}
            relevant_texts = []
            for page in prediction["pages"]:
                page_text = page.get("text", "")
                if any(code in page_text for code in gt_codes):
                    relevant_texts.append(page_text)
            
            if relevant_texts:
                prediction_text = "\n".join(relevant_texts)

        reference = build_reference_text_from_courses(ground_truth["courses"], prediction_text)
    else:
        reference = ground_truth.get(file_name) or ground_truth.get(Path(file_name).stem)
        if reference is None:
            raise KeyError(f"No ground truth found for {file_name}")

    result = evaluate_text(reference, prediction_text, file_name=file_name)
    return asdict(result)