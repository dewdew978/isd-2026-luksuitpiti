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

def build_reference_text_from_courses(courses: list[dict], prediction_text: str | None = None) -> str:
    matched = []
    for c in courses:
        code = c.get("code")
        name_th = c.get("name_th")
        if not code or not name_th:
            continue
        if prediction_text is not None:
            pos = prediction_text.find(code)
            if pos == -1:
                continue  # วิชานี้ไม่ได้อยู่ในหน้าที่ scan
            matched.append((pos, c))
        else:
            matched.append((0, c))

    # เรียงตามตำแหน่งที่ปรากฏจริงในหน้า ไม่ใช่ลำดับตามแผนการเรียน
    matched.sort(key=lambda x: x[0])

    lines = []
    for _, c in matched:
        credits = c.get("credits")
        name_en = c.get("name_en")
        lines.append(f"{c['code']} {c['name_th']} {credits}".strip())
        if name_en:
            lines.append(name_en.replace("\n", " "))
    return "\n".join(lines)


def evaluate_from_files(ground_truth_json: str | Path, prediction_json: str | Path) -> dict:
    with Path(ground_truth_json).open("r", encoding="utf-8") as f:
        ground_truth = json.load(f)
    with Path(prediction_json).open("r", encoding="utf-8") as f:
        prediction = json.load(f)

    source_name = Path(prediction["source_path"]).name

    if isinstance(ground_truth, dict) and "courses" in ground_truth:
        reference = build_reference_text_from_courses(ground_truth["courses"], prediction["text"])
    else:
        reference = ground_truth.get(source_name) or ground_truth.get(Path(source_name).stem)
        if reference is None:
            raise KeyError(f"No ground truth found for {source_name}")

    result = evaluate_text(reference, prediction["text"], file_name=source_name)
    return asdict(result)
