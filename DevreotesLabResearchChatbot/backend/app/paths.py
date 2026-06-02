import os
from pathlib import Path


BACKEND_APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BACKEND_APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

# Default single-file path (for docs); actual loading uses `load_project_dotenv()`.
DOTENV_PATH = PROJECT_ROOT / ".env"


def load_project_dotenv() -> None:
    """Load `.env` from the Devreotes project root, with optional production overlay.

    1. If ``DEVREOTES_DOTENV`` is set, load only that file (relative paths are under ``PROJECT_ROOT``).
    2. Else load ``.env`` if present; if ``DEVREOTES_USE_PRODUCTION_ENV`` is truthy, load
       ``.env.production`` with ``override=True`` (e.g. Neo4j Aura ``NEO4J_*`` in production).
    """
    from dotenv import load_dotenv

    explicit = os.getenv("DEVREOTES_DOTENV", "").strip()
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        load_dotenv(p)
        return

    base = PROJECT_ROOT / ".env"
    if base.is_file():
        load_dotenv(base)

    use_prod = os.getenv("DEVREOTES_USE_PRODUCTION_ENV", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if use_prod:
        prod = PROJECT_ROOT / ".env.production"
        if prod.is_file():
            load_dotenv(prod, override=True)
HGNC_LOOKUP_PATH = PROJECT_ROOT / "hgnc_lookup.json"
AUTHOR_ALIASES_PATH = PROJECT_ROOT / "author_aliases.json"
PAPERS_DIR = PROJECT_ROOT / "papers"
EXTRACTED_DIR = PROJECT_ROOT / "extracted"


def resolve_project_path(value: str | None, default_path: Path) -> Path:
    if value is None:
        return default_path
    p = Path(value)
    return p if p.is_absolute() else PROJECT_ROOT / p


# Sentence-Transformers Hugging Face id — must match between create_embeddings.py and retrieval.py.
DEFAULT_EMBEDDING_MODEL = "pritamdeka/PubMedBERT-mnli-snli-scinli-scitail-mednli-stsb"

# Output size of DEFAULT_EMBEDDING_MODEL (Neo4j vector index must match; override via EMBEDDING_VECTOR_DIMENSIONS if you change models).
DEFAULT_EMBEDDING_VECTOR_DIMENSIONS = 768

# Neo4j native vector index on Chunk.embedding — name must stay in sync with retrieval Cypher.
CHUNK_VECTOR_INDEX_NAME = "chunk_embedding_idx"

# Neo4j full-text index on Chunk.text — hybrid retrieval with vector search (setup_schema).
CHUNK_FULLTEXT_INDEX_NAME = "chunk_fulltext_idx"

# Neo4j `vector.similarity_function` (see CREATE VECTOR INDEX OPTIONS).
_ALLOWED_VECTOR_SIMILARITY = frozenset({"cosine", "euclidean"})
DEFAULT_VECTOR_SIMILARITY_FUNCTION = "cosine"


def embedding_model_name() -> str:
    """Model used to encode chunks (offline) and queries (online). Change only with full re-embed."""
    raw = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    s = (raw or "").strip()
    return s if s else DEFAULT_EMBEDDING_MODEL


def embedding_vector_dimensions() -> int:
    """Vector length for Neo4j Chunk.embedding and the vector index. Must match SentenceTransformer output."""
    raw = (os.getenv("EMBEDDING_VECTOR_DIMENSIONS") or "").strip()
    if raw:
        try:
            n = int(raw)
            if n > 0:
                return n
        except ValueError:
            pass
    return DEFAULT_EMBEDDING_VECTOR_DIMENSIONS


def vector_similarity_function() -> str:
    """Neo4j index similarity: cosine or euclidean."""
    raw = (os.getenv("EMBEDDING_VECTOR_SIMILARITY") or "").strip().lower()
    if raw in _ALLOWED_VECTOR_SIMILARITY:
        return raw
    return DEFAULT_VECTOR_SIMILARITY_FUNCTION


def chunk_embedding_vector_index_cypher() -> str:
    """CREATE VECTOR INDEX for :Chunk(embedding); dimensions and similarity from env-backed helpers above."""
    dim = embedding_vector_dimensions()
    sim = vector_similarity_function()
    name = CHUNK_VECTOR_INDEX_NAME
    return (
        f"CREATE VECTOR INDEX {name} IF NOT EXISTS "
        f"FOR (c:Chunk) ON (c.embedding) "
        f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dim}, `vector.similarity_function`: '{sim}'}}}}"
    )


def validate_embedding_dimension(actual_dim: int) -> None:
    """Ensure SentenceTransformer output size matches Neo4j index / EMBEDDING_VECTOR_DIMENSIONS."""
    expected = embedding_vector_dimensions()
    if int(actual_dim) != int(expected):
        raise RuntimeError(
            f"Embedding model outputs {actual_dim}-dim vectors but config expects {expected}. "
            "Set EMBEDDING_VECTOR_DIMENSIONS to match the model, update DEFAULT_EMBEDDING_VECTOR_DIMENSIONS in "
            "paths.py, recreate the vector index (setup_schema), and re-embed chunks."
        )
