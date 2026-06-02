# Devreotes Lab Research Chatbot

GraphRAG-style Q&A over a PDF corpus: papers and chunks live in **Neo4j** (with vector search on chunk embeddings); **OpenAI** generates answers with citations.

---

## Prerequisites

- **Python** 3.12+
- **Neo4j** locally (`bolt://127.0.0.1:7687`) or **Neo4j Aura** (`neo4j+s://…`)
- **OpenAI API key** for the chatbot (and optional Phase 5 extraction)
- **Node.js + pnpm** if you use the Nuxt UI (`nuxt/`)

---

## 1. Clone / open this folder

All commands below assume your shell’s working directory is this project root:

`chatBot/resources/DevreotesLabResearchChatbot/`

---

## 2. Virtual environment and Python deps

```bash
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
which python                # should end with .../DevreotesLabResearchChatbot/.venv/bin/python

python -m pip install -r requirements.txt
```

**Biomedical spaCy model** (required for ingest):

```bash
python -m pip install "https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz"
```

If `import dotenv` / `spacy` / `sentence_transformers` fails, you are not using this `.venv` — use `.venv/bin/python …` explicitly or fix `which python`.

---

## 3. Environment variables

```bash
cp .env.example .env
```

Edit `.env` and set at least:

| Variable | Purpose |
|----------|---------|
| `NEO4J_URI` | Local: `bolt://127.0.0.1:7687` · Aura: `neo4j+s://xxxx.databases.neo4j.io` |
| `NEO4J_USER` | Usually `neo4j` |
| `NEO4J_PASSWORD` | Your DB password |
| `OPENAI_API_KEY` | For answers (and Phase 5 if you run it) |

**Aura / production file:** put `NEO4J_*` in `.env.production` and set `DEVREOTES_USE_PRODUCTION_ENV=1` (or `DEVREOTES_DOTENV=.env.production`) so the backend loads it. See `.env.example` comments.

---

## 4. Data layout

- Put PDFs under **`papers/`** (or whatever path your extract script expects — default is `papers/`).
- First run downloads HGNC into **`hgnc_lookup.json`**.
- Extraction writes JSON under **`extracted/`**.

---

## 5. Pipeline (run in order)

From the project root, with the venv activated:

| Step | Command |
|------|---------|
| 1 | `python backend/scripts/run_download_hgnc.py` |
| 2 | `python backend/scripts/run_extract_pdfs.py` |
| 3 | *(optional clean slate)* `python backend/scripts/run_clear_graph.py --yes` |
| 4 | `python backend/scripts/run_setup_schema.py` |
| 5 | `python backend/scripts/run_ingest_papers.py` |
| 6 | `python backend/scripts/run_create_embeddings.py` |
| 7 | *(optional)* `python backend/scripts/run_llm_graph_extract.py` — Phase 5 LLM graph enrichment |

**Test Neo4j connectivity:**

```bash
python backend/scripts/test_connection.py
```

---

## 6. Run the app

**Gradio (quick demo)**

```bash
python app.py
```

**Nuxt (streaming chat UI)**

```bash
cd nuxt
pnpm install
pnpm dev
```

Point **`DEVREOTES_PYTHON`** in the Nuxt env at this project’s venv Python if the bridge cannot find packages, e.g.  
`/…/DevreotesLabResearchChatbot/.venv/bin/python`.

**Optional FastAPI** (warm server instead of spawning Python per request): from this root,

```bash
./.venv/Scripts/python.exe -m uvicorn backend.app.api_app:app --host 127.0.0.1 --port 8765
```

Then set `DEVREOTES_API_URL=http://127.0.0.1:8765` in the Nuxt environment.

### Conversational thread memory

The Nuxt Devreotes route supports **within-thread conversational context** on both the **FastAPI** path (`DEVREOTES_API_URL`) and the **bridge** path (JSON stdin to `devreotes_bridge.py`):

- Sends `messages` (recent turns, default last **10**) and `summary` with each request.
- Persists a per-chat `chats.summary` value in the app DB.
- Uses an LLM summary updater after each assistant response (with deterministic fallback).

Useful env knobs:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEVREOTES_CONVERSATION_RECENT_TURNS` | `10` | Number of recent turns sent as context (`messages`) |
| `DEVREOTES_SUMMARY_MAX_CHARS` | `1500` | Max persisted summary length |
| `DEVREOTES_SUMMARY_MODEL` | `openai/gpt-4o-mini` | Model used to update thread summary |

**Bridge mode and thread context:** When Nuxt runs `devreotes_bridge.py` (no `DEVREOTES_API_URL`), stdin is a **JSON object** with `message`, `summary`, and `messages` (same shape as the FastAPI body), so multi-turn context works on the local Python path too. A legacy **plain-text** line is still accepted as the whole question.

### Agent mode (optional)

With **`DEVREOTES_RAG_MODE=agent`**, retrieval uses multiple tools in a loop before the final answer. Optional features (all in `.env.example`):

| Variable | Purpose |
|----------|---------|
| `DEVREOTES_AGENT_EXPLICIT_PLAN` | Structured planner step + streamed plan checklist in the UI |
| `DEVREOTES_AGENT_ALLOW_CLARIFY` | If the planner asks for user input, return a clarification message instead of running tools (default on) |
| `DEVREOTES_AGENT_UI_PROGRESS` | Stream status / plan / tool labels during retrieval (default on) |
| `DEVREOTES_AGENT_REPLAN_ROUNDS` | Extra retrieval batches after a supervisor replan decision (`0`–`4`, default `0`) |
| `DEVREOTES_AGENT_REASONING_LOG` | Persist model reasoning snippets in API/trace (privacy-sensitive; default off) |
| `DEVREOTES_AGENT_THINK_STEP` | Extra “think” LLM call before each tool round (default off) |

See **[ARCHITECTURE_AND_USAGE.md §11](./ARCHITECTURE_AND_USAGE.md#11-key-additions-since-the-basic-router--gradio-layout)** for behavior, protocols, and file locations.

---

## More detail

- **Architecture and plain-English usage:** [ARCHITECTURE_AND_USAGE.md](./ARCHITECTURE_AND_USAGE.md)
- **Module map, full env table, troubleshooting:** [structure.md](./structure.md)
- **Original step-by-step GraphRAG build notes:** [GraphRAG_Implementation_Guide.md](./GraphRAG_Implementation_Guide.md)

