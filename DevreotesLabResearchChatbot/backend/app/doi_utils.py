"""
Shared DOI extraction and normalization (no PDF dependencies).
Used by extract_pdfs, ingest_papers, and Crossref audit script.
"""

from __future__ import annotations

import re

# Suffix allows Elsevier-style PII: 10.1016/S1874-6047(10)71081-9
_DOI_BODY_RE = re.compile(
    r"\b(10\.\d{4,9}/[A-Za-z0-9\.\/\(\)\-]+)",
    re.IGNORECASE,
)


# PLOS figures/supplements use suffixes like .g001 or .s001 on the article DOI.
_PLOS_COMPONENT_SUFFIX_RE = re.compile(r"\.(?:g|s|t)\d+$", re.IGNORECASE)


def plos_component_to_article_doi(doi: str) -> str:
    """Map 10.1371/journal.*.g001-style DOIs to the parent article DOI."""
    if not doi or not re.match(r"10\.1371/journal\.", doi, re.I):
        return doi
    return _PLOS_COMPONENT_SUFFIX_RE.sub("", doi)


def normalize_doi_for_storage(raw: str | None) -> str | None:
    """
    Clean a DOI string for JSON / Neo4j / Crossref lookup.
    """
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    for ch in ("\u2013", "\u2014", "\u2015", "—"):
        s = s.replace(ch, "-")
    # Cell Reports Elsevier id: PDF wrap "cel-\nrep" stored as j.cel-rep. → j.celrep.
    s = re.sub(r"(?i)(j\.)cel-rep\.", r"\1celrep.", s)
    s = s.split("/-/DCSupplemental")[0].strip()
    s = re.split(r"[\u2014—]\s*", s, maxsplit=1)[0].strip()
    s = re.sub(r"\.\-[A-Za-z][\w\-]*$", "", s)
    s = s.rstrip(".,;)]}\"'")
    if not re.match(r"10\.\d{4,9}/", s, re.I):
        return None
    return s[:256] if len(s) <= 256 else s[:256]


def concat_text_for_doi_scan(
    text: str | None,
    *,
    head_chars: int = 80000,
    tail_chars: int = 22000,
    max_chars: int = 110000,
) -> str:
    """
    First ~head_chars + last ~tail_chars, for DOIs that appear only in publisher footers
    (e.g. Genes & Dev. / Cold Spring Harbor) after long article bodies.
    """
    if not text:
        return ""
    t = str(text)
    n = len(t)
    if n <= head_chars + tail_chars:
        return t
    combined = f"{t[:head_chars]}\n\n{t[-tail_chars:]}"
    if len(combined) > max_chars:
        return combined[:max_chars]
    return combined


def _prepare_text_for_doi_scan(head: str) -> str:
    """Normalize PDF typography so DOI regex is not cut by line breaks (MBC dashes, Annual Reviews, Elsevier)."""
    s = head
    for ch in ("\u2013", "\u2014", "\u2015", "—"):
        s = s.replace(ch, "-")
    # "j.cel-\nrep.2011" -> "j.celrep.2011" (spurious hyphen from line-wrap inside journal id)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"([a-z]+)-\s*\n\s*([a-z]+)", r"\1\2", s)
    # e.g. "annurev-cellbio-100616-\n060739" (keep hyphen before digit continuation)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"-\s*\n\s*([A-Za-z0-9])", r"-\1", s)
    s = re.sub(r"\((\d+)\s*\n\s*(\d)", r"(\1)\2", s)
    return s


def find_best_doi_in_text(head: str) -> str | None:
    """
    Best DOI in the supplied text window.

    Callers often pass ``concat_text_for_doi_scan(full_text)`` so footers are included.

    Prefers *article* DOIs over longer PLOS component DOIs (e.g. figure .g001),
    using occurrence counts so a short article id repeated in the header wins.
    """
    if not head:
        return None
    flattened = _prepare_text_for_doi_scan(head)
    article_counts: dict[str, int] = {}
    for m in _DOI_BODY_RE.finditer(flattened):
        cand = normalize_doi_for_storage(m.group(1))
        if not cand or len(cand) < 12:
            continue
        article = plos_component_to_article_doi(cand)
        article_counts[article] = article_counts.get(article, 0) + 1
    if not article_counts:
        return None
    return max(article_counts.keys(), key=lambda d: (article_counts[d], -len(d)))
