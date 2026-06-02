"""
Normalize extracted/*.json metadata (title, authors, year, optional DOI) and write a report.

Skips bibliographic overwrites for Crossref-enriched papers unless --touch-crossref.

Run from project root:
  PYTHONPATH=. python backend/scripts/clean_extracted.py --dry-run
  PYTHONPATH=. python backend/scripts/clean_extracted.py --write
  PYTHONPATH=. python backend/scripts/clean_extracted.py --write --normalize-text
  PYTHONPATH=. python backend/scripts/clean_extracted.py --paper-id 010 --write

Report path: extracted/_metadata_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.extracted_clean import (
    build_metadata_report_row,
    clean_paper_json,
)
from backend.app.paths import EXTRACTED_DIR, load_project_dotenv


def main() -> None:
    load_project_dotenv()
    ap = argparse.ArgumentParser(description="Clean / normalize extracted paper JSON + metadata report")
    ap.add_argument("--dry-run", action="store_true", help="Print summary only; do not write JSON files")
    ap.add_argument("--write", action="store_true", help="Write updated extracted/*.json files")
    ap.add_argument(
        "--normalize-text",
        action="store_true",
        help="Strip OCR page-marker lines from the full text field",
    )
    ap.add_argument(
        "--touch-crossref",
        action="store_true",
        help="Also run heuristics on papers with successful Crossref blocks (default: skip them)",
    )
    ap.add_argument("--paper-id", type=str, default="", help="Only process this paper_id (e.g. 010)")
    args = ap.parse_args()

    if not args.dry_run and not args.write:
        print("Specify --dry-run or --write")
        sys.exit(1)

    json_files = sorted(EXTRACTED_DIR.glob("*.json"))
    if args.paper_id:
        pid = args.paper_id.strip()
        json_files = [p for p in json_files if p.stem == pid]
        if not json_files:
            print(f"No extracted/{pid}.json")
            sys.exit(1)

    report_rows: list[dict] = []
    changed = 0
    for path in json_files:
        if path.name.startswith("_"):
            continue
        with path.open(encoding="utf-8") as fp:
            data = json.load(fp)
        updated, chg = clean_paper_json(
            data,
            touch_crossref_papers=args.touch_crossref,
            normalize_text=args.normalize_text,
        )
        report_rows.append(build_metadata_report_row(updated))
        if chg:
            changed += 1
            print(f"{path.stem}: {chg}")
        if args.write:
            with path.open("w", encoding="utf-8") as fp:
                json.dump(updated, fp, ensure_ascii=False)

    report_rows.sort(key=lambda r: (len(str(r.get("paper_id", ""))), str(r.get("paper_id", ""))))
    report_path = EXTRACTED_DIR / "_metadata_report.json"
    if args.write or args.dry_run:
        payload = {
            "generated_by": "clean_extracted.py",
            "papers": report_rows,
            "summary": {
                "total": len(report_rows),
                "title_junk_remaining": sum(1 for r in report_rows if r.get("title_junk")),
                "with_doi": sum(1 for r in report_rows if r.get("doi")),
                "crossref_ok": sum(1 for r in report_rows if r.get("crossref_ok")),
                "with_authors_list": sum(1 for r in report_rows if r.get("authors")),
            },
        }
        if args.write:
            with report_path.open("w", encoding="utf-8") as fp:
                json.dump(payload, fp, ensure_ascii=False)
            print(f"Wrote {report_path} ({len(report_rows)} papers)")
        else:
            print(f"[dry-run] would write {report_path}; title_junk count: {payload['summary']['title_junk_remaining']}")

    print(f"Files with heuristic changes logged: {changed}")


if __name__ == "__main__":
    main()
