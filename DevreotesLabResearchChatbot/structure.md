Overall structure (Devreotes Lab Research Chatbot)

> **Architecture & usage (step-by-step, plain English):** [`ARCHITECTURE_AND_USAGE.md`](./ARCHITECTURE_AND_USAGE.md) in this same folder. A duplicate copy lives at the **repository root** as `ARCHITECTURE_AND_USAGE.md` (next to the `chatBot/` folder) so it shows up when you open the project root in the file tree.

This project now follows a notebook-style backend layout:

- `backend/app/` → reusable backend modules
- `backend/scripts/` → runnable entrypoints
- `app.py` → Gradio UI (imports backend modules)
- `nuxt/` → Nuxt UI frontend that calls backend through a Python bridge

Pipeline:

PDFs → extracted JSON → Neo4j graph (`Paper`, `Chunk`, `Gene`, `Author`, `Entity`, `Claim`) → chunk embeddings → retrieval/routing → LLM answer with citations.

Main backend modules:

- `backend/app/extract_pdfs.py`
  - Extracts text with PyMuPDF
  - Uses metadata-first title extraction with heuristic fallback
  - Adds best-effort `doi`, `year`, `journal` from the first pages of text and PDF metadata fields (`pdf_author`, `pdf_subject`, etc.) into each JSON under `extracted/`

- `backend/app/setup_schema.py`
  - Creates constraints/indexes including `chunk_embedding_idx`, and range/text indexes on `Paper.year` and `Paper.doi` where supported

- `backend/app/ingest_papers.py`
  - Loads extracted JSON into Neo4j (`Paper` gets `doi`, `year`, `journal`, and `pdf_*` hints when present)
  - Author list prefers `pdf_author` when usable; otherwise scans front matter
  - Optional HGNC-only token pass for gene linking (`INGEST_SUPPLEMENT_TOKEN_GENES`, default on)
  - Creates chunk-level graph structure and claim/entity links

- `backend/app/create_embeddings.py`
  - Creates embeddings on `Chunk.embedding`

- `backend/app/llm_chunk_extract.py` (Phase 5)
  - OpenAI JSON extraction of non-gene entities (Topic, Method, Pathway, …) and `RELATED_TO` edges from chunk text
  - Writes `Chunk-[:MENTIONS]->Entity`, `Paper-[:HAS_TOPIC]->Entity` for topics, sets `Chunk.llm_extracted_at`
  - Run after embeddings: `python backend/scripts/run_llm_graph_extract.py [limit]`

- `backend/app/retrieval.py`
  - Semantic, gene, author, and **gene-mention aggregates** (internal route key `themes`) over chunk-first graph
  - Per-paper dedupe; optional rerank with `RAG_RERANK`; when enabled, `RAG_RERANK_POOL` widens the deduped pool before cutting to `RAG_TOP_K`
  - Optional **graph expansion** (`RAG_GRAPH_EXPAND`): same-paper chunks that share LLM-extracted `Entity` nodes with vector hits (Phase 5)

- `backend/app/router.py`
  - Order: themes → corpus ranking patterns (“which kinases are most…”) → author → gene vocabulary → semantic
  - Gene vocabulary uses `\bgenes?\b` so words like “general” do not trigger the gene route

- `backend/app/chatbot.py`
  - Query routing + abstain logic + context assembly + LLM response generation
  - Agent mode: optional explicit planner (`agent_planner.py`), clarification short-circuit, streaming prep via `iter_run_evidence_agent_outer` (replan), NDJSON progress + finish payload
  - Responses include `query_type` (internal key) and `query_type_label` (human-readable route for UI/debug)

Script entrypoints:

- `python backend/scripts/run_download_hgnc.py`
- `python backend/scripts/run_extract_pdfs.py`
- `python backend/scripts/run_clear_graph.py --yes` — **wipe all nodes/relationships** (uses current `NEO4J_*`; then re-run schema + ingest + embeddings below)
- `python backend/scripts/run_setup_schema.py`
- `python backend/scripts/run_ingest_papers.py`
- `python backend/scripts/run_create_embeddings.py`
- `python backend/scripts/run_llm_graph_extract.py` (Phase 5; optional; requires `OPENAI_API_KEY`)

## Runbook (local, in order)

Run from this directory (`Devreotes Lab Research Chatbot/`) with your virtualenv activated and dependencies installed (`requirements.txt`).

**If you see `ModuleNotFoundError: No module named 'dotenv'` (or `spacy`, `sentence_transformers`):** your shell’s `python` is not this project’s venv. Check with `which python` — it should be `.../DevreotesLabResearchChatbot/.venv/bin/python`. Fix: `source .venv/bin/activate` from this folder, or call scripts explicitly as `.venv/bin/python backend/scripts/run_clear_graph.py --yes`. If the venv is correct but packages are missing: `.venv/bin/python -m pip install -r requirements.txt`.

1. **Environment:** Copy `.env.example` to `.env` and set `NEO4J_*` and `OPENAI_API_KEY`. For **Neo4j Aura**, put `neo4j+s://…` and credentials in `.env.production` (gitignored), then set `DEVREOTES_USE_PRODUCTION_ENV=1` in your shell or Nuxt env so Python loads `.env` first and overlays production. Alternatively set `DEVREOTES_DOTENV=.env.production` to use only that file. See table below.
2. **HGNC (first time / refresh):** `python backend/scripts/run_download_hgnc.py`
3. **Extract PDFs:** `python backend/scripts/run_extract_pdfs.py` (reads `papers/`, writes `extracted/`)
4. **(Optional) Wipe graph:** `python backend/scripts/run_clear_graph.py --yes` — deletes **everything** in the DB; use before a clean re-ingest (e.g. after switching to Aura or fixing schema).
5. **Neo4j schema:** `python backend/scripts/run_setup_schema.py` (safe to re-run)
6. **Ingest:** `python backend/scripts/run_ingest_papers.py`
7. **Embeddings:** `python backend/scripts/run_create_embeddings.py`
8. **LLM graph enrichment (Phase 5, optional):** `python backend/scripts/run_llm_graph_extract.py` (after embeddings; uses `OPENAI_API_KEY`; set `GRAPH_EXTRACT_LIMIT` as needed)
9. **UI:** `python app.py` (Gradio) or `cd nuxt && pnpm dev` (Nuxt; set `DEVREOTES_PYTHON` if not using system `python3`). **Optional HTTP API (Nuxt):** from the Devreotes project root, `uvicorn backend.app.api_app:app --host 127.0.0.1 --port 8765` in a second terminal, then set `DEVREOTES_API_URL=http://127.0.0.1:8765` in the Nuxt environment (and matching `DEVREOTES_API_SECRET` if you configure one).

Re-run from **step 3 (extract) through step 7 (embeddings)** after changing extraction or ingest logic so the graph stays consistent. For a **full empty DB**, run step 4 (`run_clear_graph.py --yes`) then **5 → 7**. After changing LLM extraction code, re-run step 8 or clear `Chunk.llm_extracted_at` in Neo4j to force re-extract.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `NEO4J_URI` | Bolt URI — local `bolt://127.0.0.1:7687`; **Aura** `neo4j+s://….databases.neo4j.io` |
| `NEO4J_USER` | Neo4j username |
| `NEO4J_PASSWORD` | Neo4j password |
| `DEVREOTES_USE_PRODUCTION_ENV` | Optional. If `1`/`true`/`yes`/`on`, load `.env.production` after `.env` (overrides keys — e.g. Aura `NEO4J_*`) |
| `DEVREOTES_DOTENV` | Optional. If set, load **only** that env file (path relative to Devreotes project root if not absolute), e.g. `.env.production` |
| `OPENAI_API_KEY` | OpenAI API key for `ChatOpenAI` in `backend/app/chatbot.py` |
| `RAG_TOP_K` | Optional. Chunks to retrieve (default `8`) |
| `RAG_MIN_SCORE` | Optional. Minimum vector score before abstaining (default `0.35`) |
| `MAX_CONTEXT_CHARS_PER_CHUNK` | Optional. Truncate per chunk in the LLM context |
| `MAX_CONTEXT_CHUNKS` | Optional. Max chunks passed to the model |
| `DEVREOTES_PYTHON` | Optional (Nuxt only). Path to Python for `server/python/devreotes_bridge.py` |
| `DEVREOTES_RAG_MODE` | Optional. `router` (default) or `agent` — multi-tool retrieval then one grounded answer |
| `DEVREOTES_AGENT_MAX_STEPS` | Optional. Max tool-calling **inner** steps per retrieval batch in `agent` mode (default `6`) |
| `DEVREOTES_AGENT_EXPLICIT_PLAN` | Optional. `true`/`1` — LLM structured plan before tools; enables streamed plan + clarification path |
| `DEVREOTES_AGENT_ALLOW_CLARIFY` | Optional. Default `true`. If `false`, planner may still set `needs_user_input` but tools run anyway |
| `DEVREOTES_AGENT_UI_PROGRESS` | Optional. Default `true`. Stream `agent_status` / `agent_plan` / `agent_step` NDJSON for the Nuxt progress strip |
| `DEVREOTES_AGENT_REPLAN_ROUNDS` | Optional. `0`–`4` (default `0`). Extra retrieval batches after structured replan (`agent_replan.py`) |
| `DEVREOTES_AGENT_REASONING_LOG` | Optional. Default off. Include `reasoning_log` in finish/trace when model emits text with tools |
| `DEVREOTES_AGENT_THINK_STEP` | Optional. Default off. Extra think-only LLM call before each inner tool step |
| `DEVREOTES_STREAM` | Set by Nuxt for bridge streaming (`1`) — not usually set manually |
| `DEVREOTES_API_URL` | Optional (Nuxt). If set (e.g. `http://127.0.0.1:8765`), Nitro calls FastAPI `POST /chat/stream` instead of spawning `devreotes_bridge.py` (warm process, lower overhead) |
| `DEVREOTES_API_SECRET` | Optional. If set in FastAPI and Nuxt, requests must send header `X-Devreotes-Key` with this value |
| `RAG_VECTOR_FETCH_MULTIPLIER` | Optional. Fetch `top_k * multiplier` vector hits before per-paper dedupe (default `4`) |
| `RAG_VECTOR_FETCH_CAP` | Optional. Upper bound on vector fetch (default `120`) |
| `RAG_MAX_CHUNKS_PER_PAPER` | Optional. Max chunks per `paper_id` after dedupe (default `2`) |
| `RAG_RERANK` | Optional. Set `true` to rerank candidates with the same embedding model (`false` default) |
| `RAG_RERANK_POOL` | Optional. When reranking, dedupe up to this many chunks before cutting to `RAG_TOP_K` (default `32`, max `96`) |
| `THEMES_MIN_PAPER_COUNT` | Optional. For the `themes` route (gene mention counts), drop genes below this paper count (default `1`) |
| `THEMES_GENE_LIMIT` | Optional. Max genes returned in the aggregate (default `20`) |
| `AUTHOR_STATS_MIN_PAPERS` | Optional. `author_stats` route: minimum distinct papers per author (default `2`) |
| `AUTHOR_STATS_LIMIT` | Optional. Max authors returned in `author_stats` (default `40`) |
| `INGEST_SUPPLEMENT_TOKEN_GENES` | Optional. `true`/`false` — add a second gene pass: ALLCAPS tokens matched only against HGNC (default `true`) |
| `OPENAI_EXTRACT_MODEL` | Optional. Model for Phase 5 chunk extraction (default `gpt-4o-mini`) |
| `GRAPH_EXTRACT_LIMIT` | Optional. Max chunks per `run_llm_graph_extract` batch (default `25`) |
| `RAG_GRAPH_EXPAND` | Optional. `true` adds same-paper chunks sharing LLM `Entity` nodes with vector hits (default `false`) |
| `RAG_GRAPH_EXPAND_EXTRA` | Optional. Max extra chunks to consider from graph expansion (default `8`) |
| `RAG_GRAPH_EXPAND_SCORE_RATIO` / `RAG_GRAPH_EXPAND_SCORE_FLOOR` | Optional. Score for expanded chunks relative to seed hit |

## Secrets

- **Do not commit** `.env` or `.env.production` (and other `.env.*` except `.env.example`). They are gitignored.
- If an API key or password was ever committed or shared, **rotate** it in the provider and update local env files.
- Commit **`.env.example`** only (placeholders, no real secrets).
