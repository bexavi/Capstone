"""
Tesseract OCR fallback when a PDF has no (or almost no) extractable text layer,
or when the native text layer decodes as garbage (broken font encoding).

Requires system package: tesseract-ocr (e.g. apt install tesseract-ocr).
Optional env: DEVREOTES_PDF_OCR, DEVREOTES_PDF_OCR_NATIVE_MAX, DEVREOTES_PDF_OCR_MAX_PAGES, DEVREOTES_PDF_OCR_ZOOM.
"""

from __future__ import annotations

import io
import os
import sys


def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key, "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def ocr_dependencies_available() -> tuple[bool, str]:
    """True if pytesseract, Pillow, and tesseract binary are usable."""
    try:
        import pytesseract
        from PIL import Image  # noqa: F401

        pytesseract.get_tesseract_version()
        return True, ""
    except Exception as e:
        return False, str(e)


def _log_ocr(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


_cached_ocr_ok: bool | None = None
_cached_ocr_err: str = ""
_ocr_unavailable_logged: bool = False


def _ocr_ready() -> bool:
    global _cached_ocr_ok, _cached_ocr_err
    if _cached_ocr_ok is not None:
        return _cached_ocr_ok
    ok, err = ocr_dependencies_available()
    _cached_ocr_ok = ok
    _cached_ocr_err = err
    return ok


def extract_text_ocr_document(doc, *, max_pages: int, zoom: float) -> str:
    """Rasterize pages and run Tesseract. Page separators aid chunking downstream."""
    import fitz as _fitz
    import pytesseract
    from PIL import Image

    zm = min(max(zoom, 1.0), 3.0)
    matrix = _fitz.Matrix(zm, zm)
    parts: list[str] = []
    n = min(doc.page_count, max_pages)
    for i in range(n):
        page = doc[i]
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        try:
            text = pytesseract.image_to_string(img)
        except Exception as e:
            _log_ocr(f"  [OCR] page {i + 1} failed: {e}")
            continue
        t = (text or "").strip()
        if t:
            parts.append(f"\n\n----- Page {i + 1} -----\n\n{t}")
    if doc.page_count > max_pages:
        parts.append(
            f"\n\n[OCR truncated: {doc.page_count - max_pages} further pages not processed "
            f"(DEVREOTES_PDF_OCR_MAX_PAGES={max_pages})]\n"
        )
    return "".join(parts).strip()


def native_pdf_text_looks_corrupted(native: str) -> bool:
    """
    True when PyMuPDF returns a long stream that is mostly non-letters (broken CMap / subset fonts).

    Normal articles are ~35–80% letters; corrupted extractions can be <2% with many C0 controls.
    """
    s = native or ""
    if len(s) < 400:
        return False
    letters = sum(1 for c in s if c.isalpha())
    letter_ratio = letters / len(s)
    ctrl = sum(1 for c in s if ord(c) < 32 and c not in "\t\n\r")
    ctrl_ratio = ctrl / len(s)
    return letter_ratio < 0.04 or ctrl_ratio > 0.05


def extract_document_text_native_then_ocr(doc, label: str) -> tuple[str, bool]:
    """
    Concatenate native PyMuPDF text; if below threshold or text looks corrupted, use OCR.

    Returns (text, used_ocr_fallback).
    """
    native = ""
    for page in doc:
        native += page.get_text()
    native = native.replace("\n\n\n", "\n\n").strip()

    if not _env_bool("DEVREOTES_PDF_OCR", True):
        return native, False

    try:
        min_native = max(0, int(os.getenv("DEVREOTES_PDF_OCR_NATIVE_MAX", "80")))
    except ValueError:
        min_native = 80
    try:
        max_pages = max(1, int(os.getenv("DEVREOTES_PDF_OCR_MAX_PAGES", "60")))
    except ValueError:
        max_pages = 60
    try:
        zoom = float(os.getenv("DEVREOTES_PDF_OCR_ZOOM", "2.0"))
    except ValueError:
        zoom = 2.0

    native_sufficient = len(native) >= min_native and not native_pdf_text_looks_corrupted(native)
    if native_sufficient:
        return native, False

    if not _ocr_ready():
        global _ocr_unavailable_logged
        if not _ocr_unavailable_logged:
            _ocr_unavailable_logged = True
            _log_ocr(
                f"  [OCR] Skipping all OCR fallbacks (install tesseract-ocr + pip pytesseract Pillow). "
                f"{_cached_ocr_err or 'check tesseract on PATH'}"
            )
        return native, False

    ocr_text = extract_text_ocr_document(doc, max_pages=max_pages, zoom=zoom)
    if not ocr_text:
        _log_ocr(f"  [OCR] No text from engine ({label}); keeping native ({len(native)} chars)")
        return native, False

    _log_ocr(f"  [OCR] {label}: native={len(native)} chars -> using OCR={len(ocr_text)} chars")
    if len(native) < 20 or native_pdf_text_looks_corrupted(native):
        return ocr_text, True
    return native + "\n\n--- OCR (scanned supplement) ---\n\n" + ocr_text, True
