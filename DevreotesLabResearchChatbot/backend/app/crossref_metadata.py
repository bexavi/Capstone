"""
Map Crossref /works/{doi} `message` JSON into fields for extracted paper JSON.

Used by backend/scripts/enrich_extracted_crossref.py (no HTTP here).
"""

from __future__ import annotations

import html
import re
from typing import Any


def _first_str(val: Any, max_len: int = 2000) -> str | None:
    if val is None:
        return None
    if isinstance(val, list):
        if not val:
            return None
        s = str(val[0]).strip()
    elif isinstance(val, str):
        s = val.strip()
    else:
        s = str(val).strip()
    if not s:
        return None
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_len] if len(s) > max_len else s


def _date_year(msg: dict) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        block = msg.get(key)
        if not isinstance(block, dict):
            continue
        parts = block.get("date-parts")
        if not parts or not isinstance(parts, list) or not parts[0]:
            continue
        y = parts[0][0]
        if isinstance(y, int) and 1900 <= y <= 2100:
            return y
    return None


_ORCID_ID_RE = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", re.IGNORECASE)


def normalize_orcid_url_or_id(raw: Any) -> str | None:
    """
    Crossref often stores ``"ORCID": "https://orcid.org/0000-0001-2345-6789"``.
    Returns uppercase canonical id or None.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    m = _ORCID_ID_RE.search(s)
    if not m:
        return None
    return m.group(1).upper()


def orcid_from_structured_author_row(row: dict[str, Any]) -> str | None:
    if not row:
        return None
    return normalize_orcid_url_or_id(row.get("orcid") or row.get("ORCID"))


def _authors(msg: dict) -> list[dict[str, str | None]]:
    raw = msg.get("author") or []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str | None]] = []
    for a in raw[:80]:
        if not isinstance(a, dict):
            continue
        aff = None
        affs = a.get("affiliation")
        if isinstance(affs, list) and affs and isinstance(affs[0], dict):
            aff = _first_str(affs[0].get("name"), 400)
        given = _first_str(a.get("given"), 200)
        family = _first_str(a.get("family"), 200)
        name = _first_str(a.get("name"), 300)
        seq = a.get("sequence")
        oid = normalize_orcid_url_or_id(a.get("ORCID") or a.get("orcid"))
        rec: dict[str, str | None] = {
            "given": given,
            "family": family,
            "name": name,
            "sequence": str(seq) if seq else None,
            "affiliation": aff,
        }
        if oid:
            rec["orcid"] = oid
        out.append(rec)
    return out


def crossref_structured_authors_to_display_names(rows: list[dict[str, Any]]) -> list[str]:
    """
    Turn Crossref-style author dicts (from _authors) into ordered display strings for JSON / ingest.
    """
    out: list[str] = []
    for a in rows:
        if not isinstance(a, dict):
            continue
        given = (a.get("given") or "").strip()
        family = (a.get("family") or "").strip()
        name = (a.get("name") or "").strip()
        if given and family:
            s = f"{given} {family}".strip()
        elif name:
            s = name
        else:
            s = (family or given or "").strip()
        if not s:
            continue
        s = s[:200]
        if s not in out:
            out.append(s)
    return out


def _issn_list(msg: dict) -> list[str]:
    issn = msg.get("ISSN") or msg.get("issn-type")
    if not isinstance(issn, list):
        return []
    out: list[str] = []
    for x in issn:
        if isinstance(x, str) and x.strip():
            out.append(x.strip()[:32])
        elif isinstance(x, dict) and x.get("value"):
            v = str(x["value"]).strip()
            if v:
                out.append(v[:32])
    return out[:4]


def message_to_enrichment(message: dict) -> dict[str, Any]:
    """
    Build a dict safe to merge into extracted JSON.

    Top-level keys for ingest: title, year, journal (when caller applies them).
    Everything else is intended for nested `crossref` in the JSON file.
    """
    title = _first_str(message.get("title"), 800)
    subtitle = _first_str(message.get("subtitle"), 500)
    journal = _first_str(message.get("container-title"), 500)
    year = _date_year(message)
    vol = _first_str(message.get("volume"), 32)
    issue = _first_str(message.get("issue"), 32)
    page = _first_str(message.get("page"), 64)
    publisher = _first_str(message.get("publisher"), 400)
    typ = _first_str(message.get("type"), 80)
    url = _first_str(message.get("URL"), 512)
    doi_from_api = _first_str(message.get("DOI"), 256)

    structured_authors = _authors(message)
    authors_display = crossref_structured_authors_to_display_names(structured_authors)

    crossref_block: dict[str, Any] = {
        "publisher": publisher,
        "type": typ,
        "url": url,
        "volume": vol,
        "issue": issue,
        "page": page,
        "subtitle": subtitle,
        "issn": _issn_list(message) or None,
        "authors": structured_authors or None,
    }
    if doi_from_api:
        crossref_block["doi"] = doi_from_api

    # Drop None values for cleaner JSON
    crossref_block = {k: v for k, v in crossref_block.items() if v is not None}

    return {
        "title": title,
        "year": year,
        "journal": journal,
        "authors": authors_display,
        "crossref": crossref_block,
    }
