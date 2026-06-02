import json
import os
import re
import threading
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer, util as st_util

from .paths import (
    CHUNK_FULLTEXT_INDEX_NAME,
    CHUNK_VECTOR_INDEX_NAME,
    HGNC_LOOKUP_PATH,
    embedding_model_name,
    load_project_dotenv,
    validate_embedding_dimension,
)
from .fulltext_query import build_fulltext_lucene_query


load_project_dotenv()
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

_embedding_model: SentenceTransformer | None = None
_embedding_model_lock = threading.Lock()


def _get_embedding_model() -> SentenceTransformer:
    """Load SentenceTransformer on first use (avoids blocking process import / unrelated routes)."""
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    with _embedding_model_lock:
        if _embedding_model is not None:
            return _embedding_model
        m = SentenceTransformer(embedding_model_name())
        validate_embedding_dimension(m.get_sentence_embedding_dimension())
        _embedding_model = m
        return _embedding_model


def _get_driver():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j credentials in .env.")
    return GraphDatabase.driver(uri, auth=(user, password))


def _load_hgnc_lookup() -> dict:
    if not HGNC_LOOKUP_PATH.exists():
        return {}
    with HGNC_LOOKUP_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


driver = _get_driver()
hgnc_lookup = _load_hgnc_lookup()


def _normalize_rows(rows, route: str):
    normalized = []
    for row in rows:
        normalized.append(
            {
                "paper_id": row.get("paper_id") or row.get("id"),
                "id": row.get("paper_id") or row.get("id"),
                "title": row.get("title"),
                "source_file": row.get("source_file"),
                "chunk_id": row.get("chunk_id"),
                "text": row.get("text"),
                "score": float(row["score"]) if row.get("score") is not None else None,
                "gene": row.get("gene"),
                "author": row.get("author"),
                "route": route,
            }
        )
    return normalized


def _normalize_author_query(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")


def _vector_fetch_k(top_k: int) -> int:
    mult = int(os.getenv("RAG_VECTOR_FETCH_MULTIPLIER", "4"))
    cap = int(os.getenv("RAG_VECTOR_FETCH_CAP", "120"))
    return min(max(top_k * mult, top_k * 2), cap)


def _fulltext_enabled() -> bool:
    return os.getenv("RAG_FULLTEXT", "true").lower() in ("1", "true", "yes", "on")


def _merge_chunk_hits_keep_best_score(*lists: list) -> list:
    by_id: dict[str, dict] = {}
    for lst in lists:
        for r in lst:
            cid = r.get("chunk_id")
            if not cid:
                continue
            sc = float(r.get("score") or 0.0)
            prev = by_id.get(cid)
            if prev is None or sc > float(prev.get("score") or 0.0):
                by_id[cid] = dict(r)
    return list(by_id.values())


def _max_chunks_per_paper() -> int:
    return max(1, int(os.getenv("RAG_MAX_CHUNKS_PER_PAPER", "2")))


def _rerank_enabled() -> bool:
    return os.getenv("RAG_RERANK", "").lower() in ("1", "true", "yes", "on")


def _dedupe_target_k(top_k: int) -> int:
    """When reranking, keep a larger per-paper-deduped pool so reordering matters."""
    if not _rerank_enabled():
        return top_k
    pool = int(os.getenv("RAG_RERANK_POOL", "32"))
    return max(top_k, min(max(pool, top_k), 96))


def _graph_expand_enabled() -> bool:
    return os.getenv("RAG_GRAPH_EXPAND", "").lower() in ("1", "true", "yes", "on")


def _expand_rows_shared_entities(session, rows: list, route: str) -> list:
    """
    Phase 5 — add same-paper chunks that share at least one LLM Entity (not GENE/AUTHOR)
    with any seed chunk, scored below the seed hit.
    """
    if not rows or not _graph_expand_enabled():
        return rows

    chunk_ids = [r["chunk_id"] for r in rows if r.get("chunk_id")][:40]
    if not chunk_ids:
        return rows

    extra_cap = max(1, int(os.getenv("RAG_GRAPH_EXPAND_EXTRA", "8")))
    ratio = float(os.getenv("RAG_GRAPH_EXPAND_SCORE_RATIO", "0.88"))
    floor = float(os.getenv("RAG_GRAPH_EXPAND_SCORE_FLOOR", "0.36"))
    seed_scores = {r["chunk_id"]: float(r.get("score") or 0.0) for r in rows if r.get("chunk_id")}

    recs = session.run(
        """
        UNWIND $chunk_ids AS cid
        MATCH (seed:Chunk {chunk_id: cid})-[:MENTIONS]->(e:Entity)
        WHERE NOT e.type IN ['GENE', 'AUTHOR']
        MATCH (e)<-[:MENTIONS]-(other:Chunk)
        MATCH (p:Paper)-[:HAS_CHUNK]->(seed)
        MATCH (p)-[:HAS_CHUNK]->(other)
        WHERE other.chunk_id <> seed.chunk_id
        WITH other, p, seed, count(DISTINCT e) AS shared
        RETURN DISTINCT
          other.chunk_id AS chunk_id,
          other.text AS text,
          p.paper_id AS paper_id,
          p.title AS title,
          coalesce(p.source_file, p.filename) AS source_file,
          shared,
          seed.chunk_id AS seed_chunk_id
        ORDER BY shared DESC
        LIMIT $limit
        """,
        chunk_ids=chunk_ids,
        limit=extra_cap,
    ).data()

    seen = {r["chunk_id"] for r in rows if r.get("chunk_id")}
    merged = list(rows)
    for rec in recs:
        cid = rec.get("chunk_id")
        if not cid or cid in seen:
            continue
        seed_id = rec.get("seed_chunk_id")
        base = seed_scores.get(seed_id, 0.35)
        score = max(floor, min(1.0, base * ratio))
        merged.append(
            {
                "paper_id": rec.get("paper_id"),
                "id": rec.get("paper_id"),
                "title": rec.get("title"),
                "source_file": rec.get("source_file"),
                "chunk_id": cid,
                "text": rec.get("text"),
                "score": score,
                "gene": None,
                "author": None,
                "route": route,
            }
        )
        seen.add(cid)

    merged.sort(key=lambda r: float(r.get("score") or 0.0), reverse=True)
    return merged


def _dedupe_by_paper(rows: list, top_k: int, max_per_paper: int | None = None) -> list:
    """Keep highest-scoring chunks first; at most `max_per_paper` chunks per paper_id."""
    if not rows:
        return []
    mpp = max_per_paper if max_per_paper is not None else _max_chunks_per_paper()
    sorted_rows = sorted(rows, key=lambda r: float(r.get("score") or 0), reverse=True)
    counts: dict[str, int] = {}
    out: list = []
    for row in sorted_rows:
        pid = str(row.get("paper_id") or row.get("id") or "unknown")
        if counts.get(pid, 0) >= mpp:
            continue
        out.append(row)
        counts[pid] = counts.get(pid, 0) + 1
        if len(out) >= top_k:
            break
    return out


def _maybe_rerank_by_query_embedding(question: str, rows: list, top_k: int) -> list:
    """
    Optional second-stage rerank using the same bi-encoder (query vs title+chunk text).
    Enable with RAG_RERANK=true.
    """
    if not _rerank_enabled():
        return rows[:top_k]
    if len(rows) <= 1:
        return rows[:top_k]
    enc = _get_embedding_model()
    q_emb = enc.encode(question, convert_to_tensor=True, normalize_embeddings=True)
    texts = [f"{r.get('title', '')} {(r.get('text') or '')[:1600]}" for r in rows]
    c_embs = enc.encode(texts, convert_to_tensor=True, normalize_embeddings=True)
    sims = st_util.cos_sim(q_emb, c_embs)[0]
    order = sims.argsort(descending=True).cpu().tolist()
    out = []
    for i in order[:top_k]:
        row = dict(rows[i])
        row["score"] = float(sims[i].item())
        out.append(row)
    return out


def vector_search(question: str, top_k: int = 5):
    fetch_k = _vector_fetch_k(top_k)
    query_embedding = _get_embedding_model().encode(question).tolist()
    ft_limit = min(
        max(fetch_k, top_k * 2),
        int(os.getenv("RAG_FULLTEXT_RESULT_CAP", "40")),
    )
    with driver.session() as session:
        results = session.run(
            f"""
            CALL db.index.vector.queryNodes('{CHUNK_VECTOR_INDEX_NAME}', $top_k, $embedding)
            YIELD node AS c, score
            MATCH (p:Paper)-[:HAS_CHUNK]->(c)
            RETURN
              p.title AS title,
              p.paper_id AS paper_id,
              coalesce(p.source_file, p.filename) AS source_file,
              c.chunk_id AS chunk_id,
              c.text AS text,
              score
            ORDER BY score DESC
            """,
            top_k=fetch_k,
            embedding=query_embedding,
        ).data()
        ft_rows: list = []
        if _fulltext_enabled():
            ft_q = build_fulltext_lucene_query(question)
            if ft_q:
                try:
                    ft_rows = session.run(
                        f"""
                        CALL db.index.fulltext.queryNodes('{CHUNK_FULLTEXT_INDEX_NAME}', $ft_q)
                        YIELD node AS c, score AS fts
                        MATCH (p:Paper)-[:HAS_CHUNK]->(c)
                        RETURN
                          p.title AS title,
                          p.paper_id AS paper_id,
                          coalesce(p.source_file, p.filename) AS source_file,
                          c.chunk_id AS chunk_id,
                          c.text AS text,
                          fts
                        ORDER BY fts DESC
                        LIMIT $ft_limit
                        """,
                        ft_q=ft_q,
                        ft_limit=ft_limit,
                    ).data()
                except Exception:
                    ft_rows = []
        for i, row in enumerate(ft_rows):
            row.pop("fts", None)
            row["score"] = max(0.36, 0.52 - i * 0.012)
    normalized = _normalize_rows(results, route="semantic")
    if ft_rows:
        normalized = _merge_chunk_hits_keep_best_score(
            normalized,
            _normalize_rows(ft_rows, route="semantic"),
        )
        normalized.sort(key=lambda r: float(r.get("score") or 0.0), reverse=True)
    deduped = _dedupe_by_paper(
        normalized,
        top_k=_dedupe_target_k(top_k),
        max_per_paper=_max_chunks_per_paper(),
    )
    with driver.session() as session:
        deduped = _expand_rows_shared_entities(session, deduped, route="semantic")
    pool = max(_dedupe_target_k(top_k), top_k + max(0, int(os.getenv("RAG_GRAPH_EXPAND_EXTRA", "8"))))
    deduped = _dedupe_by_paper(deduped, top_k=pool, max_per_paper=_max_chunks_per_paper())
    return _maybe_rerank_by_query_embedding(question, deduped, top_k)


def _graph_search_by_gene_strict(hgnc_id: str, official_symbol: str, fetch_k: int, query_embedding: list) -> list:
    with driver.session() as session:
        return session.run(
            f"""
            CALL db.index.vector.queryNodes('{CHUNK_VECTOR_INDEX_NAME}', $top_k, $embedding)
            YIELD node AS c, score
            MATCH (p:Paper)-[:HAS_CHUNK]->(c)
            MATCH (p:Paper)-[:MENTIONS]->(g:Gene {hgnc_id: $hgnc_id})
            OPTIONAL MATCH (a:Author)-[:AUTHORED]->(p)
            WHERE toLower(c.text) CONTAINS toLower($symbol)
            RETURN
              p.paper_id AS paper_id,
              p.title AS title,
              coalesce(p.source_file, p.filename) AS source_file,
              c.text AS text,
              c.chunk_id AS chunk_id,
              score,
              g.official_symbol AS gene,
              a.name AS author
            ORDER BY score DESC, p.title, c.chunk_index
            """,
            hgnc_id=hgnc_id,
            symbol=official_symbol,
            top_k=fetch_k,
            embedding=query_embedding,
        ).data()


def _graph_search_by_gene_relaxed(hgnc_id: str, fetch_k: int, query_embedding: list) -> list:
    """Vector-ranked chunks from papers that mention the gene (no substring filter on chunk text)."""
    with driver.session() as session:
        return session.run(
            f"""
            CALL db.index.vector.queryNodes('{CHUNK_VECTOR_INDEX_NAME}', $top_k, $embedding)
            YIELD node AS c, score
            MATCH (p:Paper)-[:HAS_CHUNK]->(c)
            MATCH (p:Paper)-[:MENTIONS]->(g:Gene {hgnc_id: $hgnc_id})
            OPTIONAL MATCH (a:Author)-[:AUTHORED]->(p)
            RETURN
              p.paper_id AS paper_id,
              p.title AS title,
              coalesce(p.source_file, p.filename) AS source_file,
              c.text AS text,
              c.chunk_id AS chunk_id,
              score,
              g.official_symbol AS gene,
              a.name AS author
            ORDER BY score DESC, p.title, c.chunk_index
            """,
            hgnc_id=hgnc_id,
            top_k=fetch_k,
            embedding=query_embedding,
        ).data()


def graph_search_by_gene(gene_name: str, question: str | None = None, top_k: int = 20):
    gene_key = gene_name.upper()
    if gene_key not in hgnc_lookup:
        return []
    gene_entry = hgnc_lookup[gene_key]
    hgnc_id = gene_entry["hgnc_id"]
    official_symbol = gene_entry.get("official_symbol") or gene_key
    qtext = question or gene_name
    query_embedding = _get_embedding_model().encode(qtext).tolist()
    fetch_k = _vector_fetch_k(top_k)

    results = _graph_search_by_gene_strict(hgnc_id, official_symbol, fetch_k, query_embedding)
    if not results:
        results = _graph_search_by_gene_relaxed(hgnc_id, fetch_k, query_embedding)

    normalized = _normalize_rows(results, route="gene")
    deduped = _dedupe_by_paper(
        normalized,
        top_k=_dedupe_target_k(top_k),
        max_per_paper=_max_chunks_per_paper(),
    )
    with driver.session() as session:
        deduped = _expand_rows_shared_entities(session, deduped, route="gene")
    pool = max(_dedupe_target_k(top_k), top_k + max(0, int(os.getenv("RAG_GRAPH_EXPAND_EXTRA", "8"))))
    deduped = _dedupe_by_paper(deduped, top_k=pool, max_per_paper=_max_chunks_per_paper())
    return _maybe_rerank_by_query_embedding(qtext, deduped, top_k)


def graph_search_by_author(author_name: str, question: str | None = None, top_k: int = 30):
    """
    Hybrid retrieval: vector similarity over chunks, restricted to papers authored by a matching Author.
    Produces real cosine scores from the chunk index (unlike fixed 1.0).
    """
    normalized_key = _normalize_author_query(author_name)
    qtext = question or author_name
    query_embedding = _get_embedding_model().encode(qtext).tolist()
    fetch_k = min(_vector_fetch_k(top_k), 200)

    with driver.session() as session:
        results = session.run(
            f"""
            CALL db.index.vector.queryNodes('{CHUNK_VECTOR_INDEX_NAME}', $top_k, $embedding)
            YIELD node AS c, score
            MATCH (p:Paper)-[:HAS_CHUNK]->(c)
            MATCH (a:Author)-[:AUTHORED]->(p)
            WHERE toLower(a.name) CONTAINS toLower($name)
               OR toLower(a.author_key) CONTAINS toLower($author_key)
            RETURN
              p.paper_id AS paper_id,
              p.title AS title,
              coalesce(p.source_file, p.filename) AS source_file,
              c.text AS text,
              c.chunk_id AS chunk_id,
              score,
              a.name AS author
            ORDER BY score DESC, p.title, c.chunk_index
            """,
            name=author_name,
            author_key=normalized_key,
            top_k=fetch_k,
            embedding=query_embedding,
        ).data()
    rows = _normalize_rows(results, route="author")
    deduped = _dedupe_by_paper(
        rows,
        top_k=_dedupe_target_k(top_k),
        max_per_paper=_max_chunks_per_paper(),
    )
    with driver.session() as session:
        deduped = _expand_rows_shared_entities(session, deduped, route="author")
    pool = max(_dedupe_target_k(top_k), top_k + max(0, int(os.getenv("RAG_GRAPH_EXPAND_EXTRA", "8"))))
    deduped = _dedupe_by_paper(deduped, top_k=pool, max_per_paper=_max_chunks_per_paper())
    return _maybe_rerank_by_query_embedding(qtext, deduped, top_k)




def graph_corpus_meta() -> dict:
    """
    Exact node counts in the Neo4j graph (one round-trip).
    Used for questions like "how many papers in the corpus" — not passage retrieval.
    """
    with driver.session() as session:
        row = session.run(
            """
            MATCH (p:Paper)
            WITH count(p) AS paper_count
            MATCH (c:Chunk)
            WITH paper_count, count(c) AS chunk_count
            MATCH (g:Gene)
            WITH paper_count, chunk_count, count(g) AS gene_count
            MATCH (a:Author)
            WITH paper_count, chunk_count, gene_count, count(a) AS author_count
            MATCH (e:Entity)
            WITH paper_count, chunk_count, gene_count, author_count, count(e) AS entity_count
            MATCH (cl:Claim)
            RETURN paper_count, chunk_count, gene_count, author_count, entity_count, count(cl) AS claim_count
            """
        ).single()
    if not row:
        return {
            "paper_count": 0,
            "chunk_count": 0,
            "gene_count": 0,
            "author_count": 0,
            "entity_count": 0,
            "claim_count": 0,
        }
    return dict(row)


def themes_limit() -> int:
    """Single source of truth for themes result cap used by retrieval and prompt context."""
    raw = os.getenv("THEMES_LIMIT", "").strip()
    if raw:
        return max(5, int(raw))
    # Backward compatibility
    return max(5, int(os.getenv("THEMES_GENE_LIMIT", "20")))


def graph_search_author_publication_stats():
    """
    Authors (AUTHORED) with at least N distinct papers — for "who appears on multiple papers" questions.
    Env: AUTHOR_STATS_MIN_PAPERS (default 2), AUTHOR_STATS_LIMIT (default 40).
    """
    min_papers = max(2, int(os.getenv("AUTHOR_STATS_MIN_PAPERS", "2")))
    limit = max(5, int(os.getenv("AUTHOR_STATS_LIMIT", "40")))
    with driver.session() as session:
        results = session.run(
            """
            MATCH (a:Author)-[:AUTHORED]->(p:Paper)
            WITH a, count(DISTINCT p) AS paper_count
            WHERE paper_count >= $min_papers
            RETURN coalesce(a.name, a.author_key) AS author, a.author_key AS author_key, paper_count
            ORDER BY paper_count DESC, author
            LIMIT $limit
            """,
            min_papers=min_papers,
            limit=limit,
        ).data()
    return results


def graph_search_author_directory():
    """
    All authors with at least min_papers distinct :Paper via :AUTHORED (default min 1).
    For full bibliography / directory questions. Returns (rows, meta) with truncation flag.

    Env: AUTHOR_DIRECTORY_MIN_PAPERS (default 1), AUTHOR_DIRECTORY_LIMIT (default 200).
    """
    min_papers = max(1, int(os.getenv("AUTHOR_DIRECTORY_MIN_PAPERS", "1")))
    limit = max(10, int(os.getenv("AUTHOR_DIRECTORY_LIMIT", "200")))
    fetch_limit = limit + 1
    with driver.session() as session:
        results = session.run(
            """
            MATCH (a:Author)-[:AUTHORED]->(p:Paper)
            WITH a, count(DISTINCT p) AS paper_count
            WHERE paper_count >= $min_papers
            RETURN coalesce(a.name, a.author_key) AS author, a.author_key AS author_key, paper_count
            ORDER BY paper_count DESC, author
            LIMIT $limit
            """,
            min_papers=min_papers,
            limit=fetch_limit,
        ).data()
    truncated = len(results) > limit
    rows = results[:limit]
    meta = {
        "directory_limit": limit,
        "truncated": truncated,
        "min_papers": min_papers,
        "metric": "distinct_papers_per_author",
        "sort": "paper_count_desc",
    }
    return rows, meta


def graph_search_research_themes():
    """
    Aggregate gene mention frequency across papers (graph-derived, not NLP 'themes').
    Optional filter: THEMES_MIN_PAPER_COUNT (default 1) drops very rare symbols.

    Returns (rows, meta) where meta includes truncation detection via LIMIT+1 fetch.
    """
    min_papers = max(1, int(os.getenv("THEMES_MIN_PAPER_COUNT", "1")))
    limit = themes_limit()
    fetch_limit = limit + 1
    with driver.session() as session:
        results = session.run(
            """
            MATCH (p:Paper)-[:MENTIONS]->(g:Gene)
            WITH g.official_symbol AS gene, count(DISTINCT p) AS paper_count
            WHERE paper_count >= $min_papers
            RETURN gene, paper_count
            ORDER BY paper_count DESC
            LIMIT $limit
            """,
            min_papers=min_papers,
            limit=fetch_limit,
        ).data()
    truncated = len(results) > limit
    rows = results[:limit]
    meta = {
        "themes_limit": limit,
        "truncated": truncated,
        "metric": "distinct_papers_per_gene",
        "sort": "paper_count_desc",
    }
    return rows, meta
