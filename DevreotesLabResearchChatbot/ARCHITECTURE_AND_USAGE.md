# Devreotes Lab Research Chatbot — Architecture & Usage (Plain-English Guide)

This document explains **what the system does**, **how the pieces connect**, **what lives in the graph database**, **which technologies are used and why**, and **how to run the project**. It is written so non-specialists can follow along; technical terms are introduced with everyday analogies.

---

## 1. What problem does this solve?

Imagine a **stack of PDF research papers** from Prof. Peter Devreotes’ lab. A user asks a question in natural language, for example: *“Which papers talk about PTEN?”* or *“What are the most-mentioned genes across the corpus?”*

The system must:

1. **Stay grounded** — answers should come from *those papers*, not from the model’s general internet-like knowledge.
2. **Point to evidence** — answers cite numbered passages (chunks) so readers can verify.
3. **Use the right “lens”** — sometimes the best answer is *semantic search*, sometimes *filter by gene or author*, sometimes a *simple statistic* over the graph.

This project implements **GraphRAG**: a **graph** (Neo4j) stores papers, chunks, genes, authors, and optional entities; **retrieval** finds relevant text; a **large language model (LLM)** writes the final answer using only what was retrieved.

---

## 2. Big picture: flow from PDF to answer

Think of the pipeline like a **library with a smart index**:

| Stage | Plain analogy |
|--------|----------------|
| **PDFs on disk** | Books on a shelf (`papers/`) |
| **Text extraction** | Typing each book into plain text (`extracted/*.json`) |
| **Neo4j graph** | Card catalog + cross-references: which paper, which chunk, which gene |
| **Embeddings** | “Semantic sticky notes” on each chunk so *similar meaning* can be found by vector search |
| **Question → route** | Librarian decides: *gene shelf*, *author shelf*, *statistics*, or *general similarity* |
| **LLM** | A careful writer who may only quote from the pages you slid across the desk |

```mermaid
flowchart LR
  subgraph ingest["Offline: build the library"]
    PDF[papers/*.pdf]
    EXT[extract_pdfs.py]
    JSON[extracted/*.json]
    ING[ingest_papers.py]
    NEO[(Neo4j graph)]
    EMB[create_embeddings.py]
    PDF --> EXT --> JSON --> ING --> NEO
    NEO --> EMB
  end
  subgraph online["Online: answer a question"]
    Q[User question]
    R[router.py]
    RET[retrieval.py]
    CB[chatbot.py + OpenAI]
    Q --> R --> RET --> CB --> A[Answer + citations]
  end
  NEO --> RET
```

The diagram above contrasts **offline ingest** with a simplified **online** path. The diagram below is the **full system view**: clients, Nuxt server, optional HTTP API, Python core, Neo4j, and OpenAI.

### Architecture diagram (runtime & services)

```mermaid
flowchart TB
  subgraph offline["Offline: build corpus"]
    PDF["papers/ → extract_pdfs → extracted/"]
    PIPE["setup_schema → ingest_papers → create_embeddings"]
    PDF --> PIPE
  end

  NEO[("Neo4j\n(graph + vector index)")]
  PIPE --> NEO

  subgraph clients["Clients"]
    BR["Browser\n(Nuxt UI)"]
    GR["Gradio\napp.py"]
  end

  subgraph nuxt["Nuxt server (Nitro)"]
    API["POST /api/devreotes/chats/:id\n(SSE / AI SDK stream)"]
    APPDB[("App DB\nmessages, devreotes_trace")]
    BRG["devreotes_bridge.py\n(NDJSON stdout)"]
  end

  subgraph fastapi["Optional: DEVREOTES_API_URL"]
    FAPI["FastAPI\nPOST /chat/stream"]
  end

  subgraph core["Python backend (backend/app)"]
    CHAT["chatbot.py\nrouter / agent + planner"]
    ROUT["router.py"]
    AGT["agent_tools +\nagent_planner +\nagent_replan"]
    RETR["retrieval.py\nvector + Cypher"]
  end

  LLM["OpenAI API\n(Chat completions)"]

  BR --> API
  API --> APPDB
  API --> BRG
  API -.->|optional| FAPI
  FAPI --> CHAT
  BRG --> CHAT
  GR --> CHAT
  CHAT --> ROUT
  CHAT --> AGT
  ROUT --> RETR
  AGT --> RETR
  RETR --> NEO
  CHAT --> LLM
```

**How to read it:** **Offline** jobs populate **Neo4j** once (or after corpus changes). At **question time**, either **Gradio** calls `chatbot.py` in-process, or the **Nuxt** route streams an answer via the **bridge** subprocess or, if configured, the **FastAPI** service. **Router** vs **agent** mode is decided inside `chatbot.py` (`DEVREOTES_RAG_MODE`). In **agent** mode, optional **explicit planning** (`agent_planner.py`), **replan** between batches (`agent_replan.py`), and **tool loops** live in `agent_tools.py` / `chatbot.py`. **Retrieval** always reads the graph/vector index; the **LLM** only sees retrieved text plus the user question.

**Conversational context (thread scope):** Requests may include `summary` and recent `messages` (default last 10 turns)—on **FastAPI** in the JSON body and on the **bridge** path as a **JSON line** on stdin (same keys). Python uses this context to resolve follow-ups while keeping evidence grounded in retrieved corpus passages. A legacy **single-line plain-text** question still works for the bridge.

---

## 3. Step-by-step: what runs when (offline vs online)

### A. Offline — “building the library” (run once, then again when you change rules or papers)

1. **HGNC gene dictionary** (`run_download_hgnc.py`)  
   - **Layman:** A standard **phone book for human gene symbols** (official symbols and aliases).  
   - **Why:** So when text says “PTEN” or an alias, we link to **one** canonical gene node instead of guessing.

2. **Extract PDFs** (`run_extract_pdfs.py`)  
   - Reads each PDF, pulls text and best-effort metadata (title, DOI, year, journal hints, PDF author/subject when present).  
   - **Layman:** OCR-free **photocopying the words** into JSON files under `extracted/`.

3. **Neo4j schema** (`run_setup_schema.py`)  
   - Creates **unique IDs** and **indexes** (including a **vector index** on chunk embeddings).  
   - **Layman:** Library **rules** (“every chunk has one ID”) and a **fast index** for search.

4. **Ingest** (`run_ingest_papers.py`)  
   - Creates **Paper**, **Chunk**, links genes and authors, optional **Claim** snippets, and **Entity** nodes for genes/authors as used in the original design.  
   - **Layman:** **Filing cards**: this paper has these paragraphs; these paragraphs mention these genes.

5. **Embeddings** (`run_create_embeddings.py`)  
   - Computes a **vector** (list of numbers) per chunk using a biomedical sentence model.  
   - **Layman:** Each paragraph gets a **fingerprint of meaning**, so “chemotaxis” and “cell movement” can match even if words differ.

6. **Optional: LLM graph enrichment** (`run_llm_graph_extract.py`)  
   - Calls a small/cheap model to label **topics, pathways, methods**, etc., and optional relationships.  
   - **Layman:** A **second pass of highlighting** with structured labels—not required for basic Q&A.

### B. Online — “asking the library a question”

1. User submits a question (Gradio `app.py` or Nuxt UI → Python **bridge** → `chatbot.py`).
2. **Router** (`router.py`) classifies: *themes / author_stats / corpus_meta (exact graph counts) / author / gene / semantic*.
3. **Retrieval** (`retrieval.py`) runs vector search and/or Cypher filters (e.g., only chunks from papers that *mention* gene X).
4. **Chatbot** (`chatbot.py`) builds a prompt: system rules + numbered passages + user question; the **LLM** streams or returns an answer with `[1]`, `[2]`-style citations.

---

## 4. Graph: main nodes and relationships

Neo4j stores **nodes** (things) and **relationships** (edges). Below is the **mental model** this project uses.

### Nodes (the “nouns”)

| Label | Plain meaning | Typical properties |
|--------|----------------|----------------------|
| **Paper** | One publication in the corpus | `paper_id`, `title`, `filename`, optional `doi`, `year`, `journal`, PDF metadata hints |
| **Chunk** | A slice of text from a paper (searchable unit) | `chunk_id`, `text`, `chunk_index`, **embedding** (vector) |
| **Gene** | A human gene from HGNC | `hgnc_id`, `official_symbol` |
| **Author** | A person (as extracted) | `author_key`, `name` |
| **Entity** | Tagged concept used for graph traversal and UI | `entity_key`, `type`, `name`. Ingest sets `type` to **`GENE`** or **`AUTHOR`**; Phase 5 adds types like **Topic**, **Method**, **Pathway**, … |
| **Claim** | A short extracted sentence-like unit (for grounding) | `claim_id`, `text` |

### Relationships (the “verbs”)

| Pattern | Plain meaning |
|---------|----------------|
| `(:Paper)-[:HAS_CHUNK]->(:Chunk)` | This paper **contains** this paragraph. |
| `(:Author)-[:AUTHORED]->(:Paper)` | This person **wrote** this paper. |
| `(:Paper)-[:MENTIONS]->(:Gene)` | This paper **mentions** this gene (corpus-level link to the canonical **Gene** node). |
| `(:Chunk)-[:MENTIONS]->(:Entity)` | Chunk-level mention. Ingest: **`GENE`** entities when the symbol appears in chunk text; Phase 5: LLM-extracted entities. |
| `(:Paper)-[:HAS_TOPIC]->(:Entity)` | Paper-level link to an **Entity**. Ingest: one per paper gene (`type: GENE`) and per author (`type: AUTHOR`); Phase 5: **Topic** entities from the LLM pass. |
| `(:Entity)-[:RELATED_TO]->(:Gene)` | **Ingest only:** connects a paper-level **`GENE` Entity** to its canonical **`Gene`** (same symbol / HGNC identity). |
| `(:Entity)-[:RELATED_TO]->(:Entity)` | **Phase 5 only (optional):** semantic link between two LLM-extracted entities; fine-grained kind is stored on the relationship as **`kind`** (e.g. `ASSOCIATED_WITH`, `PART_OF`). |
| `(:Claim)-[:SUPPORTS]->(:Chunk)` | A **Claim** is **evidence** for this chunk (ingest). |
| `(:Claim)-[:ABOUT]->(:Entity)` | **Ingest only:** when a claim is written for a chunk that mentions a gene, link the claim to the **`GENE` Entity** for that symbol. |

**Note on `RELATED_TO`:** Neo4j uses one relationship **type** for two different roles: **ingest** bridges `Entity {type: 'GENE'}` → **`Gene`**; **Phase 5** connects **Entity** → **Entity** with properties `kind`, `source_chunk_id`, `confidence`.

### Architecture diagram (Neo4j nodes & relationships)

**Paper** and **Chunk** anchor text; **`Gene`** is the HGNC-backed node for corpus-level gene queries. **`Entity`** is a parallel layer: ingest creates **GENE** / **AUTHOR** entities (and **Chunk**/**Claim** links to **GENE** entities); optional Phase 5 adds other entity types and **Entity↔Entity** `RELATED_TO`. **Chunk** nodes hold an **embedding** property for the **vector index** (not a separate node).

```mermaid
flowchart TB
  subgraph authors["Authors"]
    A[(:Author)]
  end

  subgraph papers["Publication & text"]
    P[(:Paper)]
    C[(:Chunk)]
    CL[(:Claim)]
  end

  subgraph biology["Reference & extracted concepts"]
    G[(:Gene)]
    E[(:Entity)]
  end

  A -->|AUTHORED| P
  P -->|HAS_CHUNK| C
  P -->|MENTIONS| G
  P -->|HAS_TOPIC| E
  C -->|MENTIONS| E
  CL -->|SUPPORTS| C
  CL -->|ABOUT ingest| E
  E -->|RELATED_TO ingest GENE only| G
  E2[(:Entity)] -.->|RELATED_TO Phase 5| E3[(:Entity)]
```

**Reading the diagram:** **AUTHORED** / **HAS_CHUNK** structure the corpus. **Paper→Gene** (`MENTIONS`) is the main canonical gene link. **Entity** nodes tie together **HAS_TOPIC** (paper-level genes and authors, plus Phase 5 topics), **Chunk→Entity** (`MENTIONS`, genes in text and LLM entities), **Claim→Entity** (`ABOUT`, gene-tagged claims), and **Entity→Gene** (`RELATED_TO`, only for **`GENE`** entities created at ingest). **SUPPORTS** links each **Claim** to its **Chunk**. Dashed **Entity↔Entity** `RELATED_TO` exists only after **`run_llm_graph_extract.py`** (Phase 5).

**Layman analogy:**  
- **Paper** = book. **Chunk** = page or paragraph. **Gene/Author** = index entries. **Embedding** = invisible tag that helps “find similar paragraphs.”

---

## 5. Tech stack — what each part is and why it was chosen

| Piece | Role | Why it fits this project |
|--------|------|---------------------------|
| **Neo4j** | Graph database | Papers, chunks, and “mentions” are naturally **networks**. Cypher can **filter by gene/author** and combine with vector search. |
| **PyMuPDF (`fitz`)** | PDF text extraction | Fast, local, no cloud OCR required for text-based PDFs. |
| **scispaCy + `en_core_sci_lg`** | Biomedical NLP | Good at spotting **gene-like spans** in running text during ingest. |
| **HGNC JSON** | Gene normalization | **Community standard** for human gene symbols and aliases—reduces duplicate or wrong gene nodes. |
| **SentenceTransformers + PubMed-tuned model** | Chunk embeddings | **Same embedding space** for question and chunks → meaningful cosine / vector index similarity in biomedicine. |
| **Neo4j vector index** | Approximate nearest-neighbor search | Lets you ask “what passages are *semantically* closest to my question?” at scale. |
| **LangChain + OpenAI (`gpt-4o`)** | Answer generation | Strong instruction-following for **citations** and **refusal** when context is weak. |
| **Gradio (`app.py`)** | Quick local UI | Minimal setup for demos and debugging without a JS build. |
| **Nuxt + AI SDK + Nuxt UI** | Production-style chat UI | **Streaming** answers, modern UX, CSRF-aware API routes. |
| **Python bridge (`devreotes_bridge.py`)** | Subprocess from Node | Reuses the **same** `chatbot.py` logic for the Nuxt app without rewriting retrieval in TypeScript. |

Nothing here is “magic”: each tool solves one layer—**storage**, **text**, **biology naming**, **meaning vectors**, **routing**, **generation**, **UI**.

---

## 6. The “organs” of the system (how they work together)

### Router (`router.py`)

- **Job:** Guess *what kind of question* this is.  
- **Layman:** The **receptionist** who sends you to “gene desk,” “author desk,” “statistics desk,” or “general reading room.”  
- **Why it matters:** Asking “which kinases are *most mentioned*?” should not be treated the same as “what does *PTEN* do in chemotaxis?”—different desks, different tools.  
- **Author stats:** Questions like “which authors appear on multiple papers?” go to **`author_stats`** (counts from `(:Author)-[:AUTHORED]->(:Paper)`), not single-author chunk search.

### Retrieval (`retrieval.py`)

- **Job:** Return ranked **chunks** (and sometimes aggregate **gene** or **author** counts).  
- **Layman:** The **librarian** who pulls books off the shelf *and* photocopies the right pages.  
- **Extras:** Per-paper diversity (not ten chunks from one paper), optional rerank, optional **graph expansion** (`RAG_GRAPH_EXPAND`: same-paper chunks that share **LLM-extracted** `Entity` nodes with vector hits—skips `GENE` / `AUTHOR` types).

### Chatbot (`chatbot.py`)

- **Job:** If confidence is too low, **say so**; otherwise assemble context and call the LLM.  
- **Layman:** The **editor**: you only get an article built from supplied quotes, with citation numbers.

### Optional Phase 5 (`llm_chunk_extract.py`)

- **Job:** Per chunk, call the LLM for JSON **entities** (non-gene types: Topic, Method, Pathway, …) and **relations**; write **`Chunk→Entity`** (`MENTIONS`), **`Paper→Entity`** (`HAS_TOPIC` for **Topic** only), and **`Entity→Entity`** (`RELATED_TO` with **`kind`**).  
- **Layman:** Optional **second round of indexing** for topics and semantic links between entities—not required for baseline Q&A. **Ingest** already creates **`GENE`** / **`AUTHOR`** entities and **`Entity→Gene`** (`RELATED_TO`); Phase 5 does **not** replace that.

---

## 7. Two ways to use the UI

| Interface | Command | Audience |
|-----------|-----------|----------|
| **Gradio** | `python app.py` | Fast local demo, single-user. |
| **Nuxt** | `cd nuxt && pnpm dev` | Richer chat UI, **streaming** responses; set `DEVREOTES_PYTHON` to your venv’s `python` if needed. |

Both ultimately call the same Python **brain** (`backend/app/chatbot.py`) for answers.

---

## 8. Usage checklist (short)

1. Copy `.env.example` → `.env` and set **Neo4j** and **OpenAI** keys. For **Neo4j Aura**, use `neo4j+s://…` in `.env` or keep Aura `NEO4J_*` in **`.env.production`** and set **`DEVREOTES_USE_PRODUCTION_ENV=1`** (or **`DEVREOTES_DOTENV=.env.production`**) so the backend loads them — same for Nuxt if the Python bridge should hit Aura.  
2. Run scripts in order: **HGNC → extract → schema → ingest → embeddings** → *(optional)* **LLM extract**.  
3. Start **Gradio** or **Nuxt** as above.

Full command list and environment table: see **`structure.md`** in this folder.

---

## 9. End-to-end example (layman walkthrough)

**Question:** *“What does the corpus say about PTEN?”*

1. **Router** notices “PTEN” and gene-related language → **gene route** (if PTEN resolves in HGNC).  
2. **Retrieval** finds chunks from papers whose graph says they **mention PTEN**, ranked by **vector similarity** to the question.  
3. **Chatbot** builds a prompt: numbered excerpts only.  
4. **LLM** answers and cites `[1]`, `[2]` matching those excerpts.  
5. If nothing clears the minimum similarity score, the system **abstains** instead of inventing facts—by design.

**Question:** *“Which genes appear in the most papers?”*

1. **Router** sends this toward the **themes** path (gene-mention **counts** over the graph).  
2. **Retrieval** returns a **table-like summary** (genes × paper counts), not long prose from one paper.  
3. The LLM is instructed **not** to invent qualitative “themes” beyond those counts.

---

## 10. Design principles (why things are the way they are)

1. **Corpus-grounded:** The LLM is a **writer**, not the **source of truth**—the graph and chunks are.  
2. **Explainable:** Chunks and scores can be inspected; citations tie answers to **specific text**.  
3. **Biomedical realism:** HGNC + scispaCy + PubMed-flavored embeddings match how **genes and papers** are discussed.  
4. **Pragmatic graph:** Not every possible ontology is modeled—only what helps **search**, **filters**, and **stats** for this capstone scope.

---

## 11. Key additions since the basic router + Gradio layout

This section summarizes **agentic RAG**, the **Nuxt API**, **retrieval / decision trace**, **streaming**, and **UI** pieces that extend the original “router → retrieval → chatbot” picture. Full **environment variable** tables and runbook details: **`structure.md`**.

### 11.1 Two RAG modes: router (default) vs agent

- **`DEVREOTES_RAG_MODE=router` (default)** — Same mental model as §6: `router.py` picks a **single** route (`themes` / `gene` / `author` / `semantic`), `retrieval.py` runs that path once, then `chatbot.py` builds one context block and calls the LLM.
- **`DEVREOTES_RAG_MODE=agent`** — The model can call **multiple retrieval tools** over several steps (`semantic_search`, `gene_literature_search`, author/themes tools in `backend/app/agent_tools.py`). The main loop is `iter_run_evidence_agent`; **`chatbot.py`** may wrap it in **`iter_run_evidence_agent_outer`** when **`DEVREOTES_AGENT_REPLAN_ROUNDS` > 0`**, merging evidence between batches using **`agent_replan.py`**. Evidence is merged and deduplicated; the final answer stays **corpus-grounded** with citations. Inner step cap: **`DEVREOTES_AGENT_MAX_STEPS`** (see `structure.md`).

**Optional agent layers (all toggled via env; see `.env.example` and `structure.md`):**

| Feature | Behavior |
|---------|----------|
| **Explicit plan** (`DEVREOTES_AGENT_EXPLICIT_PLAN`) | Before tools, a structured **planner** (`agent_planner.py`) emits goals/steps. The UI can show a **checklist** when progress streaming is on. |
| **Clarification** (`DEVREOTES_AGENT_ALLOW_CLARIFY`) | If the planner marks **needs user input**, the backend returns a short clarification message **instead of** running tools (so vague prompts don’t burn retrieval). |
| **UI progress** (`DEVREOTES_AGENT_UI_PROGRESS`) | NDJSON lines **`agent_status`**, **`agent_plan`**, **`agent_step`** during retrieval; Nuxt maps them to **`data-devreotes-progress`** SSE and **`DevreotesProgressStrip`**. |
| **Replan rounds** (`DEVREOTES_AGENT_REPLAN_ROUNDS`) | After an inner batch completes, a small **replan** model (`agent_replan.py`) may request another retrieval batch with compacted observations. |
| **Reasoning log** (`DEVREOTES_AGENT_REASONING_LOG`) | Optional persistence of model **reasoning** snippets in the finish payload / trace (off by default; privacy-sensitive). |
| **Think step** (`DEVREOTES_AGENT_THINK_STEP`) | Optional extra **think-only** LLM call before each inner tool round (latency cost). |

**Layman:** Router mode is *one trip to the library*. Agent mode is *the librarian may plan, ask you to narrow the question, and revisit different shelves (maybe in multiple waves)* before writing the answer.

### 11.2 Nuxt ↔ Python: bridge vs HTTP API

The Nuxt app does **not** reimplement retrieval in TypeScript. It gets answers by either:

1. **Subprocess bridge** — `nuxt/server/python/devreotes_bridge.py` runs the same `chatbot.py` streaming entrypoint (`iter_answer_ndjson`), printing **NDJSON** lines to stdout. **Stdin** is either a **JSON object** `{ "message", "summary?", "messages?" }` (same contract as FastAPI) or a legacy **single line** of plain question text. Configure the interpreter with **`DEVREOTES_PYTHON`** if needed.
2. **HTTP API (optional)** — Run **`uvicorn backend.app.api_app:app`** (see `structure.md`), set **`DEVREOTES_API_URL`** in Nuxt’s env so Nitro calls **`POST /chat/stream`** instead of spawning Python each time. Shared secret optional: **`DEVREOTES_API_SECRET`** / header **`X-Devreotes-Key`**.

The UI records which path was used in the trace as **`backend`: `bridge` | `http`**.

### 11.2.1 Conversational properties (Nuxt app thread memory)

Nuxt sends these properties on **both** the HTTP and bridge paths (HTTP: JSON body; bridge: JSON on stdin):

- `summary`: rolling per-thread summary from `chats.summary`
- `messages`: recent turns (`[{ role, content }]`, default last 10)

Nuxt updates the stored summary after each assistant response using an LLM summarizer
(`DEVREOTES_SUMMARY_MODEL`, default `openai/gpt-4o-mini`) with deterministic fallback.

Key knobs:

| Variable | Default | Meaning |
|----------|---------|---------|
| `DEVREOTES_CONVERSATION_RECENT_TURNS` | `10` | Number of recent turns sent in `messages` |
| `DEVREOTES_SUMMARY_MAX_CHARS` | `1500` | Summary truncation cap |
| `DEVREOTES_SUMMARY_MODEL` | `openai/gpt-4o-mini` | Summary updater model |

### 11.2.2 Dynamic follow-up suggestions (streamed over SSE)

After the main answer, **`POST /api/devreotes/chats/[id]`** may emit extra AI SDK chunks of type **`data-devreotes-followups`**: the model streams a JSON array (string fragments), then a final chunk with parsed **`suggested_followups`**. The chat UI shows these as chips; the same strings are persisted on **`devreotes_trace.suggested_followups`**.

| Variable | Default | Meaning |
|----------|---------|---------|
| `DEVREOTES_FOLLOWUPS_ENABLED` | `1` | Set `0` / `false` to disable |
| `DEVREOTES_FOLLOWUPS_MODEL` | `DEVREOTES_SUMMARY_MODEL` or `openai/gpt-4o-mini` | Follow-up generator |
| `DEVREOTES_FOLLOWUPS_COUNT` | `4` | Number of suggestions (max `8`) |
| `DEVREOTES_FOLLOWUPS_MAX_PREVIEW_CHARS` | `4000` | Retrieval preview size in the follow-up prompt |

### 11.3 Streaming protocol (NDJSON + AI SDK UI stream)

- The Python side yields lines like **`{"type":"delta","text":"..."}`** and a final **`{"type":"finish","result":{...}}`** (see `chatbot.py` and `server/utils/devreotesNdjson.ts` in the Nuxt app).
- In **agent** mode with **`DEVREOTES_AGENT_UI_PROGRESS`**, additional NDJSON types (**`agent_status`**, **`agent_plan`**, **`agent_step`**) describe high-level status, plan checklist updates, and per-tool rows. Nuxt forwards these as SSE **`data-devreotes-progress`**; the chat page shows **`DevreotesProgressStrip`** during retrieval.
- The Nuxt route **`POST /api/devreotes/chats/[id]`** turns NDJSON into an **AI SDK UI message stream** for the browser; the client **`consumeDevreotesUiSse`** reads SSE, appends **`text-delta`** to the assistant message, then handles **`data-devreotes-followups`** for live follow-up chips. The stream ends with a **`finish`** chunk after follow-ups complete.

### 11.4 Retrieval / “decision” trace (audit payload)

Each finished turn can carry a structured **`devreotes_trace`** (JSON) alongside the assistant text, for transparency and debugging:

| Field (concept) | Role |
|-----------------|------|
| **`query_type` / `query_type_label`** | Internal route key vs human-readable label (e.g. “Gene-focused retrieval”, “Agent retrieval (tools)”). |
| **`routed_key`** | Gene symbol, author string, `themes`, etc., when applicable. |
| **`results_count`** | How many retrieved rows fed the answer (where applicable). |
| **`sources`** | Ordered list of source strings (e.g. title + chunk id) aligned with citation numbers **`[1]`**, **`[2]`**, … |
| **`retrieval_preview`** | Structured snapshot of retrieval rows (scores, routes, ids). |
| **`suggested_followups`** | Optional list of suggested next questions (streamed via SSE, then stored). |
| **`abstained` / `abstain_reason`** | When the system refuses to answer (e.g. below **`RAG_MIN_SCORE`**, no chunks). |
| **`tool_calls_log`** | In **agent** mode, a log of tool names/args for audit. |
| **`agent_plan`** / **`plan_progress`** | When explicit planning runs, structured plan and step completion (if present in finish payload). |
| **`reasoning_log`** | Optional list of reasoning snippets when **`DEVREOTES_AGENT_REASONING_LOG`** is enabled. |
| **`trace_version`** | Schema version for forward compatibility. |

In the chat UI, **`DevreotesTracePanel.vue`** shows a collapsible **“Retrieval trace”** under assistant messages (including plan / reasoning sections when data is present). The same **`sources`** list drives **citation tooltips** in the rendered markdown (`injectCitationMarkdown` wraps `[n]` / list-line citations and maps indices to `sources`).

### 11.5 Citations in the UI

- The backend instructs the model to cite with **`[1]`**, **`[2]`**, … matching numbered passages. Agent prompts may also use **`[S1]`**-style tags when **gene statistics** and **chunk passages** appear in one context.
- The Nuxt layer injects **styled, hover/focus tooltips** (via `data-tooltip` + CSS) so reference markers are visually distinct and show the corresponding **source title/snippet**, not just bare numbers.

### 11.6 Persistence (Nuxt / Hub)

- Chat messages can be stored in the app database; assistant rows may include **`devreotes_trace`** (or snake_case **`devreotes_trace`**) so traces survive reloads. See server schema/migrations under `nuxt/server/db/`.

### 11.7 Quick index (agent, API, trace, streaming)

Paths in this table are relative to **this project folder** (`DevreotesLabResearchChatbot/`).

| Topic | Location |
|--------|-----------|
| RAG mode switch + streaming Q&A + chat history + agent outer loop | `backend/app/chatbot.py` (`_rag_mode`, `iter_run_evidence_agent_outer`, `iter_answer_ndjson`) |
| Agent tools + inner loop | `backend/app/agent_tools.py` (`iter_run_evidence_agent`, …) |
| Structured planner + clarification | `backend/app/agent_planner.py` |
| Replan / merge between batches | `backend/app/agent_replan.py` |
| FastAPI stream (optional) + history payload (`summary`, `messages`) | `backend/app/api_app.py` (per `structure.md`) |
| Nuxt Devreotes route + stream + summary persistence | `nuxt/server/api/devreotes/chats/[id].post.ts`, `server/utils/devreotesNdjson.ts` |
| Progress NDJSON → SSE helpers | `nuxt/app/utils/devreotesProgress.ts`, `nuxt/app/utils/devreotesSse.ts` (`onProgress`) |
| Bridge subprocess (JSON stdin) | `nuxt/server/python/devreotes_bridge.py` |
| Trace types | `nuxt/app/types/devreotes-trace.ts`, `server/types/devreotes-trace.ts` |
| Trace UI | `nuxt/app/components/DevreotesTracePanel.vue` |
| In-chat progress strip | `nuxt/app/components/DevreotesProgressStrip.vue` |
| Client stream consumer | `nuxt/app/utils/devreotesSse.ts` |
| Chat page (trace + citations + progress) | `nuxt/app/pages/chat/[id].vue` |
| Citation injection | `nuxt/app/utils/injectCitationMarkdown.ts`, `app/assets/css/main.css` (`.devreotes-cite`) |
| Planner / replan tests | `backend/tests/test_agent_planner.py`, `backend/tests/test_agent_replan_merge.py` |

---

## 12. Where to look in the repo

| Topic | Location |
|--------|----------|
| Extract PDFs | `backend/app/extract_pdfs.py` |
| Ingest / graph writes | `backend/app/ingest_papers.py` |
| Schema / indexes | `backend/app/setup_schema.py` |
| Embeddings | `backend/app/create_embeddings.py` |
| Search & routes | `backend/app/retrieval.py`, `backend/app/router.py` |
| Router regression tests | `backend/tests/test_router_golden.py` — run `PYTHONPATH=. python -m unittest backend.tests.test_router_golden -v` after changing `classify_query` |
| Q&A + streaming path | `backend/app/chatbot.py` |
| Nuxt → Python | `nuxt/server/python/devreotes_bridge.py` |
| Env template | `.env.example` |
| Run order | `structure.md` |

For **agent mode, HTTP API, trace panel, NDJSON streaming, and citation UI**, see **§11** and especially **§11.7**.

---

*This guide reflects the Devreotes Lab Research Chatbot layout under `backend/app/` and the Nuxt bridge. If you change ingest rules or schema, re-run the offline pipeline so the database matches the code.*
