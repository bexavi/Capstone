import json
import re
from pathlib import Path

import fitz

from .doi_utils import concat_text_for_doi_scan, find_best_doi_in_text
from .extracted_clean import merge_title_from_lines, normalize_head_lines, skip_leading_chaff
from .paths import EXTRACTED_DIR, PAPERS_DIR, resolve_project_path
from .pdf_ocr import extract_document_text_native_then_ocr


_JUNK_TITLE_PATTERNS = [
    r"^\s*\d+\s*$",
    r"^\s*(abstract|introduction|materials\s+and\s+methods|methods|results|discussion|references)\s*$",
    r"^\s*copyright\s*",
    r"^\s*all\s+rights\s+reserved\s*$",
    r"^\s*the\s+journal\s+of\s+",
    r"^\s*doi\s*:\s*",
    r"^\s*http[s]?://",
]


def _normalize_title(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _title_from_lines(text: str, fallback: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return fallback

    candidates = lines[:50]
    best = ""
    best_score = -1
    for ln in candidates:
        t = _normalize_title(ln)
        if len(t) < 6 or len(t) > 220:
            continue
        low = t.lower()
        if any(re.search(pat, low, flags=re.IGNORECASE) for pat in _JUNK_TITLE_PATTERNS):
            continue
        letters = sum(ch.isalpha() for ch in t)
        digits = sum(ch.isdigit() for ch in t)
        symbols = sum((not ch.isalnum()) and (not ch.isspace()) for ch in t)
        score = letters - 2 * digits - 3 * symbols
        if score > best_score:
            best = t
            best_score = score

    return best[:500] if best else _normalize_title(lines[0])[:500] if lines else fallback


def _pdf_metadata_title_trusted(title: str) -> bool:
    """False for scan filenames, bare ids, section headers, etc."""
    t = _normalize_title(title)
    if len(t) < 4:
        return False
    low = t.lower()
    if low.startswith(("microsoft word", "untitled", "doc", "document")):
        return False
    if any(re.search(pat, low, flags=re.IGNORECASE) for pat in _JUNK_TITLE_PATTERNS):
        return False
    if re.search(r"\.(tif|tiff|png|jpe?g)\b", low):
        return False
    return True


def _title_from_pdf_metadata(doc: fitz.Document) -> str:
    meta = getattr(doc, "metadata", None) or {}
    title = _normalize_title(meta.get("title") or "")
    if not _pdf_metadata_title_trusted(title):
        return ""
    return title[:500]


def _title_from_body_merged(text: str) -> str:
    """Multi-line article title from the start of full text (PageGenie, PLOS, etc.)."""
    lines = normalize_head_lines(text[:50000], max_lines=120)
    if not lines:
        return ""
    start = skip_leading_chaff(lines)
    merged, _ = merge_title_from_lines(lines, start)
    m = _normalize_title(merged)
    return m[:500] if len(m) >= 12 else ""


def _pdf_meta_dict(doc: fitz.Document) -> dict:
    """PyMuPDF metadata fields (often empty; safe to store as hints)."""
    meta = getattr(doc, "metadata", None) or {}
    out = {}
    for key in ("author", "subject", "keywords", "creator", "producer", "format"):
        val = meta.get(key)
        if val and str(val).strip():
            out[f"pdf_{key}"] = _normalize_title(str(val))[:2000]
    return out


def _heuristic_bibliography(text: str) -> dict:
    """
    Best-effort DOI / year / journal from first pages of extracted text (no external APIs).
    """
    win = concat_text_for_doi_scan(text or "")
    out: dict = {"doi": None, "year": None, "journal": None}

    out["doi"] = find_best_doi_in_text(win)

    for m in re.finditer(r"\b(19[89]\d|20[0-4]\d)\b", win):
        y = int(m.group(1))
        if 1980 <= y <= 2035:
            out["year"] = y
            break

    journal_patterns = [
        r"(?:Published in|Journal(?:\s+name)?[:]\s*)([^\n.]{6,120})",
        r"^([A-Z][A-Za-z\s&\-]{8,80}(?:Journal|Letters|Proceedings|Review))\s*$",
    ]
    for pat in journal_patterns:
        jm = re.search(pat, win, re.MULTILINE)
        if jm:
            j = _normalize_title(jm.group(1))
            if 10 < len(j) < 200 and not j.lower().startswith("http"):
                out["journal"] = j[:200]
                break

    return out


def extract_record_from_pdf_path(pdf_path: Path) -> dict:
    """Build one paper JSON dict from a PDF path (does not write to disk)."""
    pdf_path = Path(pdf_path)
    paper_id = pdf_path.stem

    doc = fitz.open(str(pdf_path))
    meta_title = _title_from_pdf_metadata(doc)
    pdf_meta = _pdf_meta_dict(doc)
    full_text, used_ocr = extract_document_text_native_then_ocr(doc, pdf_path.name)
    doc.close()

    full_text = full_text.replace("\n\n\n", "\n\n").strip()
    if meta_title:
        title = meta_title
    else:
        title = _title_from_body_merged(full_text) or _title_from_lines(
            full_text[:35000], paper_id
        )
    bib = _heuristic_bibliography(full_text)

    return {
        "paper_id": paper_id,
        "title": title,
        "filename": pdf_path.name,
        "text": full_text,
        "text_via_ocr": used_ocr,
        "doi": bib.get("doi"),
        "year": bib.get("year"),
        "journal": bib.get("journal"),
        **pdf_meta,
    }


def extract_one_pdf(
    pdf_path: str | Path,
    *,
    output_dir: str | Path | None = None,
) -> dict:
    """
    Extract a single PDF into ``extracted/{paper_id}.json`` (or ``output_dir``).

    ``pdf_path`` may be a full path, or a stem like ``139`` (resolved under ``papers/``).
    """
    raw = Path(pdf_path)
    papers_path = resolve_project_path(None, PAPERS_DIR)
    if raw.is_file() and raw.suffix.lower() == ".pdf":
        target = raw.resolve()
    else:
        stem = raw.stem if raw.suffix.lower() == ".pdf" else str(raw)
        candidate = (papers_path / stem).with_suffix(".pdf")
        if not candidate.is_file():
            raise FileNotFoundError(f"PDF not found: {pdf_path!r} (tried {candidate})")
        target = candidate

    output_path = resolve_project_path(output_dir, EXTRACTED_DIR)
    output_path.mkdir(parents=True, exist_ok=True)

    output = extract_record_from_pdf_path(target)
    out_file = output_path / f"{output['paper_id']}.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(output, f)

    print(f"Extracted: {target.name} -> {out_file} ({len(output['text'])} chars, OCR={output['text_via_ocr']})")
    return output


def extract_text_from_pdfs(papers_dir: str | None = None, output_dir: str | None = None):
    papers_path = resolve_project_path(papers_dir, PAPERS_DIR)
    output_path = resolve_project_path(output_dir, EXTRACTED_DIR)
    if not papers_path.is_dir():
        raise FileNotFoundError(f"Missing papers directory: {papers_path}")

    output_path.mkdir(parents=True, exist_ok=True)
    results = []

    for pdf_path in papers_path.iterdir():
        if pdf_path.suffix.lower() != ".pdf":
            continue

        output = extract_record_from_pdf_path(pdf_path)
        out_path = output_path / f"{output['paper_id']}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(output, f)

        results.append(output)
        print(f"Extracted: {pdf_path.name} ({len(output['text'])} chars)")

    print(f"Total papers extracted: {len(results)}")
    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 2:
        extract_one_pdf(sys.argv[1])
    else:
        extract_text_from_pdfs()
