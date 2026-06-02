"""
Resolve display author strings to stable Neo4j Author keys: ORCID when present, else alias map, else slug.

``author_aliases.json`` maps variant spellings (keys, any case) to a canonical display name.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .crossref_metadata import orcid_from_structured_author_row
from .extracted_clean import authors_for_report


def normalize_author_key(name: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower())
    return key.strip("_")


def load_author_alias_map(path: Path) -> dict[str, str]:
    """
    Load ``canonical_names`` object or a flat dict of variant (any case) -> canonical display name.
    Keys in the returned map are lowercased stripped variants.
    """
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    raw = data.get("canonical_names") if isinstance(data.get("canonical_names"), dict) else data
    out: dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        if k.startswith("_"):
            continue
        ks, vs = k.strip(), v.strip()
        if ks and vs:
            out[ks.lower()] = vs
    return out


def _orcids_aligned_with_authors(paper_data: dict[str, Any], n: int) -> list[str | None]:
    cr = paper_data.get("crossref") or {}
    struct = cr.get("authors")
    if not isinstance(struct, list) or not struct:
        return [None] * n
    out: list[str | None] = []
    for i in range(n):
        row = struct[i] if i < len(struct) and isinstance(struct[i], dict) else None
        out.append(orcid_from_structured_author_row(row) if row else None)
    return out


def author_records_for_ingest(paper_data: dict[str, Any], aliases: dict[str, str]) -> list[dict[str, Any]]:
    """
    One record per credited author, in order.

    ``author_key``: ``orcid:<id>`` when Crossref (structured) provides ORCID for that index;
    otherwise slug from canonical display name after alias lookup.
    ``name``: canonical display string for ``Author.name``.
    ``orcid``: id when known (also encoded in ``author_key`` for ORCID-backed rows).
    """
    display_list = authors_for_report(paper_data)
    orcids = _orcids_aligned_with_authors(paper_data, len(display_list))
    records: list[dict[str, Any]] = []
    for display, oid in zip(display_list, orcids):
        d = (display or "").strip()
        canonical = aliases.get(d.lower(), d) if d else d
        canonical = (canonical or "").strip() or d
        if oid:
            author_key = f"orcid:{oid.lower()}"
        else:
            author_key = normalize_author_key(canonical) or canonical.lower()
        records.append(
            {
                "author_key": author_key,
                "name": canonical[:300],
                "orcid": oid,
            }
        )
    return records
