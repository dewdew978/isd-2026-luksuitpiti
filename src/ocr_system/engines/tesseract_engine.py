import cv2
import numpy as np
from .base import BaseOCREngine
from ocr_system.schemas import OCRLine


class TesseractOCREngine(BaseOCREngine):
    name = "tesseract"

    def __init__(self, languages: str = "tha+eng", psm: int = 6):
        import pytesseract
        self.pytesseract = pytesseract
        self.languages = languages
        self.config = f"--oem 3 --psm {psm}"

    def recognize(self, image: np.ndarray, page: int | None = None) -> list[OCRLine]:
        if len(image.shape) == 2:
            rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        else:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        data = self.pytesseract.image_to_data(
            rgb,
            lang=self.languages,
            config=self.config,
            output_type=self.pytesseract.Output.DICT,
        )
        lines: list[OCRLine] = []
        n = len(data["text"])
        line_groups: dict[tuple[int, int, int], list[dict]] = {}
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i]) / 100.0
            except ValueError:
                conf = None
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            line_groups.setdefault(key, []).append(
                {"text": text, "conf": conf, "x": x, "y": y, "w": w, "h": h}
            )

        lines: list[OCRLine] = []
        for key in sorted(line_groups.keys()):
            tokens = sorted(line_groups[key], key=lambda t: t["x"])

            avg_char_w = sum(t["w"] / max(len(t["text"]), 1) for t in tokens) / len(tokens)
            gap_threshold = max(avg_char_w * 0.6, 4)

            merged_text = tokens[0]["text"]
            for prev, cur in zip(tokens, tokens[1:]):
                gap = cur["x"] - (prev["x"] + prev["w"])
                if gap > gap_threshold:
                    merged_text += " "
                merged_text += cur["text"]

            confs = [t["conf"] for t in tokens if t["conf"] is not None]
            conf = sum(confs) / len(confs) if confs else None

            min_x = min(t["x"] for t in tokens)
            min_y = min(t["y"] for t in tokens)
            max_x = max(t["x"] + t["w"] for t in tokens)
            max_y = max(t["y"] + t["h"] for t in tokens)
            box = [[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]]

            lines.append(
                OCRLine(text=merged_text, confidence=conf, box=box, engine=self.name, page=page)
            )
        return lines
