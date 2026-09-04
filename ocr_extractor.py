"""
ocr_extractor.py
-----------------
OCR + information-extraction pipeline for invoices/receipts.

Pipeline:
  1. Load the file (image or PDF -> rasterized to images).
  2. Light preprocessing (grayscale + threshold) to improve OCR accuracy.
  3. Run Tesseract OCR to get raw text.
  4. Run regex/heuristic parsers over the raw text to pull out:
       invoice_number, invoice_date, vendor, total_amount, line_items[]

This is intentionally rule-based (regex + heuristics) rather than a trained
model, which keeps the MVP dependency-light and fast to ship. The functions
are structured so the parsing step can be swapped for an LLM-based extractor
later without touching the OCR or storage layers.
"""

import io
import re
from datetime import datetime

import pytesseract
from PIL import Image, ImageOps, ImageFilter

try:
    from pdf2image import convert_from_bytes
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False


# --------------------------------------------------------------------------
# 1. Loading & preprocessing
# --------------------------------------------------------------------------

def load_images_from_file(file_bytes: bytes, filename: str) -> list[Image.Image]:
    """Return a list of PIL Images for a given uploaded file (PDF or image)."""
    ext = filename.lower().split(".")[-1]
    if ext == "pdf":
        if not PDF_SUPPORT:
            raise RuntimeError("pdf2image/poppler not available for PDF parsing.")
        return convert_from_bytes(file_bytes, dpi=300)
    else:
        img = Image.open(io.BytesIO(file_bytes))
        return [img.convert("RGB")]


def preprocess_image(img: Image.Image) -> Image.Image:
    """Grayscale + slight sharpening + binarization to help Tesseract."""
    gray = ImageOps.grayscale(img)
    gray = gray.filter(ImageFilter.SHARPEN)
    # simple adaptive-ish threshold
    bw = gray.point(lambda x: 0 if x < 150 else 255, mode="1")
    return bw


def ocr_image(img: Image.Image) -> str:
    processed = preprocess_image(img)
    config = "--oem 3 --psm 6"
    return pytesseract.image_to_string(processed, config=config)


def ocr_file(file_bytes: bytes, filename: str) -> str:
    """Run OCR over every page/image of a file and concatenate the text."""
    images = load_images_from_file(file_bytes, filename)
    texts = [ocr_image(img) for img in images]
    return "\n".join(texts)


# --------------------------------------------------------------------------
# 2. Field extraction (regex / heuristics)
# --------------------------------------------------------------------------

DATE_PATTERNS = [
    r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b",
    r"\b(\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2})\b",
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b",
]

INVOICE_NO_PATTERNS = [
    r"(?:invoice|inv|bill)\s*(?:no\.?|number|#|:)?\s*[:#]?\s*([A-Z0-9\-\/]{3,20})",
    r"(?:receipt)\s*(?:no\.?|number|#|:)?\s*[:#]?\s*([A-Z0-9\-\/]{3,20})",
]

TOTAL_PATTERNS = [
    r"(?:grand\s*total|total\s*amount|total\s*due|total)\s*[:\$]?\s*\$?\s*([\d,]+\.\d{2})",
    r"(?:grand\s*total|total\s*amount|total\s*due|total)\s*[:\$]?\s*\$?\s*([\d,]+)",
]

VENDOR_STOPWORDS = {"invoice", "receipt", "bill", "date", "total", "tax"}


def _clean_amount(raw: str) -> float | None:
    if not raw:
        return None
    try:
        return float(raw.replace(",", "").strip())
    except ValueError:
        return None


def extract_invoice_number(text: str) -> str | None:
    for pat in INVOICE_NO_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def extract_date(text: str) -> str | None:
    for pat in DATE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1)
            return _normalize_date(raw)
    return None


def _normalize_date(raw: str) -> str:
    """Try a handful of common formats; fall back to returning raw text."""
    fmts = [
        "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y",
        "%d/%m/%y", "%m/%d/%y", "%Y-%m-%d", "%Y/%m/%d",
        "%d %b %Y", "%d %B %Y",
    ]
    for f in fmts:
        try:
            return datetime.strptime(raw, f).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def extract_vendor(text: str) -> str | None:
    """
    Heuristic: the vendor name is usually one of the first non-empty lines
    at the top of the document that isn't a generic header word.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines[:6]:
        lower = line.lower()
        if any(sw in lower for sw in VENDOR_STOPWORDS):
            continue
        if len(line) < 3:
            continue
        if re.match(r"^\d+$", line):
            continue
        return line
    return lines[0] if lines else None


def extract_total(text: str) -> float | None:
    for pat in TOTAL_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = _clean_amount(m.group(1))
            if val is not None:
                return val
    # fallback: largest currency-looking number in the doc
    amounts = re.findall(r"\$?\s?([\d,]+\.\d{2})", text)
    amounts = [_clean_amount(a) for a in amounts]
    amounts = [a for a in amounts if a is not None]
    return max(amounts) if amounts else None


LINE_ITEM_PATTERN = re.compile(
    r"^(?P<product>[A-Za-z][A-Za-z0-9 &\-'./]{2,40}?)\s+"
    r"(?P<qty>\d+(?:\.\d+)?)\s+"
    r"(?:x\s*)?\$?(?P<price>[\d,]+\.\d{2})\s+"
    r"\$?(?P<lt>[\d,]+\.\d{2})\s*$"
)


def extract_line_items(text: str) -> list[dict]:
    """
    Heuristic line-item parser: looks for lines shaped like
      "Product name   qty   unit_price   line_total"
    Any line that doesn't match this shape is skipped -- OCR noise on
    line items is common, so this degrades gracefully (empty list) rather
    than raising.
    """
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = LINE_ITEM_PATTERN.match(line)
        if m:
            qty = _clean_amount(m.group("qty"))
            price = _clean_amount(m.group("price"))
            line_total = _clean_amount(m.group("lt"))
            items.append({
                "product": m.group("product").strip(),
                "quantity": qty,
                "unit_price": price,
                "line_total": line_total,
            })
    return items


# --------------------------------------------------------------------------
# 3. Public entry point
# --------------------------------------------------------------------------

def extract_invoice_data(file_bytes: bytes, filename: str) -> dict:
    """Full pipeline: OCR the file, then parse out structured fields."""
    raw_text = ocr_file(file_bytes, filename)

    data = {
        "source_file": filename,
        "raw_text": raw_text,
        "invoice_number": extract_invoice_number(raw_text),
        "invoice_date": extract_date(raw_text),
        "vendor": extract_vendor(raw_text),
        "total_amount": extract_total(raw_text),
        "line_items": extract_line_items(raw_text),
    }
    return data
