"""
Fetch Crossref metadata for each extracted paper with a DOI and update the JSON file.

Updates (on HTTP 200):
  - doi: normalized registry DOI from Crossref when available
  - title, year, journal: from Crossref (overwrites heuristic extraction)
  - authors: list of display strings from Crossref (top-level, for ingest / tooling)
  - crossref: extra fields (authors as structured dicts with optional ``orcid``, publisher, type, url, …)
  - crossref_fetched_at: ISO-8601 UTC timestamp

Backfill top-level authors from existing crossref.authors (no HTTP):
  PYTHONPATH=. python backend/scripts/enrich_extracted_crossref.py --backfill-authors-only

On failure (404, network, invalid DOI after normalize):
  - Keeps existing title/year/journal/doi
  - Sets crossref = { "error": "...", "looked_up_doi": "..." } and crossref_fetched_at

Run from project root:
  PYTHONPATH=. python backend/scripts/enrich_extracted_crossref.py
  PYTHONPATH=. python backend/scripts/enrich_extracted_crossref.py --dry-run
  PYTHONPATH=. python backend/scripts/enrich_extracted_crossref.py --limit 5

Set CROSSREF_MAILTO in .env for polite API use (see .env.example).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.crossref_metadata import (
    crossref_structured_authors_to_display_names,
    message_to_enrichment,
)
from backend.app.doi_utils import normalize_doi_for_storage
from backend.app.paths import EXTRACTED_DIR, load_project_dotenv


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def backfill_top_level_authors(*, dry_run: bool) -> int:
    """Set `authors` from nested `crossref.authors` without calling Crossref."""
    updated = 0
    for path in sorted(EXTRACTED_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as fp:
            data = json.load(fp)
        cr = data.get("crossref") or {}
        if cr.get("error"):
            continue
        raw = cr.get("authors")
        if not isinstance(raw, list):
            continue
        if not raw:
            names = []
        elif isinstance(raw[0], dict):
            names = crossref_structured_authors_to_display_names(raw)
        elif isinstance(raw[0], str):
            names = [str(x).strip() for x in raw if str(x).strip()][:80]
        else:
            names = []
        if not dry_run:
            data["authors"] = names
            with path.open("w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False)
        updated += 1
    print(f"backfill-authors: touched {updated} JSON file(s)")
    return 0


def main() -> None:
    load_project_dotenv()
    ap = argparse.ArgumentParser(description="Enrich extracted/*.json from Crossref /works/{doi}")
    ap.add_argument("--dry-run", action="store_true", help="Do not write files")
    ap.add_argument("--sleep", type=float, default=0.25, help="Seconds between requests")
    ap.add_argument("--limit", type=int, default=0, help="Max papers to process (0 = all)")
    ap.add_argument(
        "--skip-fetched",
        action="store_true",
        help="Skip JSON that already has crossref_fetched_at (re-run only missing)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch even when crossref_fetched_at is already set (fixes bad prior runs)",
    )
    ap.add_argument(
        "--backfill-authors-only",
        action="store_true",
        help="Only set top-level authors from crossref.authors (no API calls)",
    )
    args = ap.parse_args()

    if args.backfill_authors_only:
        backfill_top_level_authors(dry_run=args.dry_run)
        if args.dry_run:
            print("(dry-run: no files modified)")
        return

    try:
        import requests
    except ImportError:
        print("Install requests (pip install requests).")
        sys.exit(1)

    mail = os.getenv("CROSSREF_MAILTO", "").strip() or "anonymous@example.com"
    ua = f"DevreotesLabResearchChatbot/1.0 (mailto:{mail})"
    session = requests.Session()
    session.headers["User-Agent"] = ua

    json_files = sorted(EXTRACTED_DIR.glob("*.json"))
    stats = {"ok": 0, "fail": 0, "skipped_no_doi": 0, "skipped_already": 0, "written": 0}

    n_done = 0
    for path in json_files:
        if args.limit and n_done >= args.limit:
            break
        with path.open(encoding="utf-8") as fp:
            data = json.load(fp)

        raw_doi = data.get("doi")
        if not raw_doi or not str(raw_doi).strip():
            stats["skipped_no_doi"] += 1
            continue

        if args.skip_fetched and not args.force and data.get("crossref_fetched_at"):
            stats["skipped_already"] += 1
            continue

        n_done += 1
        doi = normalize_doi_for_storage(str(raw_doi).strip())
        ts = _utc_now_iso()

        if not doi:
            stats["fail"] += 1
            patch = {
                "crossref": {"error": "invalid_doi_after_normalize", "looked_up_doi": str(raw_doi)[:120]},
                "crossref_fetched_at": ts,
            }
            if not args.dry_run:
                data.update(patch)
                with path.open("w", encoding="utf-8") as fp:
                    json.dump(data, fp, ensure_ascii=False)
                stats["written"] += 1
            time.sleep(args.sleep)
            continue

        url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
        try:
            r = session.get(url, timeout=30)
        except requests.RequestException as e:
            stats["fail"] += 1
            if not args.dry_run:
                data["crossref"] = {"error": "request_error", "detail": str(e)[:200], "looked_up_doi": doi}
                data["crossref_fetched_at"] = ts
                with path.open("w", encoding="utf-8") as fp:
                    json.dump(data, fp, ensure_ascii=False)
                stats["written"] += 1
            time.sleep(args.sleep)
            continue

        if r.status_code == 404:
            stats["fail"] += 1
            if not args.dry_run:
                data["crossref"] = {"error": "404", "looked_up_doi": doi}
                data["crossref_fetched_at"] = ts
                with path.open("w", encoding="utf-8") as fp:
                    json.dump(data, fp, ensure_ascii=False)
                stats["written"] += 1
            time.sleep(args.sleep)
            continue

        if r.status_code != 200:
            stats["fail"] += 1
            if not args.dry_run:
                data["crossref"] = {
                    "error": f"http_{r.status_code}",
                    "looked_up_doi": doi,
                }
                data["crossref_fetched_at"] = ts
                with path.open("w", encoding="utf-8") as fp:
                    json.dump(data, fp, ensure_ascii=False)
                stats["written"] += 1
            time.sleep(args.sleep)
            continue

        try:
            msg = r.json().get("message") or {}
        except json.JSONDecodeError:
            stats["fail"] += 1
            if not args.dry_run:
                data["crossref"] = {"error": "invalid_json", "looked_up_doi": doi}
                data["crossref_fetched_at"] = ts
                with path.open("w", encoding="utf-8") as fp:
                    json.dump(data, fp, ensure_ascii=False)
                stats["written"] += 1
            time.sleep(args.sleep)
            continue

        stats["ok"] += 1
        enr = message_to_enrichment(msg if isinstance(msg, dict) else {})
        api_doi = normalize_doi_for_storage((enr.get("crossref") or {}).get("doi") or doi) or doi

        if not args.dry_run:
            data["doi"] = api_doi
            # Prefer Crossref when present; keep PDF heuristics if a field is missing.
            if enr.get("title"):
                data["title"] = enr["title"]
            else:
                cur_t = data.get("title")
                if cur_t is None or str(cur_t).strip() in ("", "[]"):
                    data["title"] = str(data.get("paper_id") or path.stem)
            if enr.get("year") is not None:
                data["year"] = enr["year"]
            if enr.get("journal"):
                data["journal"] = enr["journal"]
            else:
                cur_j = data.get("journal")
                if cur_j is not None and str(cur_j).strip() in ("", "[]"):
                    data["journal"] = None
            data["crossref"] = enr.get("crossref") or {}
            data["authors"] = list(enr.get("authors") or [])
            data["crossref_fetched_at"] = ts
            with path.open("w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False)
            stats["written"] += 1

        time.sleep(args.sleep)

    print("Crossref enrichment finished.")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if args.dry_run:
        print("(dry-run: no files modified)")


if __name__ == "__main__":
    main()
