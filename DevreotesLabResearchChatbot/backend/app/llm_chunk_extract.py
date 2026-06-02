"""

Uses controlled Entity.types from GraphRAG_Schema v1 (excludes Gene/Protein; genes remain HGNC-backed).
Writes Chunk-[:MENTIONS]->Entity, optional Paper-[:HAS_TOPIC]->Entity for Topic, and Entity-[:RELATED_TO]->Entity.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from neo4j import GraphDatabase

from .paths import load_project_dotenv


load_project_dotenv()

# Schema §2 — omit Gene/Protein so we do not duplicate HGNC / ingest gene entities.
ALLOWED_ENTITY_TYPES = frozenset(
    {
        "Topic",
        "Method",
        "Pathway",
        "CellType",
        "ModelOrganism",
        "Disease",
        "Phenotype",
        "Other",
    }
)

ALLOWED_REL_KINDS = frozenset(
    {
        "ASSOCIATED_WITH",
        "PART_OF",
        "REGULATES",
        "INTERACTS_WITH",
        "ENABLES",
        "MEASURED_BY",
        "STUDIED_IN",
    }
)


def _get_driver():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j credentials in .env.")
    return GraphDatabase.driver(uri, auth=(user, password))


def _normalize_entity_key(etype: str, name: str) -> str:
    base = f"{etype.strip().lower()}:{(name or '').strip().lower()}"
    key = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    return (key or "other:unknown")[:240]


def _map_rel_kind(raw: str | None) -> str:
    if not raw:
        return "ASSOCIATED_WITH"
    u = str(raw).strip().upper().replace(" ", "_")
    return u if u in ALLOWED_REL_KINDS else "ASSOCIATED_WITH"


def _extract_llm() -> ChatOpenAI:
    model = os.getenv("OPENAI_EXTRACT_MODEL", "gpt-4o-mini")
    return ChatOpenAI(model=model, temperature=0)


def build_extraction_messages(chunk_text: str, paper_title: str) -> list:
    system = (
        "You extract structured factual mentions from ONE passage of a scientific paper. "
        "Output a single JSON object only (no markdown). "
        "Do NOT extract gene symbols or proteins — those are handled elsewhere. "
        f"Entity types must be exactly one of: {', '.join(sorted(ALLOWED_ENTITY_TYPES))}. "
        f"Relation kind must be one of: {', '.join(sorted(ALLOWED_REL_KINDS))}. "
        "Each relation's subject and object must match the name field of entities you list. "
        "Use short canonical names (e.g. 'chemotaxis', 'Dictyostelium'). "
        "If nothing fits, return {\"entities\":[],\"relations\":[]}."
    )
    text = (chunk_text or "")[:6000]
    human = (
        f"Paper title (context): {paper_title or 'Unknown'}\n\n"
        f"Passage:\n---\n{text}\n---\n\n"
        'Respond with JSON: {"entities":[{"name":string,"type":string}],"relations":[{"subject":string,"object":string,"kind":string}]}'
    )
    return [SystemMessage(content=system), HumanMessage(content=human)]


def extract_json_from_llm(chunk_text: str, paper_title: str) -> dict[str, Any]:
    llm = _extract_llm()
    messages = build_extraction_messages(chunk_text, paper_title)
    out = llm.invoke(messages)
    raw = (out.content or "").strip()
    # tolerate accidental fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("LLM output is not a JSON object")
    return data


def _sanitize_payload(data: dict) -> tuple[list[dict], list[dict]]:
    entities_in = data.get("entities") or []
    rels_in = data.get("relations") or []
    entities: list[dict] = []
    seen_keys: set[str] = set()
    for e in entities_in:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name", "")).strip()[:500]
        et = str(e.get("type", "Other")).strip()
        if et not in ALLOWED_ENTITY_TYPES:
            et = "Other"
        if len(name) < 2:
            continue
        ek = _normalize_entity_key(et, name)
        if ek in seen_keys:
            continue
        seen_keys.add(ek)
        entities.append({"name": name, "type": et, "entity_key": ek})

    name_to_key = {e["name"].lower(): e["entity_key"] for e in entities}
    relations: list[dict] = []
    for r in rels_in:
        if not isinstance(r, dict):
            continue
        sub = str(r.get("subject", "")).strip()
        obj = str(r.get("object", "")).strip()
        if len(sub) < 2 or len(obj) < 2:
            continue
        sk = name_to_key.get(sub.lower())
        ok = name_to_key.get(obj.lower())
        if not sk or not ok or sk == ok:
            continue
        relations.append(
            {
                "src_key": sk,
                "dst_key": ok,
                "kind": _map_rel_kind(r.get("kind")),
            }
        )
    return entities, relations


def apply_extraction_tx(tx, chunk_id: str, paper_id: str, entities: list[dict], relations: list[dict]):
    ts = datetime.now(timezone.utc).isoformat()
    for e in entities:
        tx.run(
            """
            MATCH (c:Chunk {chunk_id: $chunk_id})
            MERGE (ent:Entity {entity_key: $entity_key})
            SET ent.name = $name,
                ent.type = $etype
            MERGE (c)-[:MENTIONS]->(ent)
            """,
            chunk_id=chunk_id,
            entity_key=e["entity_key"],
            name=e["name"],
            etype=e["type"],
        )
        if e["type"] == "Topic":
            tx.run(
                """
                MATCH (ent:Entity {entity_key: $entity_key})
                MATCH (p:Paper {paper_id: $paper_id})
                MERGE (p)-[:HAS_TOPIC]->(ent)
                """,
                entity_key=e["entity_key"],
                paper_id=paper_id,
            )

    for r in relations:
        tx.run(
            """
            MATCH (a:Entity {entity_key: $src})
            MATCH (b:Entity {entity_key: $dst})
            MERGE (a)-[rel:RELATED_TO]->(b)
            SET rel.kind = $kind,
                rel.source_chunk_id = $chunk_id,
                rel.confidence = coalesce(rel.confidence, 0.75)
            """,
            src=r["src_key"],
            dst=r["dst_key"],
            kind=r["kind"],
            chunk_id=chunk_id,
        )

    tx.run(
        """
        MATCH (c:Chunk {chunk_id: $chunk_id})
        SET c.llm_extracted_at = $ts
        """,
        chunk_id=chunk_id,
        ts=ts,
    )


def extract_and_store_chunk(driver, chunk_id: str) -> dict[str, Any]:
    """Load chunk + paper from Neo4j, run LLM extraction, write graph updates."""
    with driver.session() as session:
        row = session.run(
            """
            MATCH (p:Paper)-[:HAS_CHUNK]->(c:Chunk {chunk_id: $chunk_id})
            RETURN c.text AS text, c.chunk_id AS chunk_id, p.paper_id AS paper_id, p.title AS title
            """,
            chunk_id=chunk_id,
        ).single()
        if not row:
            return {"ok": False, "error": "chunk_not_found", "chunk_id": chunk_id}

        data = extract_json_from_llm(row["text"], row["title"] or "")
        entities, relations = _sanitize_payload(data)

        def work(tx):
            apply_extraction_tx(tx, row["chunk_id"], row["paper_id"], entities, relations)

        session.execute_write(work)
        return {
            "ok": True,
            "chunk_id": chunk_id,
            "entities_written": len(entities),
            "relations_written": len(relations),
        }


def extract_batch(
    limit: int | None = None,
    skip_existing: bool = True,
) -> list[dict]:
    """
    Process up to `limit` chunks (default GRAPH_EXTRACT_LIMIT or 25).
    If skip_existing is True, only chunks without llm_extracted_at are processed.
    """
    lim = limit if limit is not None else int(os.getenv("GRAPH_EXTRACT_LIMIT", "25"))
    driver = _get_driver()
    results = []
    try:
        with driver.session() as session:
            res = session.run(
                """
                MATCH (p:Paper)-[:HAS_CHUNK]->(c:Chunk)
                WHERE c.embedding IS NOT NULL
                  AND ($skip = false OR c.llm_extracted_at IS NULL)
                RETURN c.chunk_id AS chunk_id
                LIMIT $limit
                """,
                limit=lim,
                skip=skip_existing,
            )
            chunk_ids = [r["chunk_id"] for r in res]
        for cid in chunk_ids:
            try:
                results.append(extract_and_store_chunk(driver, cid))
            except Exception as exc:  # noqa: BLE001
                results.append({"ok": False, "chunk_id": cid, "error": str(exc)})
    finally:
        driver.close()
    return results


if __name__ == "__main__":
    out = extract_batch()
    print(json.dumps(out, indent=2))
