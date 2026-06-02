import os
import sys
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

from .paths import embedding_model_name, load_project_dotenv, validate_embedding_dimension


load_project_dotenv()
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
model = SentenceTransformer(embedding_model_name())
validate_embedding_dimension(model.get_sentence_embedding_dimension())

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def _get_driver():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j credentials in .env.")
    return GraphDatabase.driver(uri, auth=(user, password))


def _embed_batch_size() -> int:
    return max(8, int(os.getenv("EMBED_BATCH_SIZE", "32")))


def embed_chunks():
    driver = _get_driver()
    with driver.session() as session:
        chunks = session.run(
            """
            MATCH (p:Paper)-[:HAS_CHUNK]->(c:Chunk)
            RETURN c.chunk_id AS chunk_id, c.text AS text, p.title AS title, p.paper_id AS paper_id
            ORDER BY p.paper_id, c.chunk_index
            """
        ).data()

    n = len(chunks)
    bs = _embed_batch_size()
    print(f"Embedding {n} chunks (batch size {bs})...", flush=True)

    for start in range(0, n, bs):
        batch = chunks[start : start + bs]
        texts = [f"{c.get('title', '')} {(c.get('text') or '')[:1600]}" for c in batch]
        vectors = model.encode(texts, show_progress_bar=False)
        rows = [
            {"chunk_id": batch[i]["chunk_id"], "embedding": vectors[i].tolist()}
            for i in range(len(batch))
        ]
        with driver.session() as session:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (c:Chunk {chunk_id: row.chunk_id})
                SET c.embedding = row.embedding
                """,
                rows=rows,
            )
        done = min(start + bs, n)
        print(f"  Embedded {done}/{n} chunks", flush=True)

    driver.close()
    print("All chunk embeddings created!", flush=True)


if __name__ == "__main__":
    embed_chunks()
