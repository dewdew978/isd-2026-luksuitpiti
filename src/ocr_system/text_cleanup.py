import re

from .schemas import OCRDocumentResult, OCRPageResult

THAI_CHAR = r"[ก-๙]"
_SPACE_BETWEEN_THAI_RE = re.compile(rf"({THAI_CHAR})\s+({THAI_CHAR})")

# คำย่อที่มักตามหลัง space จริง (ต้องคง space ไว้) เช่น "ปรับปรุง พ.ศ. 2565"
_PROTECTED_ABBR_AFTER = re.compile(r"^(พ\.ศ\.|ผศ\.|รศ\.|ดร\.|ศ\.|น\.ส\.|นาย)")
# ตัวอักษรเดี่ยวตามด้วย ) หรือจบวรรค มักเป็นป้ายลำดับข้อ เช่น "(ภาคผนวก ก)"
_LIST_LABEL_RE = re.compile(rf"^{THAI_CHAR}(?=\s*[\)\.,]|\s*$)")


def fix_thai_spacing(text: str) -> str:
    """ลบ space ปลอมที่ tesseract แทรกกลางคำไทย (เกิดจาก gap_threshold ในการจับกลุ่ม
    บรรทัดตีความระยะห่างของสระ/วรรณยุกต์ลอยผิดว่าเป็นช่องว่างระหว่างคำ)
    เว้น space ที่นำหน้าคำย่อ (พ.ศ., ผศ., ดร. ฯลฯ) และป้ายลำดับข้อ (ก)(ข)(ค) ไว้ตามเดิม
    """
    if not text:
        return text

    def try_merge(match: re.Match) -> str:
        left, right_char = match.group(1), match.group(2)
        rest = text[match.end(2):]
        candidate = right_char + rest
        if _PROTECTED_ABBR_AFTER.match(candidate):
            return match.group(0)
        if _LIST_LABEL_RE.match(candidate):
            return match.group(0)
        return left + right_char

    prev = None
    while prev != text:
        prev = text
        text = _SPACE_BETWEEN_THAI_RE.sub(try_merge, text)
    return text


def fix_document_spacing(result: OCRDocumentResult) -> OCRDocumentResult:
    """แก้ spacing ทั่วทั้ง OCRDocumentResult (text รวม + ทุกหน้า + ทุกบรรทัด) แบบ in-place"""
    result.text = fix_thai_spacing(result.text)
    for page in result.pages:
        _fix_page_spacing(page)
    return result


def _fix_page_spacing(page: OCRPageResult) -> OCRPageResult:
    page.text = fix_thai_spacing(page.text)
    for line in page.lines:
        line.text = fix_thai_spacing(line.text)
    return page