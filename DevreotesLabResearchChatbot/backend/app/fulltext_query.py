"""Lucene full-text query construction for hybrid chunk retrieval (no Neo4j / ML imports)."""

from __future__ import annotations

import os
import re

from .stopword_tokens import GENE_HGNC_LOOKUP_SKIP_TOKENS

_LUCENE_SPECIAL_RE = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')


def _lucene_escape_term(term: str) -> str:
    return _LUCENE_SPECIAL_RE.sub(r"\\\1", term)


# Short tokens still useful for keyword recall (e.g. ACh, Ras family).
_FULLTEXT_SHORT_OK = frozenset(
    {
        "PTEN",
        "RAS",
        "ERK",
        "AKT",
        "PIP",
        "PI3",
        "DNA",
        "RNA",
        "GPCR",
        "ACH",
        "RHO",
        "RAC",
        "MAP",
        "JUN",
        "FOS",
        "SHH",
        "BAD",
        "SRC",
        "MTOR",
    }
)


def build_fulltext_lucene_query(question: str) -> str | None:
    """
    Build an OR-joined Lucene query for db.index.fulltext.queryNodes.
    Returns None when there is nothing useful to search.
    """
    q = (question or "").strip()
    if not q:
        return None
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]*", q)
    terms: list[str] = []
    seen: set[str] = set()
    max_terms = int(os.getenv("RAG_FULLTEXT_MAX_TERMS", "12"))
    for raw in tokens:
        u = raw.upper()
        if u in GENE_HGNC_LOOKUP_SKIP_TOKENS:
            continue
        if len(raw) < 4 and u not in _FULLTEXT_SHORT_OK:
            continue
        low = raw.lower()
        if low in seen:
            continue
        seen.add(low)
        terms.append(_lucene_escape_term(low))
        if len(terms) >= max_terms:
            break
    if not terms:
        return None
    return " OR ".join(terms)
