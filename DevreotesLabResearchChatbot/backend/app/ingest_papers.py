import json
import os
import re
import spacy
from neo4j import GraphDatabase

from .author_standardize import author_records_for_ingest, load_author_alias_map
from .doi_utils import normalize_doi_for_storage
from .paths import (
    AUTHOR_ALIASES_PATH,
    EXTRACTED_DIR,
    HGNC_LOOKUP_PATH,
    load_project_dotenv,
    resolve_project_path,
)


load_project_dotenv()
nlp = spacy.load("en_core_sci_lg")

# Supplement scispaCy gene mentions with HGNC token scan (Phase 4)
_SUPPLEMENT_TOKEN_GENES = os.getenv("INGEST_SUPPLEMENT_TOKEN_GENES", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

def _load_hgnc_lookup() -> dict:
    if not HGNC_LOOKUP_PATH.exists():
        raise FileNotFoundError(f"Missing {HGNC_LOOKUP_PATH}. Run download_hgnc.py first.")
    with HGNC_LOOKUP_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _get_driver():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j credentials in .env.")
    return GraphDatabase.driver(uri, auth=(user, password))


def chunk_text(text: str, chunk_chars: int = 2000, overlap_chars: int = 200):
    text = (text or "").strip()
    if not text:
        return []
    if overlap_chars >= chunk_chars:
        overlap_chars = max(0, chunk_chars // 5)

    chunks = []
    start = 0
    idx = 0
    n = len(text)
    while start < n:
        end = min(n, start + chunk_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((idx, chunk))
            idx += 1
        if end >= n:
            break
        start = end - overlap_chars
    return chunks


def _claim_from_chunk(chunk_text_value: str) -> str:
    cleaned = re.sub(r"\s+", " ", (chunk_text_value or "").strip())
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    claim = parts[0] if parts else cleaned
    return claim[:280]


def _build_chunk_rows(paper_data: dict):
    paper_id = paper_data["paper_id"]
    rows = []
    for idx, chunk in chunk_text(paper_data.get("text", ""), chunk_chars=2000, overlap_chars=200):
        rows.append(
            {
                "chunk_id": f"{paper_id}_{idx}",
                "paper_id": paper_id,
                "chunk_index": idx,
                "text": chunk,
            }
        )
    return rows


def find_genes_in_text(text: str, hgnc_lookup: dict):
    """scispaCy entities plus optional ALLCAPS token pass validated against HGNC only."""
    found_genes = {}
    doc = nlp(text[:50000])
    for ent in doc.ents:
        token = ent.text.strip().upper()
        if token in hgnc_lookup:
            gene = hgnc_lookup[token]
            found_genes[gene["hgnc_id"]] = gene

    if _SUPPLEMENT_TOKEN_GENES and hgnc_lookup:
        head = (text or "")[:80000]
        for m in re.finditer(r"\b[A-Z][A-Z0-9]{1,12}\b", head):
            tok = m.group(0)
            if tok in hgnc_lookup:
                gene = hgnc_lookup[tok]
                found_genes[gene["hgnc_id"]] = gene

    return list(found_genes.values())


def resolve_bibliography_for_ingest(paper_data: dict) -> dict:
    """
    Paper bibliographic fields for Neo4j: match ``build_metadata_report_row`` / ``_metadata_report.json``.

    Title, year, journal, and DOI use the same top-level JSON keys as the report (DOI is normalized).
    """
    title = paper_data.get("title") or ""
    year = paper_data.get("year")
    journal = paper_data.get("journal")
    raw_doi = paper_data.get("doi")
    s = str(raw_doi).strip() if raw_doi is not None else ""
    doi = normalize_doi_for_storage(s) if s else None
    return {"title": title, "year": year, "journal": journal, "doi": doi}


def load_paper(session, paper_data: dict, genes: list, author_records: list, chunk_rows: list):
    bib = resolve_bibliography_for_ingest(paper_data)
    session.run(
        """
        MERGE (p:Paper {paper_id: $paper_id})
        SET p.title = $title,
            p.filename = $filename,
            p.source_file = $filename,
            p.text_preview = $text_preview,
            p.doi = $doi,
            p.year = $year,
            p.journal = $journal,
            p.pdf_author = $pdf_author,
            p.pdf_subject = $pdf_subject,
            p.pdf_keywords = $pdf_keywords,
            p.pdf_creator = $pdf_creator,
            p.pdf_producer = $pdf_producer,
            p.pdf_format = $pdf_format,
            p.text_via_ocr = $text_via_ocr
        """,
        paper_id=paper_data["paper_id"],
        title=bib["title"],
        text_preview=(paper_data.get("text") or "")[:500],
        filename=paper_data["filename"],
        text_via_ocr=bool(paper_data.get("text_via_ocr")),
        doi=bib["doi"],
        year=bib["year"],
        journal=bib["journal"],
        pdf_author=paper_data.get("pdf_author"),
        pdf_subject=paper_data.get("pdf_subject"),
        pdf_keywords=paper_data.get("pdf_keywords"),
        pdf_creator=paper_data.get("pdf_creator"),
        pdf_producer=paper_data.get("pdf_producer"),
        pdf_format=paper_data.get("pdf_format"),
    )

    if chunk_rows:
        session.run(
            """
            MATCH (p:Paper {paper_id: $paper_id})
            UNWIND $rows AS row
            MERGE (c:Chunk {chunk_id: row.chunk_id})
            SET c.paper_id = row.paper_id,
                c.chunk_index = row.chunk_index,
                c.text = row.text
            MERGE (p)-[:HAS_CHUNK]->(c)
            """,
            paper_id=paper_data["paper_id"],
            rows=chunk_rows,
        )

    for gene in genes:
        session.run(
            """
            MERGE (g:Gene {hgnc_id: $hgnc_id})
            SET g.official_symbol = $symbol
            WITH g
            MATCH (p:Paper {paper_id: $paper_id})
            MERGE (p)-[:MENTIONS]->(g)
            MERGE (e:Entity {entity_key: $entity_key})
            SET e.type = 'GENE', e.name = $symbol
            MERGE (p)-[:HAS_TOPIC]->(e)
            MERGE (e)-[:RELATED_TO]->(g)
            """,
            hgnc_id=gene["hgnc_id"],
            symbol=gene["official_symbol"],
            entity_key=f"gene:{gene['official_symbol'].upper()}",
            paper_id=paper_data["paper_id"],
        )

    for rec in author_records:
        author_key = rec["author_key"]
        name = rec["name"]
        orcid = rec.get("orcid")
        session.run(
            """
            MERGE (a:Author {author_key: $author_key})
            SET a.name = $name,
                a.orcid = coalesce($orcid, a.orcid)
            WITH a
            MATCH (p:Paper {paper_id: $paper_id})
            MERGE (a)-[:AUTHORED]->(p)
            MERGE (e:Entity {entity_key: $entity_key})
            SET e.type = 'AUTHOR', e.name = $name
            MERGE (p)-[:HAS_TOPIC]->(e)
            """,
            author_key=author_key,
            name=name,
            orcid=orcid,
            entity_key=f"author:{author_key}",
            paper_id=paper_data["paper_id"],
        )

    for row in chunk_rows:
        chunk_id = row["chunk_id"]
        chunk_text_value = row["text"]
        chunk_lower = chunk_text_value.lower()

        for gene in genes:
            symbol = (gene.get("official_symbol") or "").strip()
            if symbol and symbol.lower() in chunk_lower:
                entity_key = f"gene:{symbol.upper()}"
                session.run(
                    """
                    MATCH (c:Chunk {chunk_id: $chunk_id})
                    MERGE (e:Entity {entity_key: $entity_key})
                    SET e.type = 'GENE', e.name = $symbol
                    MERGE (c)-[:MENTIONS]->(e)
                    """,
                    chunk_id=chunk_id,
                    entity_key=entity_key,
                    symbol=symbol,
                )

        claim_text = _claim_from_chunk(chunk_text_value)
        if claim_text:
            claim_id = f"{paper_data['paper_id']}_claim_{row['chunk_index']}"
            session.run(
                """
                MATCH (c:Chunk {chunk_id: $chunk_id})
                MERGE (cl:Claim {claim_id: $claim_id})
                SET cl.text = $text
                MERGE (cl)-[:SUPPORTS]->(c)
                """,
                chunk_id=chunk_id,
                claim_id=claim_id,
                text=claim_text,
            )

            for gene in genes:
                symbol = (gene.get("official_symbol") or "").strip()
                if symbol and symbol.lower() in chunk_lower:
                    entity_key = f"gene:{symbol.upper()}"
                    session.run(
                        """
                        MATCH (cl:Claim {claim_id: $claim_id})
                        MERGE (e:Entity {entity_key: $entity_key})
                        SET e.type = 'GENE', e.name = $symbol
                        MERGE (cl)-[:ABOUT]->(e)
                        """,
                        claim_id=claim_id,
                        entity_key=entity_key,
                        symbol=symbol,
                    )


def ingest_all_papers(extracted_dir: str | None = None):
    extracted_path = resolve_project_path(extracted_dir, EXTRACTED_DIR)
    if not extracted_path.is_dir():
        raise FileNotFoundError(f"Missing extracted directory: {extracted_path}")

    hgnc_lookup = _load_hgnc_lookup()
    alias_map = load_author_alias_map(AUTHOR_ALIASES_PATH)
    driver = _get_driver()
    papers = []

    with driver.session() as session:
        for filename in os.listdir(extracted_path):
            if not filename.endswith(".json"):
                continue
            if filename.startswith("_"):
                continue
            path = extracted_path / filename
            with path.open("r", encoding="utf-8") as f:
                paper_data = json.load(f)

            bib = resolve_bibliography_for_ingest(paper_data)
            print(f"Processing: {bib.get('title', '')[:60]}...")
            genes = find_genes_in_text(paper_data.get("text", ""), hgnc_lookup)
            author_records = author_records_for_ingest(paper_data, alias_map)
            chunk_rows = _build_chunk_rows(paper_data)
            load_paper(session, paper_data, genes, author_records, chunk_rows)
            print(
                f"  -> {len(chunk_rows)} chunks, {len(genes)} genes, {len(author_records)} authors loaded"
            )
            papers.append(paper_data)

    driver.close()
    print(f"Ingestion complete: {len(papers)} papers loaded into Neo4j")
    return papers


if __name__ == "__main__":
    ingest_all_papers()
