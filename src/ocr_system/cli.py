import argparse
import json
from pathlib import Path
from rich import print
from .config import OCRConfig
from .pipeline import run_ocr
from .evaluation import evaluate_from_files
from .field_extraction import (
    extract_common_fields,
    extract_courses,
    format_extraction_output,
    filter_courses_by_ground_truth,
    filter_text_by_ground_truth,
)
from .evaluation import load_ground_truth_courses
from .utils.io import save_json


def parse_args():
    parser = argparse.ArgumentParser(description="Thai-English OCR system")
    sub = parser.add_subparsers(dest="command", required=True)

    ocr = sub.add_parser("ocr", help="Run OCR on image or PDF")
    ocr.add_argument("input_path")
    ocr.add_argument("--output-dir", default="outputs")
    ocr.add_argument("--engine", choices=["paddle", "tesseract", "trocr", "ensemble"], default="ensemble")
    ocr.add_argument("--languages", default="tha+eng", help="Tesseract languages, e.g. tha+eng")
    ocr.add_argument("--paddle-lang", default="th", help="PaddleOCR language, e.g. th or en")
    ocr.add_argument("--dpi", type=int, default=300)
    ocr.add_argument("--no-preprocess", action="store_true")
    ocr.add_argument("--no-deskew", action="store_true")
    ocr.add_argument("--save-debug-images", action="store_true")
    ocr.add_argument("--min-confidence", type=float, default=0.0)
    ocr.add_argument("--device", default="cpu")

    ev = sub.add_parser("evaluate", help="Evaluate OCR JSON against ground truth JSON")
    ev.add_argument("ground_truth_json")
    ev.add_argument("prediction_json")
    ev.add_argument("--output", default="outputs/evaluation_result.json")

    ex = sub.add_parser("extract", help="Reformat an existing OCR JSON (Lab 3 output) into GT-shaped course JSON")
    ex.add_argument("ocr_json", help="Path to a *_ocr.json file produced by the 'ocr' command")
    ex.add_argument("--output", default=None, help="Where to save the extracted courses JSON (default: outputs/<stem>_extracted.json)")

    fg = sub.add_parser(
        "filter-gt",
        help="Keep only OCR text/courses that match a ground-truth file; drop everything else",
    )
    fg.add_argument("prediction_json", help="A *_ocr.json (has 'text') or *_extracted.json (has 'courses') file")
    fg.add_argument("ground_truth_json", help="Ground truth JSON, e.g. data/ground_truth/DSBA/DSBA_academic_plan_coop.json")
    fg.add_argument("--output", default=None, help="Where to save the filtered JSON (default: outputs/<stem>_filtered.json)")

    run = sub.add_parser("run", help="End-to-end: OCR -> reformat to GT shape -> (optional) evaluate")
    run.add_argument("input_path")
    run.add_argument("--output-dir", default="outputs")
    run.add_argument("--engine", choices=["paddle", "tesseract", "trocr", "ensemble"], default="ensemble")
    run.add_argument("--languages", default="tha+eng", help="Tesseract languages, e.g. tha+eng")
    run.add_argument("--paddle-lang", default="th", help="PaddleOCR language, e.g. th or en")
    run.add_argument("--dpi", type=int, default=300)
    run.add_argument("--no-preprocess", action="store_true")
    run.add_argument("--no-deskew", action="store_true")
    run.add_argument("--save-debug-images", action="store_true")
    run.add_argument("--min-confidence", type=float, default=0.0)
    run.add_argument("--device", default="cpu")
    run.add_argument("--ground-truth", default=None, help="Ground truth JSON to evaluate the OCR text against")

    return parser.parse_args()


def main():
    args = parse_args()

    if args.command == "ocr":
        output_dir = Path(args.output_dir)
        config = OCRConfig(
            input_path=Path(args.input_path),
            output_dir=output_dir,
            page_image_dir=output_dir / "pages",
            engine=args.engine,
            languages=args.languages,
            paddle_lang=args.paddle_lang,
            dpi=args.dpi,
            preprocess=not args.no_preprocess,
            deskew=not args.no_deskew,
            save_debug_images=args.save_debug_images,
            min_confidence=args.min_confidence,
            device=args.device,
        )
        result = run_ocr(config)
        fields = extract_common_fields(result.text)
        field_path = output_dir / f"{Path(args.input_path).stem}_fields.json"
        save_json(fields, field_path)
        print(f"[green]OCR done[/green]: {output_dir}")
        print(f"Extracted fields: {json.dumps(fields, ensure_ascii=False, indent=2)}")

    elif args.command == "evaluate":
        result = evaluate_from_files(args.ground_truth_json, args.prediction_json)
        save_json(result, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "extract":
        with open(args.ocr_json, "r", encoding="utf-8") as f:
            ocr_result = json.load(f)
        courses = extract_courses(ocr_result["text"])
        formatted = format_extraction_output(courses, ocr_result["source_path"], ocr_result.get("engine"))
        output_path = args.output or f"outputs/{Path(ocr_result['source_path']).stem}_extracted.json"
        save_json(formatted, output_path)
        print(f"[green]Extracted {len(courses)} course(s)[/green] -> {output_path}")

    elif args.command == "filter-gt":
        with open(args.prediction_json, "r", encoding="utf-8") as f:
            prediction = json.load(f)
        gt_courses = load_ground_truth_courses(args.ground_truth_json)

        if "courses" in prediction:
            before = len(prediction["courses"])
            filtered_courses = filter_courses_by_ground_truth(prediction["courses"], gt_courses)
            result = dict(prediction)
            result["courses"] = filtered_courses
        elif "text" in prediction:
            all_courses = extract_courses(prediction["text"])
            before = len(all_courses)
            filtered_text, filtered_courses = filter_text_by_ground_truth(prediction["text"], gt_courses)
            result = format_extraction_output(
                filtered_courses, prediction.get("source_path", args.prediction_json), prediction.get("engine")
            )
            result["text"] = filtered_text
        else:
            raise KeyError("Prediction file has neither 'courses' nor 'text' — nothing to filter.")

        stem = Path(args.prediction_json).stem
        output_path = args.output or f"outputs/{stem}_filtered.json"
        save_json(result, output_path)
        print(
            f"[green]Filtered to ground truth[/green]: kept {len(filtered_courses)} of {before} "
            f"extracted course(s) ({len(gt_courses)} real code(s) in GT) -> {output_path}"
        )

    elif args.command == "run":
        output_dir = Path(args.output_dir)
        config = OCRConfig(
            input_path=Path(args.input_path),
            output_dir=output_dir,
            page_image_dir=output_dir / "pages",
            engine=args.engine,
            languages=args.languages,
            paddle_lang=args.paddle_lang,
            dpi=args.dpi,
            preprocess=not args.no_preprocess,
            deskew=not args.no_deskew,
            save_debug_images=args.save_debug_images,
            min_confidence=args.min_confidence,
            device=args.device,
        )

        # 1) Lab 3: run OCR end to end
        result = run_ocr(config)
        stem = Path(args.input_path).stem
        ocr_json_path = output_dir / f"{stem}_ocr.json"

        # 2) Lab 4: reformat the raw OCR text into the GT course schema
        courses = extract_courses(result.text)
        formatted = format_extraction_output(courses, result.source_path, result.engine)
        extracted_path = output_dir / f"{stem}_extracted.json"
        save_json(formatted, extracted_path)
        print(f"[green]OCR done[/green]: {ocr_json_path}")
        print(f"[green]Extracted {len(courses)} course(s)[/green] -> {extracted_path}")

        # 3) Evaluate against ground truth, if provided (uses the Lab 3 evaluation code)
        if args.ground_truth:
            eval_result = evaluate_from_files(args.ground_truth, ocr_json_path)
            eval_path = output_dir / f"{stem}_evaluation_result.json"
            save_json(eval_result, eval_path)
            print(f"[green]Evaluation[/green] -> {eval_path}")
            print(json.dumps(eval_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()