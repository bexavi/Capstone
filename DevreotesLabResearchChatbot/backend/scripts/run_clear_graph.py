"""
Delete every node and relationship in the configured Neo4j database.

Uses the same env loading as the rest of the backend (.env, optional .env.production).
Re-run setup_schema + ingest + embeddings afterward.

  python backend/scripts/run_clear_graph.py --yes
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from neo4j import GraphDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.paths import load_project_dotenv


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wipe the Neo4j graph (MATCH (n) DETACH DELETE n).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required. Confirms you intend to delete all graph data.",
    )
    args = parser.parse_args()
    if not args.yes:
        print("Aborted: pass --yes to confirm full graph deletion.", file=sys.stderr)
        return 1

    load_project_dotenv()
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    if not all([uri, user, password]):
        print("Missing NEO4J_URI, NEO4J_USER, or NEO4J_PASSWORD.", file=sys.stderr)
        return 1

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            # Count first (readable feedback)
            n = session.run("MATCH (n) RETURN count(n) AS c").single()
            count_before = n["c"] if n else 0
            session.run("MATCH (n) DETACH DELETE n")
            print(f"Removed {count_before} nodes (and all attached relationships).")
    finally:
        driver.close()

    print("Next: python backend/scripts/run_setup_schema.py")
    print("      python backend/scripts/run_ingest_papers.py")
    print("      python backend/scripts/run_create_embeddings.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
