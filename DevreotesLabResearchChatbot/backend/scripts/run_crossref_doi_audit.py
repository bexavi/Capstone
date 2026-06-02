"""
Audit extracted paper DOIs against Crossref (author + title metadata).

Run from project root:
  PYTHONPATH=. python backend/scripts/run_crossref_doi_audit.py
  PYTHONPATH=. python backend/scripts/run_crossref_doi_audit.py --offline

Crossref etiquette: set CROSSREF_MAILTO in .env (loaded via paths.load_project_dotenv).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.doi_utils import normalize_doi_for_storage
from backend.app.paths import EXTRACTED_DIR, load_project_dotenv


def load_paper_dois() -> list[tuple[str, str, str]]:
    """(paper_id, raw_doi, title)"""
    out: list[tuple[str, str, str]] = []
    for f in sorted(EXTRACTED_DIR.glob("*.json")):
        with f.open(encoding="utf-8") as fp:
            d = json.load(fp)
        doi = d.get("doi")
        if doi and str(doi).strip():
            out.append(
                (
                    str(d.get("paper_id") or f.stem),
                    str(doi).strip(),
                    (d.get("title") or "")[:80],
                )
            )
    return out


def author_shape(authors: list) -> tuple[str, int]:
    if not authors:
        return "no_authors", 0
    n = len(authors)
    structured = sum(
        1
        for a in authors
        if isinstance(a, dict) and (a.get("family") or a.get("given"))
    )
    if structured >= max(1, n // 2):
        return "mostly_structured", n
    if structured == 0:
        return "literal_name_only", n
    return "mixed", n


def main() -> None:
    load_project_dotenv()
    ap = argparse.ArgumentParser(description="Crossref DOI metadata audit")
    ap.add_argument(
        "--offline",
        action="store_true",
        help="Only print DOI normalization stats (no HTTP)",
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=0.25,
        help="Seconds between Crossref requests (default 0.25)",
    )
    args = ap.parse_args()

    rows = load_paper_dois()
    print(f"Extracted JSON with non-empty doi: {len(rows)}\n")

    changed = []
    for pid, raw, _ in rows:
        norm = normalize_doi_for_storage(raw)
        raw_s = raw.strip()
        if norm != raw_s:
            changed.append((pid, raw, norm or "(invalid / empty after normalize)"))
    print(f"DOIs altered by normalization: {len(changed)}")
    for pid, raw, norm in changed[:15]:
        print(f"  {pid}: {raw[:70]} -> {norm[:70]}")
    if len(changed) > 15:
        print(f"  ... +{len(changed) - 15} more")

    if args.offline:
        return

    try:
        import requests
    except ImportError:
        print("Install requests (pip install requests) for Crossref calls.")
        sys.exit(1)

    mail = os.getenv("CROSSREF_MAILTO", "").strip() or "anonymous@example.com"
    ua = f"DevreotesLabResearchChatbot/1.0 (mailto:{mail})"
    session = requests.Session()
    session.headers["User-Agent"] = ua

    stats: dict = {
        "200": 0,
        "404": 0,
        "other": 0,
        "with_authors": 0,
        "empty_authors": 0,
        "shape": {},
    }
    fails: list[tuple[str, str, str]] = []
    wins: list[tuple[str, int, list[str]]] = []

    for pid, raw, _ in rows:
        doi = normalize_doi_for_storage(raw)
        if not doi:
            stats["other"] += 1
            if len(fails) < 12:
                fails.append((pid, raw[:55], "skipped: invalid DOI after normalize"))
            time.sleep(args.sleep)
            continue
        url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
        try:
            r = session.get(url, timeout=25)
        except requests.RequestException as e:
            stats["other"] += 1
            if len(fails) < 12:
                fails.append((pid, doi[:55], str(e)[:100]))
            time.sleep(args.sleep)
            continue

        if r.status_code == 404:
            stats["404"] += 1
            if len(fails) < 12:
                fails.append((pid, doi[:55], "404"))
            time.sleep(args.sleep)
            continue
        if r.status_code != 200:
            stats["other"] += 1
            if len(fails) < 12:
                fails.append((pid, doi[:55], f"HTTP {r.status_code}"))
            time.sleep(args.sleep)
            continue

        stats["200"] += 1
        try:
            msg = r.json().get("message") or {}
        except json.JSONDecodeError:
            stats["200"] -= 1
            stats["other"] += 1
            fails.append((pid, doi[:55], "invalid JSON"))
            time.sleep(args.sleep)
            continue

        authors = msg.get("author") or []
        if authors:
            stats["with_authors"] += 1
        else:
            stats["empty_authors"] += 1
        tag, n = author_shape(authors)
        stats["shape"][tag] = stats["shape"].get(tag, 0) + 1

        if len(wins) < 8 and authors:
            names = []
            for a in authors[:4]:
                if isinstance(a, dict):
                    g, fam = a.get("given") or "", a.get("family") or ""
                    nm = a.get("name") or ""
                    names.append(f"{g} {fam}".strip() or nm or "?")
            wins.append((pid, n, names))

        time.sleep(args.sleep)

    print("\n=== Crossref /works/{{doi}} (after normalization) ===")
    print(f"HTTP 200: {stats['200']}")
    print(f"HTTP 404: {stats['404']}")
    print(f"Other / network / JSON error: {stats['other']}")
    print(f"\nAmong 200: author list non-empty: {stats['with_authors']}, empty: {stats['empty_authors']}")
    print("\nAuthor field shape (HTTP 200 only):")
    for k, v in sorted(stats["shape"].items()):
        print(f"  {k}: {v}")

    print("\nSample successes:")
    for pid, n, names in wins:
        print(f"  paper {pid} | {n} authors | {names}")

    print("\nSample failures:")
    for pid, doi, err in fails:
        print(f"  paper {pid} | {doi} | {err}")


if __name__ == "__main__":
    main()
