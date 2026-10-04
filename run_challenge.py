import argparse
import json
import os
from pathlib import Path

# Import the model service from the FastAPI project
# Adjust import path if the script is run from repository root
from lab10_fastapi.curriculum_app.model_service import QwenTextToSQL


def load_questions(input_path: Path):
    """Load a list of questions from a JSON or CSV file.
    Expected JSON format: [{"question": "...", "expect": "..."}, ...]
    CSV format (optional) with headers 'question' and 'expect'.
    """
    if input_path.suffix.lower() == ".json":
        with input_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    elif input_path.suffix.lower() == ".csv":
        import csv
        with input_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [row for row in reader]
    else:
        raise ValueError("Unsupported input file type: {0}".format(input_path.suffix))


def save_results(output_path: Path, results: list):
    """Write the accumulated results to a JSON file (pretty‑printed)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Batch‑run curriculum challenge questions using the upgraded model service.")
    parser.add_argument("-i", "--input", required=True, help="Path to input JSON/CSV file containing questions.")
    parser.add_argument("-o", "--output", required=True, help="Path to output JSON file where results will be written.")
    parser.add_argument("-b", "--batch-size", type=int, default=20, help="How many results to write after each batch (default: 20).")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    questions = load_questions(input_path)
    model = QwenTextToSQL()

    results = []
    for idx, q in enumerate(questions, start=1):
        question_text = q.get("question") or q.get("prompt")
        if not question_text:
            continue
        # The model service's ask method already returns a dict with the needed fields.
        try:
            answer_dict = model.ask(question_text)
        except Exception as e:
            # Guard against unexpected crashes; embed the exception as an error field.
            answer_dict = {
                "question": question_text,
                "sql": "",
                "rows": [],
                "answer": "",
                "error": str(e),
            }
        # Preserve any expected answer from the source for later evaluation.
        if "expect" in q:
            answer_dict["expect"] = q["expect"]
        results.append(answer_dict)

        # Periodically flush results to disk so we don't lose progress on long runs.
        if idx % args.batch_size == 0:
            save_results(output_path, results)
            print(f"[✓] Saved {idx} results to {output_path}")

    # Final write of any remaining entries.
    save_results(output_path, results)
    print(f"[✓] Completed {len(results)} questions. Results stored in {output_path}")


if __name__ == "__main__":
    main()
