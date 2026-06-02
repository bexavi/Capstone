"""
Post-process extracted paper JSON: normalize head parsing, optional metadata fixes, report.

Does not overwrite Crossref-enriched bibliographic fields unless explicitly allowed.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .crossref_metadata import crossref_structured_authors_to_display_names
from .doi_utils import concat_text_for_doi_scan, find_best_doi_in_text

# Lines dropped when building the logical "front matter" view
_PAGE_MARKER_RE = re.compile(r"^[\s\-]*page\s+\d+[\s\-]*$", re.IGNORECASE)
_PAGE_MARKER_RE2 = re.compile(r"^\-+\s*Page\s+\d+\s*\-+\s*$", re.IGNORECASE)

_BOILERPLATE_SUBSTR = (
    "jstor",
    "terms and conditions",
    "stable url",
    "your use of the jstor",
    "each copy of any part",
    "printed page of such",
    "publisher for further permissions",
    "trademark office",
    "jstor-info@",
    "http://",
    "https://",
    "www.jstor.org",
    "obtained prior permission",
    "personal, non-commercial",
    "contact information may be obtained",
    "is published by national",
)

_EXTRA_JUNK_TITLE_SUBSTR = (
    "jstor transmission",
    "virtual copier",
    "microsoft word",
    "acrobat",
)


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def sanitize_pdf_extracted_text(text: str | None) -> str:
    """
    Fix common PDF text-extraction artifacts: C0 controls, Adobe PUA glyphs,
    and misplaced G-protein / cAMP prime notation (seen in MBC / Dev Cell PDFs).

    Does not recover titles when the underlying extraction is mostly non-text (e.g. broken font encoding).
    """
    if not text:
        return ""
    s = str(text)
    # Gβγ before Gβ / Gα so we do not leave stray control bytes.
    s = s.replace("G\x02\x01", "Gβγ")
    s = s.replace("G\x01\x02", "Gαβ")
    s = re.sub(r"G\x03(?=[\s\-‑–—])", "Gγ", s)
    s = re.sub(r"G\x02(?=[\s\-‑–—])", "Gβ", s)
    s = re.sub(r"G\x01(?=[\s\-‑–—])", "Gα", s)
    s = s.replace("G\x03", "Gγ")
    s = s.replace("G\x02", "Gβ")
    s = s.replace("G\x01", "Gα")
    # 3′,5′-cAMP style: digit + C1 control used as prime
    s = re.sub(r"(\d)\x01,\s*(\d)\x01", r"\1′, \2′", s)
    s = re.sub(r"(\d)\x01-(\d)\x01", r"\1′-\2′", s)
    s = re.sub(r"(\d)\x01-(?=[a-zA-Z])", r"\1′-", s)
    # Adobe CID / symbol fallback to PUA (e.g. superscript © before year)
    s = s.replace("\uf8e9", "©")
    s = "".join(ch for ch in s if not (0xF8E0 <= ord(ch) <= 0xF8FF))
    # Drop remaining C0 controls except TAB / LF / CR
    s = "".join(ch for ch in s if ord(ch) >= 32 or ch in "\t\n\r")
    return s


def crossref_enrichment_ok(paper_data: dict) -> bool:
    cr = paper_data.get("crossref")
    return isinstance(cr, dict) and "error" not in cr


def metadata_title_is_junk(title: str | None) -> bool:
    if not title or not str(title).strip():
        return True
    t = str(title).strip()
    if len(t) < 6:
        return True
    if any(ord(c) < 9 or (ord(c) > 13 and ord(c) < 32) for c in t):
        return True
    # Broken font encoding: C0 strip leaves long strings of punctuation / digits only
    if len(t) >= 24:
        letters = sum(1 for c in t if c.isalpha())
        if letters < 10 or letters / len(t) < 0.12:
            return True
    low = t.lower()
    if re.search(r"\.(tif|tiff|png|jpe?g|gif|pdf)\b", low):
        return True
    if re.match(r"^\s*PII:\s*", t, re.I):
        return True
    if re.match(r"^se\d+p\s*$", t, re.I):
        return True
    if any(x in low for x in _EXTRA_JUNK_TITLE_SUBSTR):
        return True
    if "jstor" in low and len(t) > 40:
        return True
    if low.startswith("each copy of any part"):
        return True
    if low.startswith("of ") and len(t) < 55:
        return True
    # Library / scan slip sheet (OCR first page)
    if re.search(r"call\s+qh\b|datereq:|date\s+ree:|number:\s*date|location:\s*\w", low):
        return True
    if re.search(r"\.indd\b|n&v\s+final", low):
        return True
    if re.search(r"conditional\s+title:|location:.*ver:\s*jhw", low):
        return True
    if re.search(r"nature\s+cell\s+biology\s+volume\s+\d+\s*\|", low):
        return True
    return False


def strip_page_markers_from_text(text: str) -> str:
    """Remove OCR page banner lines; collapse excessive newlines."""
    if not text:
        return ""
    lines_out = []
    for ln in text.splitlines():
        s = ln.strip()
        if _PAGE_MARKER_RE2.match(s) or _PAGE_MARKER_RE.match(s):
            continue
        lines_out.append(ln)
    out = "\n".join(lines_out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def normalize_head_lines(text: str, max_lines: int = 140) -> list[str]:
    """Non-empty lines from the start of text, skipping OCR page markers."""
    out: list[str] = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if _PAGE_MARKER_RE2.match(s) or _PAGE_MARKER_RE.match(s):
            continue
        if _is_boilerplate_line(s):
            continue
        if _is_ill_library_slip_line(s):
            continue
        if _is_low_value_heading_line(s):
            continue
        if re.fullmatch(r"\d{1,3}", s.strip()):
            continue
        out.append(s)
        if len(out) >= max_lines:
            break
    return out


def _is_boilerplate_line(s: str) -> bool:
    low = s.lower()
    return any(b in low for b in _BOILERPLATE_SUBSTR)


def _is_ill_library_slip_line(s: str) -> bool:
    """Interlibrary loan / catalog sticker lines (often OCR page 1)."""
    low = s.lower().strip()
    if re.search(
        r"call\s+qh\b|ill:\s*\d|datereq:|date\s+ree:|borrower:|lenderstring:|maxcost:|"
        r"^number:\s*date|^location:\s*borrower|conditional\s+ill:",
        low,
    ):
        return True
    if re.match(r"^title:\s*current biology\b", low):
        return True
    if low.startswith("edition:") and "imprint:" in low:
        return True
    if re.match(r"^author:\s*$", low):
        return True
    if re.match(r"^\d+\s+american zoologist", low):
        return True
    if re.search(r"^date\s+rec:", low):
        return True
    if low.startswith("imprint:"):
        return True
    if re.fullmatch(r"tional", low):
        return True
    if re.match(r"^borrowing\s+qh\b", low):
        return True
    if re.match(r"^notes:\s*$", low):
        return True
    if re.match(r"^edition:\s*$", low):
        return True
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}\s+yes\s*$", low):
        return True
    if re.search(r"number:\s*\.|conditional\s+title:", low):
        return True
    if re.search(r"^location:.*jhw\s+conditional", low):
        return True
    return False


def _is_low_value_heading_line(s: str) -> bool:
    """Section banners that are not article title lines (OCR page 1)."""
    low = s.lower().strip()
    if low == "news and views":
        return True
    if re.match(r"^jan\s+n&v\s+final", low):
        return True
    if re.search(r"nature\s+cell\s+biology\s+volume\s+\d+", low) and "|" in s:
        return True
    return False


def _is_journal_chaff(s: str) -> bool:
    raw = s.strip()
    low = raw.lower().rstrip(",.")
    if len(raw) <= 2:
        return True
    if re.fullmatch(r"vol\.?", low):
        return True
    if re.fullmatch(r"cell\.?", low):
        return True
    if re.match(r"^io,\s*\d", low):
        return True
    if re.fullmatch(r"\d{1,2},\s*\d{3}-\d{3}", low):
        return True
    if re.fullmatch(r"\d{4}", raw):
        return True
    if low in ("march", "january", "february", "april", "may", "june", "july", "august", "september", "october", "november", "december"):
        return len(raw) < 12
    if low.startswith("copyright"):
        return True
    if low.startswith("by mit"):
        return True
    if re.match(r"^0\s*\d{4}\b", raw):
        return True
    if re.match(r"^vol\.\s*\d", low):
        return True
    return False


def skip_leading_chaff(lines: list[str]) -> int:
    i = 0
    while i < len(lines) and _is_journal_chaff(lines[i]):
        i += 1
    return i


def _is_roman_section_subtitle_line(s: str) -> bool:
    """e.g. 'II. Requirements for the Initiation and Termination' — not an author byline."""
    t = s.strip()
    if re.match(r"^(?:Part\s+)?[IVXLC]{1,6}\.\s+\S", t, re.I):
        return True
    if re.match(r"^\d+\.\s+[A-Za-z]", t) and len(t) > 25 and " and " in t.lower():
        return True
    return False


def _line_looks_like_authors_start(s: str) -> bool:
    """First author token in journal style: DOUGLAS M. FAMBROUGH or PETER N. DEVREOTES"""
    t = s.strip()
    return bool(re.match(r"^[A-Z]{2,}\s+[A-Z]\.\s+[A-Z][A-Za-z'\-]*", t))


def _line_is_oxford_three_author(s: str) -> bool:
    """e.g. 'Ning Zhang, Yu Long, and Peter N. Devreotes' or 'Miho Iijima, Yi Elaine Huang, and Peter Devreotes1'."""
    ch = r"(?:[A-Z][a-z]+\s+)+[A-Z][a-zA-Z'\-\u2019]+\d*"
    return bool(re.search(rf"{ch}\s*,\s*{ch}\s*,\s+and\s+[A-Z]", s))


def _is_byline_line(s: str) -> bool:
    low = s.lower().strip()
    if len(s) > 220 or len(s) < 8:
        return False
    if _is_roman_section_subtitle_line(s):
        return False
    if any(
        x in low
        for x in (
            "requirements for the initiation",
            "termination of the response",
        )
    ):
        return False
    if any(
        x in low
        for x in (
            "received for publication",
            "revised form",
            "copyright",
            "stable url",
            "terms and conditions",
            "figure ",
            "fig. ",
            "cells moving",
            "alex and simon",
        )
    ):
        return False
    if re.search(r"\s+and(?:\s+|$)", s, re.I) and re.match(r"^[A-Z]", s.strip()):
        if s.count(",") > 10:
            return False
        # Titles: "Foo, Bar, and Baz" — not "Smith, J. and Jones"
        if re.search(r",\s+and(?:\s+|$)", s, re.I):
            if _line_is_oxford_three_author(s):
                return True
            return False
        # Author lists: comma-separated names before final " and " (line may end at "and")
        if re.search(r",\s*.+\s+and(?:\s+|$)", s, re.I):
            # Not "(3,4,5)P3 and directed" or news-style deck headlines
            if not (
                re.search(r"\(\s*\d\s*,\s*\d", s)
                or "ptdins" in low
                or "leading-edge" in low
            ):
                return True
        if _line_looks_like_authors_start(s):
            return True
        # Two-name byline: "Pamela J. Lilly and Peter N. Devreotes"
        if (
            len(s) < 130
            and s.count(",") <= 2
            and re.search(
                r"[A-Z][a-z]+\s+[A-Z]\.\s+[A-Za-z\-'\u2019]+\s+and\s+[A-Z][a-z]",
                s,
            )
        ):
            return True
        return False
    # PLOS-style byline: surnames with footnote digits, e.g. "Shi1, Chuan-Hsiang Huang2, Peter N. Devreotes"
    if len(s) < 400 and s.count(",") >= 2 and re.search(
        r"[A-Za-z]\d{1,2}\s*,\s*[A-Z]", s
    ):
        return True
    if ";" in s and len(s) < 300:
        parts = [p for p in s.split(";") if len(p.strip()) > 3]
        if len(parts) >= 2:
            return True
    return False


def _is_affiliation_or_section_start(s: str) -> bool:
    low = s.lower()
    if low.startswith(("from the", "department", "abstract", "summary")):
        return True
    if low.startswith("abstract—") or low.startswith("abstract-"):
        return True
    return False


def _is_proceedings_banner(s: str) -> bool:
    return "proceedings of the national academy" in s.lower() and len(s) > 70


def _looks_like_split_author_block(lines: list[str], i: int) -> bool:
    """e.g. Peter / N. / Devreotes / Department of ..."""
    if i + 3 >= len(lines):
        return False
    a, b, c = lines[i].strip(), lines[i + 1].strip(), lines[i + 2].strip()
    if not a or not b or not c:
        return False
    if not re.match(r"^[A-Z][a-zA-Z\-]{1,20}$", a.split()[0]):
        return False
    if not re.match(r"^[A-Z]\.?$", b):
        return False
    if len(c) > 45 or len(c.split()) > 3:
        return False
    if not re.match(r"^[A-Z]", c):
        return False
    nxt = lines[i + 3].lower() if i + 3 < len(lines) else ""
    if nxt.startswith(("department", "from the", "abstract", "summary")):
        return True
    return False


def _looks_like_two_line_author(lines: list[str], i: int) -> bool:
    """e.g. Peter / N. Devreotes / Department (OCR merged middle + surname)"""
    if i + 2 >= len(lines):
        return False
    a, b = lines[i].strip(), lines[i + 1].strip()
    if not a or not b:
        return False
    if not re.match(r"^[A-Z][a-zA-Z\-]{1,20}$", a.split()[0]):
        return False
    if not re.match(r"^[A-Z]\.\s+[A-Za-z]", b):
        return False
    if len(b) > 50:
        return False
    nxt = lines[i + 2].lower() if i + 2 < len(lines) else ""
    if nxt.startswith(("department", "from the", "abstract", "summary")):
        return True
    return False


def merge_title_from_lines(lines: list[str], start: int) -> tuple[str, int]:
    """
    Merge title lines starting at start; return (title, index_after_title).
    """
    parts: list[str] = []
    i = start
    n = len(lines)
    while i < n:
        if _looks_like_split_author_block(lines, i) or _looks_like_two_line_author(lines, i):
            break
        ln = lines[i]
        if _is_boilerplate_line(ln):
            i += 1
            continue
        up = ln.upper()
        if up.startswith("ABSTRACT") or up.startswith("SUMMARY"):
            break
        if _is_roman_section_subtitle_line(ln):
            parts.append(_strip_title_noise(ln))
            i += 1
            continue
        if _line_looks_like_authors_start(ln) and parts:
            break
        if _is_byline_line(ln) or _is_affiliation_or_section_start(ln):
            break
        if _is_proceedings_banner(ln) and parts:
            break
        if len(ln) > 120:
            parts.append(_strip_title_noise(ln))
            i += 1
            break
        # Stop columnar run if a "long prose" line appears after we already have chunks
        if parts and len(ln.split()) > 14:
            break
        parts.append(_strip_title_noise(ln))
        i += 1
        # Two-line classic title (ALL CAPS) often ends before byline on next iteration
        if i < n and _is_byline_line(lines[i]):
            break
    title = _normalize_ws(" ".join(parts))
    return title[:500], i


def _strip_title_noise(s: str) -> str:
    s = re.sub(r"(?i)^title:\s*", "", s)
    s = re.sub(r"['\u2019]+\s*:\??\s*$", "", s)
    return s.strip()


def _looks_like_person_name_chunk(c: str) -> bool:
    c = c.strip()
    if len(c) < 5 or len(c) > 90:
        return False
    if not re.match(r"^[A-Z\u00c0-\u024f]", c):
        return False
    low = c.lower()
    bad = (
        "department",
        "university",
        "laboratory",
        "institute",
        "school of",
        "genetics unit",
        "zoological",
        "philadelphia",
        "baltimore",
        "wolfe street",
        "current biology",
        "nanobiology",
        "graduate school",
        "biology department",
        "et al",
        "fax",
        "homology domain",
        "springer",
        "geneticin",
        "submitted",
        "accepted",
        "imprint",
        "edition",
        "received",
        "publication",
        "revised",
        "copyright",
        "figure",
        "journal",
        "review",
        "meta-analysis",
        "news",
        "views",
        "provided for",
        "non-commercial",
        "open access",
        "licensee",
        "http",
    )
    if any(b in low for b in bad):
        return False
    letters = sum(ch.isalpha() for ch in c)
    if letters < max(4, len(c) // 4):
        return False
    return True


def _collapse_spaced_caps_runs(s: str) -> str:
    """OCR: 'T H E O D O R E L. STECK' -> 'THEODORE L. STECK' (runs of single-letter caps)."""

    def _collapse(m: re.Match) -> str:
        return re.sub(r"\s+", "", m.group(0))

    return re.sub(r"\b(?:[A-Z]\s+){3,}[A-Z]\b", _collapse, s)


def _stored_authors_look_invalid(authors: Any) -> bool:
    if not isinstance(authors, list) or not authors:
        return True
    for a in authors:
        if not isinstance(a, str):
            return True
        low = a.lower()
        if any(
            x in low
            for x in (
                "requirements for the initiation",
                "termination of the response",
                "initiation and termination",
            )
        ):
            return True
        if _author_string_should_drop(a):
            return True
    return False


def _strip_inline_author_footnotes(s: str) -> str:
    """Remove journal-style superscript/footnote markers between author names (e.g. ', 1 Charles', ', 2'3 Rachel')."""
    s = _normalize_ws(s)
    if not s:
        return s
    s = re.sub(r",\s*\d+'?\d*\s+(?=[A-Z][a-z])", ", ", s)
    # ", 2 and Peter N." (Genes & Dev.) -> " and Peter N."
    s = re.sub(r",\s*\d+\s+and\s+(?=[A-Z])", " and ", s, flags=re.I)
    s = re.sub(r"\s+(?:\d{1,2}'\d{1,2}|\d{1,2})\s*$", "", s)
    return _normalize_ws(s)


def _fix_author_ocr_token(name: str) -> str:
    n = name.strip()
    if "Milne9" in n:
        n = n.replace("Milne9", "Milne")
    if "Milned" in n:
        n = n.replace("Milned", "Milne")
    if "Caterinat" in n:
        n = n.replace("Caterinat", "Caterina")
    if " " in n and re.search(r"[A-Za-z]\d+$", n):
        n = re.sub(r"\d+$", "", n)
    n = re.sub(r",\s*\d+(?:\s*,\s*\d+)*\s*$", "", n)
    n = re.sub(r"(?<=[A-Za-z])\d+(?:,\d+)*$", "", n)
    return n


def _author_string_should_drop(t: str) -> bool:
    """Affiliations, citations, and title fragments mistaken for author names."""
    s = (t or "").strip()
    if len(s) < 3:
        return True
    low = s.lower()
    if re.search(
        r"department of|university of|school of medicine|laboratory of|graduate school|"
        r"wolfe street|philadelphia,\s*pennsylvania|current biology|zoological laboratory|"
        r"genetics unit|nanobiology|biology department,\s*university",
        low,
    ):
        return True
    if low == "school of medicine":
        return True
    if len(s) > 70 and re.search(r"\b(md|pa)\b", low) and re.search(r"\d{5}", s):
        return True
    if re.search(r"\bet al\b|\)\.\s*it is\b|jin et al", low):
        return True
    if re.search(r"^the and ", low):
        return True
    if re.search(r"^is required for\b", low):
        return True
    if "wepartment" in low:
        return True
    if re.search(r"fax:|tel:\s*\d|e-mail:\s*\d", low):
        return True
    if re.search(r"\bsan diego\b|\bla jolla\b", low):
        return True
    if re.search(r"^the johns hopkins\b|\bjohns hopkins univ", low):
        return True
    if "homology domain" in low:
        return True
    if low in ("article", "imprint", "edition", "berlin", "london", "new york"):
        return True
    if re.search(r"\bspringer\b|¢\s*19\d{2}|¢\s*20\d{2}", low):
        return True
    if re.search(r"^submitted\b|^accepted\b", low):
        return True
    if re.search(r"\bmaryland\s+\d{5}\b|^\d{5}$", low):
        return True
    if re.search(r"\bg418\b|\bgeneticin\b", low):
        return True
    if re.search(r"ptdins|p\s*\(\s*3\s*,\s*4\s*,\s*5\s*\)", low):
        return True
    if re.search(r",\s*eds\.?\s*$|\beds\.?\s*$", low):
        return True
    if re.search(r"^plants,\s*", low):
        return True
    if re.search(r"^j\.\s+and\s+devreotes\b", low):
        return True
    if re.search(r"\baimless\s+rasgef\b|rasgef\s+is\s+required", low):
        return True
    if re.search(r"processing of chemotactic", low) and len(s) > 35:
        return True
    if re.search(r"leading-edge|leading edge research", low):
        return True
    if re.search(r"\bc\s*a\s*r\s*,\s*camp\b|\bcamp\s+receptor\b", low):
        return True
    if re.search(r"comparative biology\s*\[|society for integrative", low):
        return True
    return False


def _repair_author_string(name: str) -> str:
    """OCR / PDF glue fixes before validation."""
    n = _normalize_ws(name).strip()
    if not n:
        return ""
    n = re.sub(r"^Ls\s+", "", n, flags=re.I)
    n = re.sub(r"^Dictyostelium\s+", "", n, flags=re.I)
    n = re.sub(r"\b\d{3,}\.\s*", "", n)
    n = re.sub(r"\b([A-Z])\.([A-Z][a-z]{2,})\b", r"\1. \2", n)
    n = re.sub(r"\s+From the\s+.*$", "", n, flags=re.I)
    n = re.sub(r"\s+and\s*$", "", n, flags=re.I)
    n = re.sub(r"['\u2019]+$", "", n)
    if re.search(r"[a-z][SYH]$", n):
        n = n[:-1]
    n = _fix_author_ocr_token(n)
    return _normalize_ws(n).strip()


def _split_two_comma_authors(s: str) -> list[str] | None:
    if s.count(",") != 1:
        return None
    a, b = [x.strip() for x in s.split(",", 1)]
    if (
        _looks_like_person_name_chunk(a)
        and _looks_like_person_name_chunk(b)
        and len(a.split()) >= 2
        and len(b.split()) >= 2
    ):
        return [_repair_author_string(a), _repair_author_string(b)]
    return None


def _split_multi_comma_authors(s: str) -> list[str] | None:
    """e.g. 'Sally H. Zigmond, Michael Joyce, Jane Borleis, Gary M. Bokoch'."""
    if s.count(",") < 2:
        return None
    parts: list[str] = []
    for p in s.split(","):
        p = p.strip()
        if re.match(r"(?i)^and\s+", p):
            p = re.sub(r"(?i)^and\s+", "", p).strip()
        if not p:
            return None
        rp = _repair_author_string(p)
        if not rp or _author_string_should_drop(rp):
            return None
        ok = _looks_like_person_name_chunk(rp) or (
            5 <= len(rp) <= 90
            and re.match(r"^[A-Z]", rp)
            and " " in rp
            and rp.count(" ") <= 4
        )
        if not ok:
            return None
        parts.append(rp[:300])
    return parts if len(parts) >= 3 else None


def sanitize_stored_authors_list(authors: Any) -> tuple[list[str], bool]:
    """
    Drop affiliation/citation junk, repair OCR tokens, split colon-joined pairs.
    Returns (new_list, changed).
    """
    if not isinstance(authors, list):
        return [], False
    before = [x for x in authors if isinstance(x, str)]
    expanded: list[str] = []

    for x in authors:
        if not isinstance(x, str):
            continue
        o = x.strip()
        fixed = _repair_author_string(o)
        if not fixed or _author_string_should_drop(fixed):
            continue
        multi = _split_multi_comma_authors(fixed)
        if multi:
            expanded.extend(multi)
            continue
        if ":" in fixed:
            bits = [b.strip() for b in re.split(r":+", fixed) if b.strip()]
            kept: list[str] = []
            for b in bits:
                bb = _repair_author_string(b)
                if not bb or _author_string_should_drop(bb):
                    continue
                if _looks_like_person_name_chunk(bb) or (
                    6 <= len(bb) <= 160 and re.match(r"^[A-Z]", bb) and " " in bb
                ):
                    kept.append(bb[:300])
            if kept:
                expanded.extend(kept)
            continue
        pair = _split_two_comma_authors(fixed)
        if pair:
            expanded.extend(pair)
            continue
        if _looks_like_person_name_chunk(fixed) or (
            6 <= len(fixed) <= 160 and re.match(r"^[A-Z]", fixed) and " " in fixed
        ):
            expanded.append(fixed[:300])

    seen: set[str] = set()
    deduped: list[str] = []
    for a in expanded:
        k = a.lower()
        if k not in seen:
            seen.add(k)
            deduped.append(a)

    changed = deduped != before
    return deduped, changed


def _expand_and_conjoined_author_chunks(names: list[str]) -> list[str]:
    """Split 'LAST M. FIRST and LAST2 M2. FIRST2' kept as one chunk after comma splitting."""
    out: list[str] = []
    for n in names:
        t = _normalize_ws(n).strip()
        if not re.search(r"\s+and\s+", t, re.I):
            out.append(t)
            continue
        pieces = [p.strip(" ,.") for p in re.split(r"\s+and\s+", t, flags=re.I) if p.strip()]
        if len(pieces) == 2:
            a, b = pieces[0], pieces[1]
            if (
                _looks_like_person_name_chunk(a)
                and len(a.split()) >= 2
                and _looks_like_person_name_chunk(b)
                and len(b.split()) >= 2
            ):
                out.extend([a, b])
                continue
        out.append(t)
    return out


def parse_byline_authors(s: str) -> list[str]:
    s = re.sub(r'[*"\u201c\u201d\u2019†‡§]+', " ", s)
    s = _collapse_spaced_caps_runs(s)
    s = _strip_inline_author_footnotes(s)
    s = _normalize_ws(s)
    if not s:
        return []
    chunks = [c.strip() for c in s.split(";") if c.strip()]
    if len(chunks) >= 2:
        raw_names = chunks
    elif ";" not in s and "," in s and len(s) < 420:
        parts: list[str] = []
        for p in s.split(","):
            p = p.strip()
            if re.match(r"(?i)^and\s+", p):
                p = re.sub(r"(?i)^and\s+", "", p).strip()
            if p:
                parts.append(p)
        ok = [p for p in parts if _looks_like_person_name_chunk(p) and len(p.split()) >= 2]
        if len(ok) >= 2:
            raw_names = ok
        else:
            raw_names = re.split(r"\s+and\s+", s, flags=re.IGNORECASE)
    else:
        raw_names = re.split(r"\s+and\s+", s, flags=re.IGNORECASE)
    raw_names = _expand_and_conjoined_author_chunks(raw_names)
    out: list[str] = []
    for n in raw_names[:20]:
        n = _normalize_ws(n).strip(" ,.")
        if _looks_like_person_name_chunk(n) or (
            6 <= len(n) <= 160 and re.match(r"^[A-Z]", n) and " " in n and not n.lower().startswith("http")
        ):
            rep = _repair_author_string(n[:200])
            if rep and not _author_string_should_drop(rep):
                out.append(rep)
    return out[:15]


def split_glued_title_and_authors_blob(title: str) -> tuple[str | None, list[str] | None]:
    """
    PDF metadata sometimes concatenates title + author list (no comma before first author).
    """
    t = (title or "").strip()
    if len(t) < 35:
        return None, None
    m = re.search(r"(?i)(.{15,}?[a-z0-9\)\'\"])\s+([A-Z]{2,}\s+[A-Z]\.\s+[A-Za-z].*)$", t)
    if not m:
        return None, None
    head, tail = m.group(1).strip(), m.group(2).strip()
    if len(head) < 12 or len(tail) < 20:
        return None, None
    authors = parse_byline_authors(tail)
    if len(authors) < 2:
        return None, None
    return head, authors


def infer_year_from_head_lines(lines: list[str]) -> int | None:
    """
    Prefer years on citation/copyright lines; skip JSTOR access / terms lines.
    """
    bad_line = re.compile(r"jstor|terms and conditions|wed\s+\w+\s+\d{1,2}\s+\d{4}", re.I)
    good_line = re.compile(
        r"volume|vol\.|issue|\(jan|\(feb|march|april|may|june|july|aug|sept|oct|nov|dec|copyright|©|national academy|inst monogr|proc\.?\s*nat",
        re.I,
    )
    year_re = re.compile(r"\b(19[6-9]\d|20[0-2]\d)\b")
    scored: list[tuple[int, int, int]] = []
    for idx, ln in enumerate(lines[:120]):
        for m in year_re.finditer(ln):
            y = int(m.group(1))
            if not (1965 <= y <= 2030):
                continue
            if bad_line.search(ln) and not good_line.search(ln):
                continue
            pri = 3 if good_line.search(ln) else 1
            scored.append((pri, idx, y))
    if not scored:
        return None
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[0][2]


def _authors_from_split_block(lines: list[str], j: int) -> tuple[list[str], int]:
    if _looks_like_split_author_block(lines, j):
        a, b, c = lines[j], lines[j + 1], lines[j + 2]
        name = _normalize_ws(f"{a.strip()} {b.strip()} {c.strip()}")
        return [name], j + 3
    if _looks_like_two_line_author(lines, j):
        a, b = lines[j], lines[j + 1]
        name = _normalize_ws(f"{a.strip()} {b.strip()}")
        return [name], j + 2
    return [], j


def _line_looks_like_given_first_byline(s: str) -> bool:
    """e.g. 'Pamela J. Lilly and Peter N. Devreotes' or 'Ronald L. Johnson, 1 Charles'."""
    t = s.strip()
    return bool(re.search(r"^[A-Z][a-z]+\s+[A-Z]\.\s+[A-Za-z]", t))


def collect_wrapped_author_block(lines: list[str], j: int) -> tuple[str, int]:
    """Merge author lines split across wraps (e.g. '... GARDNER and' + 'DIANA J. CARD')."""
    if j >= len(lines):
        return "", j
    ln0 = lines[j]
    if not (
        _line_looks_like_authors_start(ln0)
        or _line_is_oxford_three_author(ln0)
        or (_is_byline_line(ln0) and _line_looks_like_given_first_byline(ln0))
    ):
        return "", j
    blob_parts = [lines[j].strip()]
    j += 1
    while j < len(lines) and len(blob_parts) < 5:
        ln = lines[j].strip()
        if _is_affiliation_or_section_start(ln):
            break
        low = ln.lower()
        if low.startswith("introduction") or low.startswith("keywords"):
            break
        prev = blob_parts[-1]
        if prev.rstrip().endswith("and") or prev.rstrip().endswith(", and"):
            blob_parts.append(ln)
            j += 1
            continue
        if _line_looks_like_authors_start(ln):
            blob_parts.append(ln)
            j += 1
            continue
        if (
            prev.count(",") >= 1
            and len(ln) < 95
            and re.search(r"[A-Z]\.\s+[A-Za-z]", ln)
            and ln.upper() == ln
        ):
            blob_parts.append(ln)
            j += 1
            continue
        break
    return _normalize_ws(" ".join(blob_parts)), j


def _authors_from_surname_comma_catalog(blob: str) -> list[str]:
    """Parse 'Insall, R., Borleis, J. and Devreotes, P.N.' from ILL catalog lines."""
    out: list[str] = []
    blob = blob.strip()
    if not blob:
        return out
    for and_seg in re.split(r"\s+and\s+", blob, flags=re.I):
        and_seg = and_seg.strip().rstrip(",").strip()
        pieces = re.split(r"(?<=\.),\s*(?=[A-Z][a-z])", and_seg)
        for piece in pieces:
            piece = piece.strip()
            m_hy = re.match(r"^([A-Za-z'\-]+),\s*([A-Z]-[A-Z]\.)\s*$", piece)
            if m_hy:
                sur, ini = m_hy.group(1), m_hy.group(2)
                disp = _normalize_ws(f"{ini} {sur}")
                if disp and not _author_string_should_drop(disp):
                    out.append(disp[:200])
                continue
            m = re.match(r"^([A-Za-z'\-]+),\s*((?:[A-Z]\.)+)\s*$", piece)
            if not m:
                continue
            sur, dots = m.group(1), m.group(2)
            letters = [x for x in dots.split(".") if len(x) == 1 and x.isalpha()]
            if not letters:
                continue
            ini = " ".join(f"{x}." for x in letters)
            disp = _normalize_ws(f"{ini} {sur}")
            if disp and not _author_string_should_drop(disp):
                out.append(disp[:200])
    return out


def _try_interlibrary_article_line(line: str) -> tuple[str | None, list[str]]:
    """ILL OCR line: Article: Surname, I., ... : The real title… (or : Cell-cell …)."""
    s = (line or "").strip()
    m = re.match(r"^Article:\s*(.+)$", s, re.I)
    if not m:
        return None, []
    rest = m.group(1).strip()
    matches = list(re.finditer(r":\s*([A-Z][^\n:]{14,})\s*$", rest))
    if not matches:
        return None, []
    mcol = matches[-1]
    auth_blob = rest[: mcol.start()].strip().rstrip(":").strip()
    title = mcol.group(1).strip()
    if len(title) < 15:
        return None, []
    authors = _authors_from_surname_comma_catalog(auth_blob)
    if len(authors) < 2:
        return None, []
    if metadata_title_is_junk(title):
        return None, []
    return title[:500], authors[:15]


def infer_title_authors_year(
    text: str,
    paper_id: str,
    existing_title: str,
) -> tuple[str | None, list[str], int | None]:
    """
    Heuristic front-matter parse. Returns (title or None, authors, year or None).
    Title None means caller should keep existing.
    """
    lines = normalize_head_lines(text[:60000])
    if not lines:
        return None, [], None
    for ln in lines[:45]:
        cat_title, cat_auth = _try_interlibrary_article_line(ln)
        if cat_title and len(cat_auth) >= 2:
            year = infer_year_from_head_lines(lines[:48])
            return cat_title, cat_auth, year
    i0 = skip_leading_chaff(lines)
    if i0 >= len(lines):
        i0 = 0
    title, j = merge_title_from_lines(lines, i0)
    authors: list[str] = []
    split_auth, j2 = _authors_from_split_block(lines, j)
    if split_auth:
        authors = split_auth
        j = j2
    else:
        blob, jn = collect_wrapped_author_block(lines, j)
        if blob:
            authors = parse_byline_authors(blob)
            j = jn
        elif j < len(lines) and _is_byline_line(lines[j]):
            authors = parse_byline_authors(lines[j])
    # Keep year inference near the front matter (avoid reference-section years).
    year = infer_year_from_head_lines(lines[:48])
    if not title or len(title) < 8:
        return None, authors, year
    # Avoid replacing with garbage shorter than existing if existing is longer and not junk
    if not metadata_title_is_junk(existing_title) and len(existing_title) > len(title) + 10:
        return None, authors, year
    return title, authors, year


def authors_for_report(paper_data: dict[str, Any]) -> list[str]:
    """Display names for metadata report: top-level list or Crossref structured."""
    raw = paper_data.get("authors")
    if isinstance(raw, list) and raw:
        out: list[str] = []
        for x in raw:
            if isinstance(x, str) and x.strip():
                out.append(x.strip()[:300])
        if out:
            return out
    if crossref_enrichment_ok(paper_data):
        cr = paper_data.get("crossref") or {}
        struct = cr.get("authors")
        if isinstance(struct, list) and struct and isinstance(struct[0], dict):
            return crossref_structured_authors_to_display_names(struct)
    return []


def build_metadata_report_row(paper_data: dict[str, Any]) -> dict[str, Any]:
    text = paper_data.get("text") or ""
    cr_ok = crossref_enrichment_ok(paper_data)
    authors_list = authors_for_report(paper_data)
    ac = len(authors_list)
    title = paper_data.get("title") or ""
    return {
        "paper_id": paper_data.get("paper_id"),
        "filename": paper_data.get("filename"),
        "title": title[:300] if title else "",
        "title_junk": metadata_title_is_junk(title),
        "doi": paper_data.get("doi"),
        "year": paper_data.get("year"),
        "journal": (paper_data.get("journal") or "")[:200],
        "authors": authors_list,
        "authors_count": ac,
        "text_via_ocr": bool(paper_data.get("text_via_ocr")),
        "text_chars": len(text),
        "crossref_ok": cr_ok,
        "crossref_fetched_at": paper_data.get("crossref_fetched_at"),
        "metadata_cleaned_at": paper_data.get("metadata_cleaned_at"),
    }


def clean_paper_json(
    data: dict[str, Any],
    *,
    touch_crossref_papers: bool = False,
    normalize_text: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Return (updated_data, change_log). Mutates a copy of data when fixes apply.
    """
    changes: dict[str, Any] = {}
    out = dict(data)
    cr_ok = crossref_enrichment_ok(out)

    if isinstance(out.get("text"), str):
        st = sanitize_pdf_extracted_text(out["text"])
        if st != out["text"]:
            out["text"] = st
            changes["text_sanitized_unicode"] = True
    if isinstance(out.get("title"), str):
        tt = sanitize_pdf_extracted_text(out["title"])
        if tt != out["title"]:
            out["title"] = tt
            changes["title_sanitized_unicode"] = True

    if normalize_text and out.get("text"):
        new_text = strip_page_markers_from_text(out["text"])
        if new_text != out["text"]:
            out["text"] = new_text
            changes["text_page_markers_stripped"] = True

    if cr_ok and not touch_crossref_papers:
        sa, auth_san = sanitize_stored_authors_list(out.get("authors"))
        if auth_san:
            out["authors"] = sa
            changes["authors"] = list(sa[:6]) if sa else []
        if not changes:
            return out, {}
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        out["metadata_cleaned_at"] = ts
        return out, changes

    text = out.get("text") or ""
    paper_id = str(out.get("paper_id") or "")
    existing_title = str(out.get("title") or "")
    title_was_junk = metadata_title_is_junk(existing_title)
    bad_stored_authors = _stored_authors_look_invalid(out.get("authors"))

    glued_t, glued_a = split_glued_title_and_authors_blob(existing_title)
    new_title, new_authors, new_year = infer_title_authors_year(text, paper_id, existing_title)

    if glued_t and glued_a and len(glued_a) >= 2:
        out["title"] = glued_t[:500]
        out["authors"] = glued_a[:15]
        changes["title"] = {"from": existing_title[:120], "to": glued_t[:120]}
        changes["authors"] = glued_a[:6]
    elif new_title and title_was_junk and not metadata_title_is_junk(new_title):
        out["title"] = new_title
        changes["title"] = {"from": existing_title[:120], "to": new_title[:120]}

    if not (glued_t and glued_a and len(glued_a) >= 2):
        authors_missing = not isinstance(out.get("authors"), list) or len(out.get("authors") or []) == 0
        if (
            new_authors
            and all(len(a.split()) >= 2 for a in new_authors)
            and (title_was_junk or bad_stored_authors or authors_missing)
        ):
            out["authors"] = new_authors
            changes["authors"] = new_authors[:6]

    if new_year is not None:
        old_y = out.get("year")
        if old_y is None and (title_was_junk or bad_stored_authors):
            out["year"] = new_year
            changes["year"] = {"from": None, "to": new_year}
        elif (
            isinstance(old_y, int)
            and old_y >= 1995
            and new_year < old_y
            and 1960 <= new_year <= 1999
        ):
            # Typical JSTOR/reprint header vs real publication (e.g. 2003 vs 1976)
            out["year"] = new_year
            changes["year"] = {"from": old_y, "to": new_year}

    if not out.get("doi") and text:
        doi = find_best_doi_in_text(concat_text_for_doi_scan(text))
        if doi:
            out["doi"] = doi
            changes["doi"] = doi

    sa, auth_san = sanitize_stored_authors_list(out.get("authors"))
    if auth_san:
        out["authors"] = sa
        changes["authors"] = list(sa[:6]) if sa else []

    if changes:
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        out["metadata_cleaned_at"] = ts
        cm = out.get("clean_metadata") if isinstance(out.get("clean_metadata"), dict) else {}
        cm = dict(cm)
        cm["last_run"] = ts
        if "title" in changes:
            cm["title_inferred"] = True
        if "authors" in changes:
            cm["authors_inferred"] = True
        if "year" in changes:
            cm["year_inferred"] = True
        if "doi" in changes:
            cm["doi_inferred"] = True
        out["clean_metadata"] = cm

    return out, changes
