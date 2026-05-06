"""
Text extraction for student answer uploads.

Supports:
  - PDF (typed text via PyMuPDF; falls back to OCR per page if no text layer)
  - JPG / JPEG / PNG images (OCR via pytesseract)

OCR requires the Tesseract binary on Windows. If it's not installed, PDF
text-layer extraction still works and the user gets a clear error for images.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

try:
    import fitz  # PyMuPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


SUPPORTED_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _autodetect_tesseract_cmd() -> str:
    """If Tesseract is installed but not on PATH, point pytesseract at the
    default Windows install path so users don't have to edit PATH."""
    if not TESSERACT_AVAILABLE:
        return ""
    import os
    import shutil

    # 1. Already configured?
    cur = getattr(pytesseract.pytesseract, "tesseract_cmd", "") or ""
    if cur and os.path.isfile(cur):
        return cur

    # 2. On PATH?
    found = shutil.which("tesseract")
    if found:
        pytesseract.pytesseract.tesseract_cmd = found
        return found

    # 3. Common Windows install paths
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    # Allow override via env var
    env_override = os.environ.get("TESSERACT_CMD")
    if env_override:
        candidates.insert(0, env_override)

    for path in candidates:
        if path and os.path.isfile(path):
            pytesseract.pytesseract.tesseract_cmd = path
            logger.info(f"Tesseract auto-detected at: {path}")
            return path
    return ""


# Run autodetection once at import time
_TESSERACT_CMD = _autodetect_tesseract_cmd()


def _check_tesseract_binary() -> Tuple[bool, str]:
    """Returns (available, error_message). Tesseract must be installed
    separately on Windows from https://github.com/UB-Mannheim/tesseract/wiki ."""
    if not TESSERACT_AVAILABLE:
        return False, "pytesseract not installed (pip install pytesseract)"
    try:
        pytesseract.get_tesseract_version()
        return True, ""
    except Exception as e:
        return False, (
            "Tesseract binary not found. Install it from "
            "https://github.com/UB-Mannheim/tesseract/wiki and add it to your PATH "
            "(default install path: C:\\Program Files\\Tesseract-OCR). "
            f"Underlying error: {e}"
        )


def _ocr_image_bytes(image_bytes: bytes) -> str:
    """Run OCR on raw image bytes."""
    if not PIL_AVAILABLE:
        raise Exception("Pillow is not installed")
    ok, err = _check_tesseract_binary()
    if not ok:
        raise Exception(err)
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")
    text = pytesseract.image_to_string(img)
    return (text or "").strip()


def _extract_pdf_text_layer(pdf_bytes: bytes) -> str:
    """Use PyMuPDF to extract any embedded text from a PDF (typed PDFs)."""
    if not PDF_AVAILABLE:
        raise Exception("PyMuPDF (fitz) is not installed")
    parts = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page in doc:
            t = page.get_text("text")
            if t:
                parts.append(t)
    finally:
        doc.close()
    return "\n".join(parts).strip()


def _ocr_pdf_pages(pdf_bytes: bytes, max_pages: int = 8) -> str:
    """Render each page to PNG and run OCR — used when the PDF has no text layer
    (i.e. it's a scan). Capped at `max_pages` for speed on weak hardware."""
    if not PDF_AVAILABLE:
        raise Exception("PyMuPDF (fitz) is not installed")
    ok, err = _check_tesseract_binary()
    if not ok:
        raise Exception(err)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    parts = []
    try:
        for i, page in enumerate(doc):
            if i >= max_pages:
                logger.info(f"OCR capped at {max_pages} pages — stopping early")
                break
            pix = page.get_pixmap(dpi=200)
            png_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(png_bytes))
            if img.mode != "RGB":
                img = img.convert("RGB")
            text = pytesseract.image_to_string(img) or ""
            parts.append(text.strip())
    finally:
        doc.close()
    return "\n\n".join(p for p in parts if p).strip()


def extract_text(file_bytes: bytes, filename: str) -> dict:
    """Extract text from a PDF or image upload.

    Returns:
        {
          "text": str,
          "char_count": int,
          "method": "pdf_text_layer" | "pdf_ocr" | "image_ocr",
          "page_count": int,                 # PDFs only
        }

    Raises:
        ValueError if the file extension is unsupported.
        Exception with a user-friendly message if OCR is required but unavailable.
    """
    ext = Path(filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: PDF, JPG, JPEG, PNG, WEBP, BMP."
        )

    if ext == ".pdf":
        # Try the embedded text layer first (instant if present)
        text = _extract_pdf_text_layer(file_bytes)
        if len(text) >= 30:
            return {
                "text": text,
                "char_count": len(text),
                "method": "pdf_text_layer",
            }
        # Otherwise OCR the rendered pages
        text = _ocr_pdf_pages(file_bytes)
        return {
            "text": text,
            "char_count": len(text),
            "method": "pdf_ocr",
        }

    # Image branch
    text = _ocr_image_bytes(file_bytes)
    return {
        "text": text,
        "char_count": len(text),
        "method": "image_ocr",
    }
