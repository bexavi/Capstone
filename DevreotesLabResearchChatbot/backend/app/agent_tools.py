"""
LangChain tools wrapping Neo4j-backed retrieval for multi-step evidence gathering.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from .paths import load_project_dotenv
from .retrieval import (
    graph_corpus_meta,
    graph_search_author_directory,
    graph_search_author_publication_stats,
    graph_search_by_author,
    graph_search_by_gene,
    graph_search_research_themes,
    vector_search,
)

load_project_dotenv()


def _rag_top_k() -> int:
    return int(os.getenv("RAG_TOP_K", "8"))


def _max_context_chars() -> int:
    return int(os.getenv("MAX_CONTEXT_CHARS_PER_CHUNK", "900"))


def _slim_chunk_rows(rows: list, route: str) -> list[dict[str, Any]]:
    cap = _max_context_chars()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "paper_id": r.get("paper_id") or r.get("id"),
                "title": r.get("title"),
                "chunk_id": r.get("chunk_id"),
                "text": (r.get("text") or "")[:cap],
                "score": r.get("score"),
                "gene": r.get("gene"),
                "author": r.get("author"),
                "source_file": r.get("source_file"),
                "route": route,
            }
        )
    return out


def _pack_chunks(route: str, rows: list) -> str:
    return json.dumps(
        {"kind": "chunks", "route": route, "items": _slim_chunk_rows(rows, route)},
        ensure_ascii=True,
    )


@tool
def semantic_search(query: str) -> str:
    """Vector similarity search over paper chunks. Use for broad or conceptual questions when no specific HGNC gene symbol or author filter is required. Pass a focused search phrase."""
    q = (query or "").strip()
    if not q:
        return json.dumps({"kind": "chunks", "route": "semantic", "items": []}, ensure_ascii=True)
    rows = vector_search(q, top_k=_rag_top_k())
    return _pack_chunks("semantic", rows)


@tool
def gene_literature_search(gene_symbol: str, question_context: str = "") -> str:
    """Retrieve chunks from papers that mention a human gene by official HGNC symbol (e.g. PTEN, PIK3CB). Optionally pass question_context to steer ranking. Returns empty items if the symbol is not found."""
    sym = (gene_symbol or "").strip().upper()
    if not sym:
        return json.dumps({"kind": "chunks", "route": "gene", "items": []}, ensure_ascii=True)
    ctx = (question_context or "").strip()
    rows = graph_search_by_gene(sym, question=ctx or None, top_k=_rag_top_k())
    return _pack_chunks("gene", rows)


@tool
def author_literature_search(author_name: str, question_context: str = "") -> str:
    """Retrieve chunks from papers associated with an author name (matched loosely). Default lab context: use 'Devreotes' if unsure. Pass question_context for semantic reranking within that author scope."""
    name = (author_name or "").strip() or "Devreotes"
    ctx = (question_context or "").strip()
    rows = graph_search_by_author(name, question=ctx or None, top_k=max(_rag_top_k(), 12))
    return _pack_chunks("author", rows)


@tool
def corpus_gene_frequencies() -> str:
    """Corpus-wide gene mention counts (papers per gene via the graph). Use for questions about most-mentioned genes, prevalence, or bibliometric summaries—not for passage-level quotes."""
    rows, meta = graph_search_research_themes()
    return json.dumps(
        {"kind": "themes", "route": "themes", "items": rows or [], "meta": meta},
        ensure_ascii=True,
    )


@tool
def corpus_author_publication_stats() -> str:
    """Authors with multiple papers in this corpus (:AUTHORED counts). Use for which authors appear on more than one paper, collaborators across publications, or publication counts per author—not 'papers by a specific name'."""
    rows = graph_search_author_publication_stats()
    return json.dumps({"kind": "author_stats", "route": "author_stats", "items": rows or []}, ensure_ascii=True)


@tool
def corpus_all_authors_directory() -> str:
    """Full author bibliography: every :Author with :AUTHORED links and their distinct paper counts (min 1 paper), sorted by count. Use for 'list all authors', 'complete author list', or 'every author in the corpus'—not for 'papers by Dr. X'."""
    rows, meta = graph_search_author_directory()
    return json.dumps(
        {"kind": "author_directory", "route": "author_directory", "items": rows or [], "meta": meta},
        ensure_ascii=True,
    )


@tool
def corpus_graph_inventory() -> str:
    """Exact counts of Paper, Chunk, Gene, Author, Entity, and Claim nodes in the Neo4j graph. Use when the user asks how many papers/chunks/genes/authors are in the corpus, database, or graph—not for 'most mentioned' genes (use corpus_gene_frequencies) or passage search."""
    meta = graph_corpus_meta()
    return json.dumps(
        {"kind": "corpus_meta", "route": "corpus_meta", "items": [meta]},
        ensure_ascii=True,
    )


DEVREOTES_RETRIEVAL_TOOLS = [
    semantic_search,
    gene_literature_search,
    author_literature_search,
    corpus_gene_frequencies,
    corpus_author_publication_stats,
    corpus_all_authors_directory,
    corpus_graph_inventory,
]

# User-facing labels for streaming progress (NDJSON / UI).
TOOL_UI_LABELS: dict[str, str] = {
    "semantic_search": "Searching papers for relevant passages",
    "gene_literature_search": "Finding papers that mention this gene",
    "author_literature_search": "Finding papers by this author",
    "corpus_gene_frequencies": "Loading gene mention statistics",
    "corpus_author_publication_stats": "Loading author publication counts",
    "corpus_all_authors_directory": "Loading the full author list",
    "corpus_graph_inventory": "Counting papers and nodes in the corpus graph",
}

AGENT_SYSTEM_PROMPT = """You are a retrieval planner for a biomedical literature corpus (Prof. Devreotes lab papers).

Your job is to call one or more tools to gather evidence for the user's question. Rules:
- Prefer gene_literature_search when the user names a specific human gene symbol (HGNC).
- Prefer author_literature_search when the question is about passages from papers by a **specific** author name.
- Use corpus_author_publication_stats for questions about **which authors** show up on **multiple papers**, collaborators across the corpus, or author–publication counts (not a single named author).
- Use corpus_all_authors_directory for a **complete list** of authors with paper counts (every author in the graph), or when the user asks for **all** / **every** author.
- Use corpus_gene_frequencies for questions about which genes are most mentioned across the corpus, counts, or prevalence.
- Use corpus_graph_inventory for **total** papers, chunks, genes, or authors **in the graph/corpus** (exact inventory counts)—not semantic search over text.
- For **combined** questions (e.g. full author list **and** how many papers in the corpus), call **corpus_graph_inventory** together with **corpus_all_authors_directory** or **corpus_author_publication_stats** as appropriate.
- Use semantic_search for general conceptual questions or when other tools are not a clear fit.
- You may call multiple tools if the question combines scopes (e.g. gene + author).
- Do not write a final answer to the user; only call tools. After you have enough evidence, stop calling tools (respond with no tool calls)."""


def _reasoning_log_enabled() -> bool:
    return os.getenv("DEVREOTES_AGENT_REASONING_LOG", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _think_step_enabled() -> bool:
    return os.getenv("DEVREOTES_AGENT_THINK_STEP", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _extract_ai_text(msg: Any) -> str:
    c = getattr(msg, "content", None)
    if isinstance(c, str):
        return c.strip()
    if isinstance(c, list):
        parts: list[str] = []
        for p in c:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text", "")))
            elif isinstance(p, str):
                parts.append(p)
        return "".join(parts).strip()
    return ""


def compact_observation_summary(ev: dict[str, Any]) -> str:
    """Compact text for replan LLM (no full chunk bodies)."""
    lines: list[str] = []
    log = ev.get("tool_calls_log") or []
    names = [str(x.get("name") or "?") for x in log[-16:]]
    lines.append(f"Tool calls so far ({len(log)}): {', '.join(names) if names else 'none'}")
    chunks = ev.get("raw_chunks") or []
    lines.append(f"Chunk rows accumulated: {len(chunks)}")
    papers = {str(c.get("paper_id") or "") for c in chunks if c.get("paper_id")}
    papers.discard("")
    if papers:
        sample = list(papers)[:10]
        lines.append(f"Sample paper_ids: {', '.join(sample)}")
    th = ev.get("themes")
    if isinstance(th, list) and th:
        lines.append(f"Gene-frequency rows: {len(th)}")
    ast = ev.get("author_stats")
    if isinstance(ast, list) and ast:
        lines.append(f"Author-stats rows: {len(ast)}")
    ad = ev.get("author_directory")
    if isinstance(ad, list) and ad:
        lines.append(f"Author-directory rows: {len(ad)}")
    cm = ev.get("corpus_meta")
    if isinstance(cm, list) and cm:
        lines.append("Corpus graph inventory: present")
    return "\n".join(lines)


def _merge_evidence_piece(merged: dict[str, Any], piece: dict[str, Any]) -> None:
    merged["used_tools"] = merged["used_tools"] or bool(piece.get("used_tools"))
    merged["raw_chunks"].extend(piece.get("raw_chunks") or [])
    merged["tool_calls_log"].extend(piece.get("tool_calls_log") or [])
    for x in piece.get("reasoning_log") or []:
        merged["reasoning_log"].append(x)
    if piece.get("themes") is not None:
        merged["themes"] = list(piece["themes"])
    if piece.get("author_stats") is not None:
        merged["author_stats"] = list(piece["author_stats"])
    if piece.get("author_directory") is not None:
        merged["author_directory"] = list(piece["author_directory"])
    adm = piece.get("author_directory_meta")
    if isinstance(adm, dict) and adm:
        merged["author_directory_meta"] = dict(adm)
    if piece.get("corpus_meta") is not None:
        merged["corpus_meta"] = list(piece["corpus_meta"])
    tm = piece.get("themes_meta")
    if isinstance(tm, dict) and tm:
        merged["themes_meta"] = dict(tm)


def _final_evidence_from_merged(merged: dict[str, Any]) -> dict[str, Any]:
    adm = merged.get("author_directory_meta") or {}
    tmeta = merged.get("themes_meta") or {}
    return {
        "used_tools": bool(merged.get("used_tools")),
        "raw_chunks": list(merged.get("raw_chunks") or []),
        "themes": merged.get("themes") if merged.get("themes") else None,
        "author_stats": merged.get("author_stats") if merged.get("author_stats") else None,
        "author_directory": merged.get("author_directory") if merged.get("author_directory") else None,
        "author_directory_meta": dict(adm) if adm else None,
        "corpus_meta": merged.get("corpus_meta") if merged.get("corpus_meta") else None,
        "themes_meta": dict(tmeta) if tmeta else None,
        "tool_calls_log": list(merged.get("tool_calls_log") or []),
        "reasoning_log": list(merged["reasoning_log"]) if merged.get("reasoning_log") else None,
    }


def _parse_tool_payload(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return {"kind": "unknown", "items": [], "raw": raw[:500]}


def _accumulate_payload(
    chunk_acc: list[dict[str, Any]],
    themes_holder: list[Any],
    author_stats_holder: list[Any],
    author_directory_holder: list[Any],
    author_directory_meta_holder: dict[str, Any],
    corpus_meta_holder: list[Any],
    themes_meta_holder: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    kind = payload.get("kind")
    if kind == "chunks":
        items = payload.get("items") or []
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    chunk_acc.append(it)
    elif kind == "themes":
        items = payload.get("items") or []
        if isinstance(items, list):
            themes_holder.clear()
            themes_holder.extend(items)
        m = payload.get("meta")
        if isinstance(m, dict):
            themes_meta_holder.clear()
            themes_meta_holder.update(m)
    elif kind == "author_stats":
        items = payload.get("items") or []
        if isinstance(items, list):
            author_stats_holder.clear()
            author_stats_holder.extend(items)
    elif kind == "author_directory":
        items = payload.get("items") or []
        if isinstance(items, list):
            author_directory_holder.clear()
            author_directory_holder.extend(items)
        m = payload.get("meta")
        if isinstance(m, dict):
            author_directory_meta_holder.clear()
            author_directory_meta_holder.update(m)
    elif kind == "corpus_meta":
        items = payload.get("items") or []
        if isinstance(items, list) and items:
            corpus_meta_holder.clear()
            corpus_meta_holder.extend(items)


def iter_run_evidence_agent(
    llm,
    question: str,
    plan_context: str | None = None,
    *,
    ui_progress: bool = False,
    messages: list | None = None,
):
    """
    Single-batch tool-calling loop (up to DEVREOTES_AGENT_MAX_STEPS).
    If ``messages`` is provided, continues from that transcript (replan rounds).
    Yields NDJSON lines when ui_progress is True.
    Returns evidence dict plus ``messages`` (for outer replan loop).
    """
    max_steps = max(1, int(os.getenv("DEVREOTES_AGENT_MAX_STEPS", "6")))
    bound = llm.bind_tools(DEVREOTES_RETRIEVAL_TOOLS)
    log_reasoning = _reasoning_log_enabled()
    think_step = _think_step_enabled()
    reasoning_log: list[dict[str, Any]] = []

    if messages is None:
        human_content = (question or "").strip()
        if plan_context and plan_context.strip():
            human_content = (
                "Retrieval plan (prioritize unless observations contradict it):\n"
                f"{plan_context.strip()}\n\n---\n{human_content}"
            )
        messages = [
            SystemMessage(content=AGENT_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]
    else:
        messages = list(messages)

    tool_calls_log: list[dict[str, Any]] = []
    chunk_acc: list[dict[str, Any]] = []
    themes_holder: list[Any] = []
    author_stats_holder: list[Any] = []
    author_directory_holder: list[Any] = []
    author_directory_meta_holder: dict[str, Any] = {}
    corpus_meta_holder: list[Any] = []
    themes_meta_holder: dict[str, Any] = {}
    tool_by_name = {t.name: t for t in DEVREOTES_RETRIEVAL_TOOLS}
    used_tools = False

    for step_i in range(max_steps):
        if ui_progress:
            yield json.dumps(
                {
                    "type": "agent_status",
                    "phase": "tools",
                    "message": "Choosing retrieval tools and running searches…",
                },
                ensure_ascii=True,
            ) + "\n"
        if think_step:
            think_resp = llm.invoke(
                list(messages)
                + [
                    HumanMessage(
                        content=(
                            "Before calling retrieval tools, state in 1–2 sentences what you will "
                            "try to retrieve and why. Do not call tools in this reply."
                        )
                    )
                ]
            )
            ttext = _extract_ai_text(think_resp)
            if ttext:
                if log_reasoning:
                    reasoning_log.append({"kind": "think", "step": step_i, "text": ttext[:4000]})
                messages.append(AIMessage(content=ttext))

        ai_msg: AIMessage = bound.invoke(messages)
        body = _extract_ai_text(ai_msg)
        if body and log_reasoning:
            reasoning_log.append({"kind": "tool_round", "step": step_i, "text": body[:4000]})

        calls = getattr(ai_msg, "tool_calls", None) or []
        if not calls:
            messages.append(ai_msg)
            break
        used_tools = True
        messages.append(ai_msg)
        for tc in calls:
            name = tc.get("name")
            tid = tc.get("id") or tc.get("tool_call_id") or str(uuid.uuid4())
            args = tc.get("args")
            if not isinstance(args, dict):
                args = {}
            tool_calls_log.append({"name": name, "args": dict(args)})
            tool_fn = tool_by_name.get(name)
            if tool_fn is None:
                out = json.dumps({"kind": "error", "message": f"unknown_tool:{name}"})
            else:
                if ui_progress:
                    label = TOOL_UI_LABELS.get(name or "", name or "retrieval tool")
                    yield json.dumps(
                        {
                            "type": "agent_step",
                            "step_id": name or "unknown",
                            "status": "active",
                            "label": label,
                        },
                        ensure_ascii=True,
                    ) + "\n"
                try:
                    out = tool_fn.invoke(args)
                except Exception as exc:  # pragma: no cover - defensive
                    out = json.dumps({"kind": "error", "message": str(exc)})
                if ui_progress:
                    yield json.dumps(
                        {
                            "type": "agent_step",
                            "step_id": name or "unknown",
                            "status": "done",
                            "label": TOOL_UI_LABELS.get(name or "", name or "tool"),
                        },
                        ensure_ascii=True,
                    ) + "\n"
            payload = _parse_tool_payload(out if isinstance(out, str) else str(out))
            _accumulate_payload(
                chunk_acc,
                themes_holder,
                author_stats_holder,
                author_directory_holder,
                author_directory_meta_holder,
                corpus_meta_holder,
                themes_meta_holder,
                payload,
            )
            messages.append(ToolMessage(content=out if isinstance(out, str) else str(out), tool_call_id=tid))

    piece = {
        "used_tools": used_tools,
        "raw_chunks": chunk_acc,
        "themes": list(themes_holder) if themes_holder else None,
        "author_stats": list(author_stats_holder) if author_stats_holder else None,
        "author_directory": list(author_directory_holder) if author_directory_holder else None,
        "author_directory_meta": dict(author_directory_meta_holder) if author_directory_meta_holder else None,
        "corpus_meta": list(corpus_meta_holder) if corpus_meta_holder else None,
        "themes_meta": dict(themes_meta_holder) if themes_meta_holder else None,
        "tool_calls_log": tool_calls_log,
        "reasoning_log": reasoning_log if reasoning_log else None,
        "messages": messages,
    }
    return piece


def iter_run_evidence_agent_outer(
    llm,
    question: str,
    plan_context: str | None = None,
    *,
    ui_progress: bool = False,
):
    """
    Runs one or more retrieval batches with optional replan (DEVREOTES_AGENT_REPLAN_ROUNDS).
    Yields the same NDJSON progress lines as the inner iterator.
    """
    from .agent_replan import replan_rounds_cap, run_replan_decision

    replan_max = replan_rounds_cap()
    merged: dict[str, Any] = {
        "used_tools": False,
        "raw_chunks": [],
        "tool_calls_log": [],
        "reasoning_log": [],
        "themes": None,
        "author_stats": None,
        "author_directory": None,
        "author_directory_meta": {},
        "corpus_meta": None,
        "themes_meta": {},
    }
    messages: list | None = None

    for outer in range(replan_max + 1):
        gen = iter_run_evidence_agent(
            llm,
            question,
            plan_context,
            ui_progress=ui_progress,
            messages=messages,
        )
        try:
            while True:
                yield next(gen)
        except StopIteration as exc:
            piece = exc.value

        messages = piece["messages"]
        _merge_evidence_piece(merged, piece)

        if outer >= replan_max:
            break
        if outer == 0 and not piece.get("used_tools"):
            break
        obs = compact_observation_summary(merged)
        try:
            dec = run_replan_decision(llm, question, obs)
        except Exception:
            break
        if dec.action == "sufficient":
            break
        messages = list(messages) + [
            HumanMessage(
                content=(
                    "Retrieval supervisor (replan):\n"
                    f"{dec.guidance.strip()}\n\n"
                    f"Compact observations so far:\n{obs}\n\n"
                    "Call more retrieval tools if needed; otherwise respond with no tool calls."
                )
            )
        ]
        if ui_progress:
            yield json.dumps(
                {
                    "type": "agent_status",
                    "phase": "replanning",
                    "message": "Adjusting retrieval based on what we found so far…",
                },
                ensure_ascii=True,
            ) + "\n"

    return _final_evidence_from_merged(merged)


def run_evidence_agent(llm, question: str, plan_context: str | None = None) -> dict[str, Any]:
    """
    Run tool-calling loop; return merged raw chunk dicts, optional themes list, and log.
    If the model issues no tool calls on the first turn, used_tools is False (caller should fallback).
    """
    gen = iter_run_evidence_agent_outer(llm, question, plan_context, ui_progress=False)
    try:
        while True:
            next(gen)
    except StopIteration as exc:
        return exc.value
