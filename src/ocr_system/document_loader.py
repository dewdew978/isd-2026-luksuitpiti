from pathlib import Path
from pdf2image import convert_from_path, pdfinfo_from_path
import cv2
from PIL import Image
from .utils.io import ensure_dir

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def is_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def is_pdf(path: str | Path) -> bool:
    return Path(path).suffix.lower() == ".pdf"


def pdf_to_images(pdf_path: str | Path, output_dir: str | Path, dpi: int = 300, batch_size: int = 5) -> list[Path]:
    """Rasterize a PDF to per-page JPEGs.

    Converts `batch_size` pages at a time instead of calling
    `convert_from_path(pdf_path)` on the whole document at once. At 300 DPI
    an A4 page is ~25-30MB as a decoded PIL Image, so a long document (e.g.
    400+ pages) held entirely in memory can easily reach several GB and get
    OOM-killed (seen as `zsh: killed` with no traceback, since the OS kills
    the process directly rather than raising a Python exception). Batching
    keeps peak memory bounded regardless of document length.
    """
    output_dir = ensure_dir(output_dir)
    total_pages = pdfinfo_from_path(str(pdf_path))["Pages"]

    image_paths: list[Path] = []
    for start in range(1, total_pages + 1, batch_size):
        end = min(start + batch_size - 1, total_pages)
        pages = convert_from_path(str(pdf_path), dpi=dpi, first_page=start, last_page=end)
        for offset, page in enumerate(pages):
            idx = start + offset
            out = output_dir / f"{Path(pdf_path).stem}_page_{idx:03d}.jpg"
            page.save(out, "JPEG")
            image_paths.append(out)
        del pages  # release this batch's decoded images before converting the next

    return image_paths


def load_document_pages(input_path: str | Path, output_dir: str | Path, dpi: int = 300) -> list[Path]:
    input_path = Path(input_path)
    if is_pdf(input_path):
        return pdf_to_images(input_path, output_dir, dpi=dpi)
    if is_image(input_path):
        return [input_path]
    raise ValueError(f"Unsupported file type: {input_path.suffix}")