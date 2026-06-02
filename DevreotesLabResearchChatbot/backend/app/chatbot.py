import json
import os
import sys
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .paths import HGNC_LOOKUP_PATH, load_project_dotenv
from .retrieval import (
    graph_corpus_meta,
    graph_search_author_directory,
    graph_search_author_publication_stats,
    graph_search_by_author,
    graph_search_by_gene,
    graph_search_research_themes,
    themes_limit,
    vector_search,
)
from .router import (
    classify_query,
    extract_author_from_question,
    extract_gene_from_question,
    is_author_directory_query,
    is_author_stats_query,
    wants_corpus_inventory_addon,
)
from .agent_planner import (
    allow_clarification,
    explicit_plan_enabled,
    format_plan_for_agent,
    run_agent_planner,
)
from .agent_tools import iter_run_evidence_agent_outer, run_evidence_agent


load_project_dotenv()

with HGNC_LOOKUP_PATH.open("r", encoding="utf-8") as f:
    hgnc_lookup = json.load(f)

llm = ChatOpenAI(model="gpt-4o", temperature=0)
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "8"))
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.35"))
MAX_CONTEXT_CHARS_PER_CHUNK = int(os.getenv("MAX_CONTEXT_CHARS_PER_CHUNK", "900"))
MAX_CONTEXT_CHUNKS = int(os.getenv("MAX_CONTEXT_CHUNKS", "8"))

SYSTEM_PROMPT = (
    "You are a research assistant for Prof. Peter Devreotes' lab at Johns Hopkins University. "
    "You answer questions based ONLY on the provided research papers from the lab corpus. "
    "Do not use outside knowledge. If the answer is not in the provided context, say so clearly. "
    "When the context supports an answer, explain in depth: define important terms, trace mechanisms "
    "step by step, and tie each substantive claim to the cited evidence. "
    "Use clear structure (short sections or bullets) when it helps readability. "
    "Prefer scientific precision and completeness over brevity; do not pad or speculate beyond the passages. "
    "For equations, use Markdown math: inline as $expression$ and display as $$expression$$ "
    "(not \\(...\\) or \\[...\\]). "
    "The conversation context may be included to resolve references between turns; treat it only as context, not as evidence. "
    "When the context provides numbered paper passages, cite them as [1], [2], etc. "
    "When the context is an author list without passage numbers, give names and counts directly—do not invent [A1]-style row tags. "
    "When separate sections define bracket labels, follow the user message "
    "(e.g. [C1]–[C6] for corpus-wide graph totals, [S1] for gene statistics). "
    "For corpus-wide totals (how many papers, chunks, etc.), use only numbers that appear explicitly in the provided context; "
    "do not infer totals from a sample of passages."
)

CONVERSATION_RECENT_TURNS = int(os.getenv("DEVREOTES_CONVERSATION_RECENT_TURNS", "10"))


def _extract_chat_history(chat_history: Any):
    """
    Supported shapes:
      - None
      - { summary: str | None, messages: list[{role, content}] | None }
      - messages: list[{role, content}]
    """
    if chat_history is None:
        return None, None
    if isinstance(chat_history, dict):
        return chat_history.get("summary"), chat_history.get("messages")
    return None, chat_history


def _format_conversation_context(summary: str | None, messages: Any) -> str:
    parts: list[str] = []
    if isinstance(summary, str):
        s = summary.strip()
        if s:
            parts.append(f"Conversation summary:\n{s}")

    if messages is not None:
        try:
            recent = list(messages)[-CONVERSATION_RECENT_TURNS:]
        except TypeError:
            recent = []

        turn_lines: list[str] = []
        for m in recent:
            if not isinstance(m, dict):
                continue
            role = m.get("role") or "user"
            content = m.get("content")
            if not isinstance(content, str):
                continue
            content = content.strip()
            if not content:
                continue
            turn_lines.append(f"{str(role).title()}: {content}")

        if turn_lines:
            parts.append("Recent turns:\n" + "\n".join(turn_lines))

    return "\n\n".join(parts)


def _build_retrieval_question(user_question: str, conversation_context: str) -> str:
    user_question = (user_question or "").strip()
    if not conversation_context:
        return user_question
    return f"{conversation_context}\n\nCurrent user question: {user_question}"


def _query_type_label(effective: str) -> str:
    """Human-readable route for UI/debug (internal keys stay stable)."""
    return {
        "themes": "Gene mention frequency (corpus)",
        "author_stats": "Author publication counts (corpus)",
        "corpus_meta": "Corpus inventory (graph counts)",
        "author_directory": "Full author bibliography (graph)",
        "gene": "Gene-focused retrieval",
        "author": "Author-filtered retrieval",
        "semantic": "Semantic (vector) retrieval",
        "agent": "Agent retrieval (tools)",
    }.get(effective, effective)


def _result_score(row) -> float:
    score = row.get("score")
    if score is None:
        return 0.0
    try:
        return float(score)
    except (TypeError, ValueError):
        return 0.0


def _author_stats_context_limit() -> int:
    return max(5, int(os.getenv("AUTHOR_STATS_CONTEXT_LIMIT", "40")))


def _author_directory_context_limit() -> int:
    return max(10, int(os.getenv("AUTHOR_DIRECTORY_CONTEXT_LIMIT", "120")))


def _corpus_wide_addon_block(meta: dict) -> str:
    """Corpus totals with [C1]–[C6] labels (shown above a plain author list)."""
    m = meta if isinstance(meta, dict) else {}
    return (
        "Corpus-wide graph totals (cite as [C1]–[C6] only for these lines; author lines below are named, not tagged):\n"
        f"[C1] Papers (distinct :Paper nodes): {int(m.get('paper_count') or 0)}\n"
        f"[C2] Chunks: {int(m.get('chunk_count') or 0)}\n"
        f"[C3] Gene nodes: {int(m.get('gene_count') or 0)}\n"
        f"[C4] Author nodes: {int(m.get('author_count') or 0)}\n"
        f"[C5] Entity nodes: {int(m.get('entity_count') or 0)}\n"
        f"[C6] Claims: {int(m.get('claim_count') or 0)}"
    )


def _author_directory_disclosure_prompt(meta: dict | None) -> str:
    if meta is None:
        return ""
    lim = int(meta.get("directory_limit") or 200)
    truncated = bool(meta.get("truncated"))
    parts = [
        f"This table lists authors with at least {int(meta.get('min_papers') or 1)} distinct paper(s), "
        f"up to {lim} rows, sorted by paper count.",
        "Author names follow extracted JSON / Crossref (same source as _metadata_report.json).",
    ]
    if truncated:
        parts.append(
            f"More authors exist beyond row {lim}; the list is truncated by configuration. "
            "Say so if the user asked for a complete census."
        )
    return " ".join(parts)


def build_context(results, result_type: str = "semantic", max_chunks: int = MAX_CONTEXT_CHUNKS) -> str:
    if not results:
        return "No relevant papers found in the corpus."

    context_parts = []
    if result_type == "themes":
        context_parts.append(
            "Gene mention frequency across the corpus (papers with a :MENTIONS edge to each gene; "
            "this is a bibliometric summary, not a qualitative thematic analysis):"
        )
        for idx, item in enumerate(results[:themes_limit()], 1):
            g = item.get("gene", "Unknown")
            n = item.get("paper_count", 0)
            context_parts.append(f"[{idx}] Gene {g}: mentioned in {n} paper(s)")
        return "\n".join(context_parts)

    if result_type == "author_stats":
        cap = _author_stats_context_limit()
        context_parts.append(
            "Authors with multiple papers (:Author)-[:AUTHORED]->(:Paper); "
            "each line is one author’s distinct-paper count (not total corpus size). "
            "Refer to authors by name in your answer."
        )
        for item in results[:cap]:
            a = item.get("author") or item.get("author_key") or "Unknown"
            n = item.get("paper_count", 0)
            context_parts.append(f"• {a}: {n} paper(s)")
        return "\n".join(context_parts)

    if result_type == "author_directory":
        cap = _author_directory_context_limit()
        context_parts.append(
            "All authors in the graph with at least the configured minimum papers per author. "
            "Each line is that author’s distinct-paper count only. Refer to authors by name in your answer."
        )
        for item in results[:cap]:
            a = item.get("author") or item.get("author_key") or "Unknown"
            n = item.get("paper_count", 0)
            context_parts.append(f"• {a}: {n} paper(s)")
        return "\n".join(context_parts)

    if result_type == "corpus_meta":
        if not results or not isinstance(results[0], dict):
            return "No corpus statistics available."
        m = results[0]
        lines = [
            "Exact node counts from the Neo4j graph (full corpus, not a sample of passages):",
            f"[1] Papers: {int(m.get('paper_count') or 0)}",
            f"[2] Chunks: {int(m.get('chunk_count') or 0)}",
            f"[3] Genes (Gene nodes): {int(m.get('gene_count') or 0)}",
            f"[4] Authors (Author nodes): {int(m.get('author_count') or 0)}",
            f"[5] Entities (Entity nodes): {int(m.get('entity_count') or 0)}",
            f"[6] Claims: {int(m.get('claim_count') or 0)}",
        ]
        return "\n".join(lines)

    for idx, item in enumerate(results[:max_chunks], 1):
        title = item.get("title", "Unknown")
        chunk_id = item.get("chunk_id", "chunk_unknown")
        score = _result_score(item)
        source_file = item.get("source_file")
        text = (item.get("text") or "")[:MAX_CONTEXT_CHARS_PER_CHUNK]
        header = f"[{idx}] title={title} chunk_id={chunk_id} score={score:.4f}"
        if source_file:
            header += f" file={source_file}"
        context_parts.append(f"{header}\n{text}")
    return "\n\n".join(context_parts)


def _build_sources_and_preview(results, result_kind: str):
    """
    result_kind matches the retrieval path (usually `effective_query_type`):
    themes | author_stats | author_directory | corpus_meta | gene | author | semantic.
    """
    sources = []
    preview = []

    if result_kind == "author_directory":
        cap = _author_directory_context_limit()
        for item in results[:cap]:
            a = item.get("author") or item.get("author_key") or "Unknown"
            n = item.get("paper_count", 0)
            sources.append(f"{a} ({n} papers)")
            preview.append(
                {
                    "author": a,
                    "author_key": item.get("author_key"),
                    "paper_count": n,
                    "stat_type": "author_directory_row",
                    "route": "author_directory",
                }
            )
        return sources, preview

    if result_kind == "corpus_meta" and results and isinstance(results[0], dict):
        m = results[0]
        summary = (
            f"Papers={m.get('paper_count', 0)}, Chunks={m.get('chunk_count', 0)}, "
            f"Genes={m.get('gene_count', 0)}, Authors={m.get('author_count', 0)}"
        )
        sources.append(summary)
        preview.append(
            {
                "stat_type": "corpus_graph_counts",
                "route": "corpus_meta",
                **{k: m.get(k) for k in ("paper_count", "chunk_count", "gene_count", "author_count", "entity_count", "claim_count")},
            }
        )
        return sources, preview

    if result_kind == "author_stats":
        cap = _author_stats_context_limit()
        for item in results[:cap]:
            a = item.get("author") or item.get("author_key") or "Unknown"
            n = item.get("paper_count", 0)
            sources.append(f"{a} ({n} papers)")
            preview.append(
                {
                    "author": a,
                    "author_key": item.get("author_key"),
                    "paper_count": n,
                    "stat_type": "author_publication_count",
                    "route": "author_stats",
                }
            )
        return sources, preview

    if result_kind == "themes":
        for item in results[:10]:
            gene = item.get("gene", "Unknown")
            count = item.get("paper_count", 0)
            sources.append(f"{gene} ({count} papers)")
            preview.append(
                {
                    "gene": gene,
                    "paper_count": count,
                    "stat_type": "gene_mention_frequency",
                    "route": "themes",
                }
            )
        return sources, preview

    seen_sources = set()
    for item in results[:MAX_CONTEXT_CHUNKS]:
        title = (item.get("title") or "Unknown").strip()
        chunk_id = item.get("chunk_id")
        source_file = item.get("source_file")
        source_key = f"{title} [{chunk_id}]" if chunk_id else title
        if source_file:
            source_key = f"{source_key} ({source_file})"
        if source_key and source_key not in seen_sources:
            sources.append(source_key)
            seen_sources.add(source_key)
        row_route = item.get("route") or result_kind
        preview.append(
            {
                "paper_id": item.get("paper_id") or item.get("id"),
                "title": title,
                "source_file": source_file,
                "chunk_id": chunk_id,
                "score": item.get("score"),
                "gene": item.get("gene"),
                "author": item.get("author"),
                "route": row_route,
                "retrieval_path": result_kind,
            }
        )
    return sources, preview


def _retrieve_or_abstain(question: str, query_type: str, routed_key: str | None):
    if query_type == "themes":
        results, themes_meta = graph_search_research_themes()
        if not results:
            return {
                "abstained": True,
                "abstain_reason": "no_theme_data",
                "results": [],
            }
        return {
            "abstained": False,
            "abstain_reason": None,
            "results": results,
            "themes_meta": themes_meta,
        }

    if query_type == "author_stats":
        results = graph_search_author_publication_stats()
        if not results:
            return {
                "abstained": True,
                "abstain_reason": "no_author_stats",
                "results": [],
            }
        out = {
            "abstained": False,
            "abstain_reason": None,
            "results": results,
        }
        if wants_corpus_inventory_addon(question):
            out["corpus_meta_addon"] = graph_corpus_meta()
        return out

    if query_type == "author_directory":
        results, dir_meta = graph_search_author_directory()
        if not results:
            return {
                "abstained": True,
                "abstain_reason": "no_author_directory",
                "results": [],
            }
        out = {
            "abstained": False,
            "abstain_reason": None,
            "results": results,
            "author_directory_meta": dir_meta,
        }
        if wants_corpus_inventory_addon(question):
            out["corpus_meta_addon"] = graph_corpus_meta()
        return out

    if query_type == "corpus_meta":
        meta = graph_corpus_meta()
        return {
            "abstained": False,
            "abstain_reason": None,
            "results": [meta],
        }

    if query_type == "gene":
        if routed_key:
            results = graph_search_by_gene(routed_key, question=question, top_k=RAG_TOP_K)
        else:
            results = vector_search(question, top_k=RAG_TOP_K)
    elif query_type == "author":
        results = graph_search_by_author(routed_key or "Devreotes", question=question, top_k=RAG_TOP_K)
    else:
        results = vector_search(question, top_k=RAG_TOP_K)

    if not results:
        return {
            "abstained": True,
            "abstain_reason": "no_chunks",
            "results": [],
        }

    best_score = max(_result_score(r) for r in results)
    if best_score < RAG_MIN_SCORE:
        return {
            "abstained": True,
            "abstain_reason": "below_min_score",
            "results": results,
            "best_score": best_score,
        }

    return {
        "abstained": False,
        "abstain_reason": None,
        "results": sorted(results, key=_result_score, reverse=True),
    }


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _rag_mode() -> str:
    return os.getenv("DEVREOTES_RAG_MODE", "router").strip().lower()


def _ui_progress_enabled() -> bool:
    v = os.getenv("DEVREOTES_AGENT_UI_PROGRESS", "true").strip().lower()
    return v not in ("0", "false", "no", "off")


def _progress_ndjson(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=True) + "\n"


def _agent_plan_ui_payload(agent_plan_dict: dict) -> dict:
    subtasks = agent_plan_dict.get("subtasks") or []
    steps: list[dict] = []
    for i, s in enumerate(subtasks, 1):
        if isinstance(s, str) and s.strip():
            steps.append({"id": f"t{i}", "label": s.strip(), "status": "pending"})
    summary_parts = [x.strip() for x in subtasks[:2] if isinstance(x, str) and str(x).strip()]
    summary = " · ".join(summary_parts) if summary_parts else (str(agent_plan_dict.get("notes") or "")[:240]).strip()
    return {
        "summary": summary or "Retrieval plan",
        "steps": steps,
        "tool_sequence": list(agent_plan_dict.get("tool_sequence") or []),
    }


def _agent_gather_planner_context(question: str, chat_history):
    """Returns {kind: clarify, state} or {kind: go, retrieval_question, conversation_prefix, agent_plan_dict, plan_context}."""
    summary, recent_messages = _extract_chat_history(chat_history)
    conversation_context = _format_conversation_context(summary, recent_messages)
    retrieval_question = _build_retrieval_question(question, conversation_context)
    conversation_prefix = (
        "Conversation context (for reference resolution only):\n"
        f"{conversation_context}\n\n"
        if conversation_context
        else ""
    )

    agent_plan_dict: dict | None = None
    plan_context: str | None = None
    plan_model, plan_err = run_agent_planner(llm, retrieval_question)
    if plan_err:
        _log(f"[Agent planner] failed: {plan_err}")
    if plan_model is not None:
        agent_plan_dict = plan_model.model_dump()
        if plan_model.needs_user_input and allow_clarification():
            clarify = (plan_model.clarification_prompt or "").strip() or (
                "Could you clarify what you would like to know?"
            )
            return {
                "kind": "clarify",
                "state": {
                    "clarification_required": True,
                    "result": {
                        "answer": clarify,
                        "query_type": "agent",
                        "query_type_label": _query_type_label("agent"),
                        "routed_key": "agent",
                        "results_count": 0,
                        "sources": [],
                        "retrieval_preview": [],
                        "abstained": False,
                        "abstain_reason": None,
                        "clarification_required": True,
                        "agent_plan": agent_plan_dict,
                        "tool_calls_log": [],
                    },
                },
            }
        if plan_model.needs_user_input and not allow_clarification():
            plan_model = plan_model.model_copy(
                update={
                    "needs_user_input": False,
                    "clarification_prompt": "",
                    "notes": (
                        (plan_model.notes or "").strip()
                        + "\n(Planner asked for user input but clarification is disabled; proceed with best effort.)"
                    ).strip(),
                }
            )
            agent_plan_dict = plan_model.model_dump()
        plan_context = format_plan_for_agent(plan_model)
    return {
        "kind": "go",
        "retrieval_question": retrieval_question,
        "conversation_prefix": conversation_prefix,
        "agent_plan_dict": agent_plan_dict,
        "plan_context": plan_context,
    }


def _merge_raw_chunks(rows: list) -> list:
    """Deduplicate by chunk_id keeping the row with the best score."""
    by_id: dict = {}
    for r in rows:
        cid = r.get("chunk_id")
        if not cid:
            continue
        prev = by_id.get(cid)
        if prev is None or _result_score(r) > _result_score(prev):
            by_id[cid] = dict(r)
    return sorted(by_id.values(), key=_result_score, reverse=True)


def _themes_context_with_s_labels(results: list, max_n: int | None = None) -> str:
    lines = [
        "Gene mention frequency across the corpus (bibliometric summary):",
    ]
    cap = max_n if max_n is not None else themes_limit()
    for idx, item in enumerate(results[:cap], 1):
        g = item.get("gene", "Unknown")
        pc = item.get("paper_count", 0)
        lines.append(f"[S{idx}] Gene {g}: mentioned in {pc} paper(s)")
    return "\n".join(lines)


def _themes_disclosure_prompt(meta: dict | None) -> str:
    """Instructions so the model discloses ranking/limit vs full :Gene node count."""
    if meta is None:
        return ""
    lim = int(meta.get("themes_limit") or themes_limit())
    truncated = bool(meta.get("truncated"))
    parts = [
        f"These statistics are ranked by distinct papers per gene (descending), showing at most {lim} rows.",
        "They are not an exhaustive list of every :Gene node in the database.",
    ]
    if truncated:
        parts.append(
            f"At least one additional gene would appear beyond row {lim} (result set was cut at the configured limit). "
            "Briefly tell the user the list may be incomplete if they asked for completeness."
        )
    else:
        parts.append(
            "If the user asks for 'all genes' or a complete census, explain that this table is still capped by configuration "
            "and does not enumerate every gene symbol."
        )
    return " ".join(parts)


def _prepare_generation_router(question: str, chat_history=None):
    """
    Rule-based routing + retrieval + prompt construction.
    Returns either {abstain: True, result: dict} or {abstain: False, messages, results, effective_query_type, routed_key}.
    """
    summary, recent_messages = _extract_chat_history(chat_history)
    conversation_context = _format_conversation_context(summary, recent_messages)
    retrieval_question = _build_retrieval_question(question, conversation_context)

    query_type = classify_query(retrieval_question)
    if query_type == "author" and is_author_directory_query(retrieval_question):
        query_type = "author_directory"
        _log("[Router] Promoted author → author_directory (full list wording)")
    elif query_type == "author" and is_author_stats_query(retrieval_question):
        query_type = "author_stats"
        _log("[Router] Promoted author → author_stats (aggregate wording)")
    _log(f"[Router] Query type: {query_type}")

    routed_key = None
    effective_query_type = query_type
    if query_type == "gene":
        gene = extract_gene_from_question(retrieval_question, hgnc_lookup)
        if gene:
            routed_key = gene
            _log(f"[Graph] Gene route for '{gene}'")
        else:
            routed_key = "semantic_fallback"
            effective_query_type = "semantic"
            _log("[Graph] Gene route fell back to semantic retrieval")
    elif query_type == "author":
        author = extract_author_from_question(retrieval_question) or "Devreotes"
        routed_key = author
        _log(f"[Graph] Author route for '{author}'")
    elif query_type == "author_stats":
        routed_key = "author_stats"
        _log("[Graph] Author publication stats route")
    elif query_type == "author_directory":
        routed_key = "author_directory"
        _log("[Graph] Author directory route")
    elif query_type == "themes":
        routed_key = "themes"
        _log("[Graph] Themes route")
    elif query_type == "corpus_meta":
        routed_key = "corpus_meta"
        _log("[Graph] Corpus meta (counts) route")
    else:
        routed_key = "semantic"
        _log("[Vector] Semantic route")

    retrieved = _retrieve_or_abstain(
        retrieval_question,
        effective_query_type,
        routed_key
        if query_type not in ("themes", "author_stats", "author_directory", "corpus_meta")
        else None,
    )
    results = retrieved["results"]
    themes_meta = retrieved.get("themes_meta")
    corpus_meta_addon = retrieved.get("corpus_meta_addon")
    author_directory_meta = retrieved.get("author_directory_meta")

    if retrieved["abstained"]:
        reason = retrieved.get("abstain_reason")
        best_score = retrieved.get("best_score")
        if reason == "below_min_score":
            answer = (
                f"The best retrieved chunk score ({best_score:.4f}) is below the configured minimum "
                f"({RAG_MIN_SCORE:.4f}), so I cannot answer confidently from this corpus alone."
            )
        elif reason == "no_theme_data":
            answer = "No gene mention statistics were found in the corpus yet."
        elif reason == "no_author_stats":
            answer = (
                "No authors with multiple papers were found in the graph yet "
                "(or the minimum paper threshold filtered everyone out)."
            )
        elif reason == "no_author_directory":
            answer = "No author nodes with :AUTHORED links were found in the graph yet."
        else:
            answer = "No relevant passages were retrieved from the corpus."
        sources, preview = _build_sources_and_preview(results, effective_query_type)
        return {
            "abstain": True,
            "result": {
                "answer": answer,
                "query_type": effective_query_type,
                "query_type_label": _query_type_label(effective_query_type),
                "routed_key": routed_key,
                "results_count": len(results),
                "sources": sources,
                "retrieval_preview": preview,
                "abstained": True,
                "abstain_reason": reason,
            },
        }

    context_prefix = ""
    if corpus_meta_addon and effective_query_type in ("author_stats", "author_directory"):
        context_prefix = _corpus_wide_addon_block(corpus_meta_addon) + "\n\n---\n\n"
    context = context_prefix + build_context(results, effective_query_type)
    conversation_prefix = (
        "Conversation context (for reference resolution only):\n"
        f"{conversation_context}\n\n"
        if conversation_context
        else ""
    )

    if effective_query_type == "themes":
        user_block = (
            "Numbered gene mention statistics derived from the graph:\n"
            "---\n"
            f"{context}\n"
            "---\n\n"
            f"{conversation_prefix}"
            f"Question: {question}\n\n"
            "Answer only using the statistics above. Cite each statistic you rely on as [n]. "
            "When the question calls for interpretation, elaborate carefully while staying tied to those counts. "
            "Do not invent qualitative research themes that are not supported by these counts."
        )
        dline = _themes_disclosure_prompt(themes_meta)
        if dline:
            user_block += "\n\n" + dline
    elif effective_query_type == "author_stats":
        corpus_note = ""
        if corpus_meta_addon:
            corpus_note = (
                "The [C1]–[C6] block (if present) is corpus-wide; bulleted author lines are per-author counts only. "
                "Use [C1] for total distinct papers in the graph when answering that part. "
            )
        user_block = (
            "Author–publication statistics from the graph (:Author)-[:AUTHORED]->(:Paper):\n"
            "---\n"
            f"{context}\n"
            "---\n\n"
            f"{conversation_prefix}"
            f"Question: {question}\n\n"
            f"{corpus_note}"
            "Answer only using the sections above. Refer to authors by name; do not use [An] citation tags. "
            "When helpful, give a thorough answer (grouping, trends, or notable counts) without exceeding what the data show. "
            "Do not treat the first author line as the total number of papers in the corpus. "
            "If the question asks who appears on multiple papers, list authors with paper_count ≥ 2."
        )
    elif effective_query_type == "author_directory":
        ddir = _author_directory_disclosure_prompt(author_directory_meta)
        corpus_note = ""
        if corpus_meta_addon:
            corpus_note = (
                "Use [C1] for total distinct :Paper nodes when the user asks how many papers are in the corpus. "
                "Bulleted author lines are each author’s own paper count, not the corpus total. "
            )
        user_block = (
            "Author directory from the graph (per-author distinct paper counts):\n"
            "---\n"
            f"{context}\n"
            "---\n\n"
            f"{conversation_prefix}"
            f"Question: {question}\n\n"
            f"{corpus_note}"
            "Answer only using the sections above. Refer to authors by name; do not use [An] citation tags. "
            "When helpful, elaborate on patterns in the directory (e.g. high-count authors) while staying factual. "
            "If both corpus totals and the author list appear, use [C1]–[C6] only for corpus-wide figures."
        )
        if ddir:
            user_block += "\n\n" + ddir
    elif effective_query_type == "corpus_meta":
        user_block = (
            "Corpus statistics (exact graph counts for the full indexed corpus):\n"
            "---\n"
            f"{context}\n"
            "---\n\n"
            f"{conversation_prefix}"
            f"Question: {question}\n\n"
            "Answer only using the numbered lines above. Cite each figure you use as [n]. "
            "If the user asked only for one total (e.g. papers), give that number clearly and you may explain related counts in context. "
            "For broader questions, relate the figures explicitly to what was asked."
        )
    else:
        user_block = (
            "Numbered passages from Prof. Devreotes' papers:\n"
            "---\n"
            f"{context}\n"
            "---\n\n"
            f"{conversation_prefix}"
            f"Question: {question}\n\n"
            "Answer only from the passages above. Cite supporting passages as [n]. "
            "For multi-part questions, address each part in turn with the relevant citations."
        )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_block),
    ]
    out = {
        "abstain": False,
        "messages": messages,
        "results": results,
        "effective_query_type": effective_query_type,
        "routed_key": routed_key,
    }
    if themes_meta is not None:
        out["themes_meta"] = themes_meta
    if author_directory_meta is not None:
        out["author_directory_meta"] = author_directory_meta
    return out


def _finalize_agent_state_after_evidence(
    question: str,
    chat_history,
    conversation_prefix: str,
    agent_plan_dict: dict | None,
    ev: dict,
):
    tool_calls_log = ev["tool_calls_log"]
    themes_meta = ev.get("themes_meta")
    extras = {"tool_calls_log": tool_calls_log}
    if agent_plan_dict is not None:
        extras["agent_plan"] = agent_plan_dict
    rl = ev.get("reasoning_log")
    if rl:
        extras["reasoning_log"] = rl

    if not ev["used_tools"]:
        _log("[Agent] No tool calls; falling back to router")
        return _prepare_generation_router(question, chat_history=chat_history)

    themes = ev["themes"] if ev["themes"] else None
    author_stats = ev.get("author_stats") if ev.get("author_stats") else None
    author_directory = ev.get("author_directory") if ev.get("author_directory") else None
    author_dir_meta = ev.get("author_directory_meta")
    corpus_meta_list = ev.get("corpus_meta") if ev.get("corpus_meta") else None
    merged = _merge_raw_chunks(ev["raw_chunks"])
    routed_key = "agent"

    def abstain_payload(answer: str, reason: str, results: list, qtype: str):
        kind = (
            "themes"
            if qtype == "themes"
            else "author_stats"
            if qtype == "author_stats"
            else "author_directory"
            if qtype == "author_directory"
            else "corpus_meta"
            if qtype == "corpus_meta"
            else "semantic"
        )
        sources, preview = _build_sources_and_preview(results, kind)
        return {
            "abstain": True,
            "result": {
                "answer": answer,
                "query_type": qtype,
                "query_type_label": _query_type_label(qtype),
                "routed_key": routed_key,
                "results_count": len(results),
                "sources": sources,
                "retrieval_preview": preview,
                "abstained": True,
                "abstain_reason": reason,
                **extras,
            },
        }

    if not merged and not themes and not author_stats and not corpus_meta_list and not author_directory:
        return abstain_payload(
            "No relevant passages were retrieved from the corpus.",
            "no_chunks",
            [],
            "agent",
        )

    if not merged:
        cm = corpus_meta_list
        has_cm = bool(cm)
        has_th = bool(themes)
        has_as = bool(author_stats)
        has_ad = bool(author_directory)
        corpus_use_c = has_cm and bool(cm and isinstance(cm[0], dict)) and (has_th or has_as or has_ad)

        parts: list[str] = []
        if has_cm and cm and isinstance(cm[0], dict):
            corpus_block = (
                _corpus_wide_addon_block(cm[0]) if corpus_use_c else build_context(cm, "corpus_meta")
            )
            parts.append("=== Corpus graph counts ===\n" + corpus_block)
        if has_th:
            parts.append("=== Gene mention statistics ===\n" + _themes_context_with_s_labels(themes))
        if has_as:
            parts.append(
                "=== Author publication counts ===\n" + build_context(author_stats, "author_stats")
            )
        if has_ad:
            parts.append(
                "=== Full author bibliography ===\n" + build_context(author_directory, "author_directory")
            )

        cite_bits: list[str] = []
        if has_cm:
            cite_bits.append(
                "corpus-wide totals as [C1]–[C6]" if corpus_use_c else "corpus inventory as [1]–[6]"
            )
        if has_th:
            cite_bits.append("gene statistics as [S1], [S2], …")
        if has_as or has_ad:
            cite_bits.append(
                "authors by name in the author sections (no bracket tags for author lines; per-author counts, not corpus totals)"
            )
        cite_line = (
            "Cite " + "; ".join(cite_bits) + ". Do not treat the first author row as total corpus papers."
            if cite_bits
            else ""
        )

        user_block = (
            "Graph-derived statistics (answer only from the sections below):\n\n"
            + "\n\n".join(parts)
            + f"\n\n{conversation_prefix}"
            f"Question: {question}\n\n"
            f"{cite_line} "
            "If the question has multiple parts, answer each part using the matching section. "
            "Explain thoroughly where the data allow; do not invent counts or themes not shown."
        )
        dline = _themes_disclosure_prompt(themes_meta) if has_th else ""
        if dline:
            user_block += "\n\n" + dline
        ddir = _author_directory_disclosure_prompt(author_dir_meta) if has_ad else ""
        if ddir:
            user_block += "\n\n" + ddir
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_block)]

        n_stat_kinds = sum(1 for x in (has_cm, has_th, has_as, has_ad) if x)
        if n_stat_kinds == 1 and has_cm:
            eqt = "corpus_meta"
            res_list = cm
        elif n_stat_kinds == 1 and has_th:
            eqt = "themes"
            res_list = themes
        elif n_stat_kinds == 1 and has_as:
            eqt = "author_stats"
            res_list = author_stats
        elif n_stat_kinds == 1 and has_ad:
            eqt = "author_directory"
            res_list = author_directory
        else:
            eqt = "agent"
            res_list = (
                (cm or [])
                + (themes or [])
                + (author_stats or [])
                + (author_directory or [])
            )

        out = {
            "abstain": False,
            "messages": messages,
            "results": res_list,
            "effective_query_type": eqt,
            "routed_key": routed_key,
            "tool_calls_log": tool_calls_log,
        }
        if themes_meta is not None:
            out["themes_meta"] = themes_meta
        if agent_plan_dict is not None:
            out["agent_plan"] = agent_plan_dict
        if ev.get("reasoning_log"):
            out["reasoning_log"] = ev["reasoning_log"]
        return out

    best_score = max(_result_score(r) for r in merged)
    if best_score < RAG_MIN_SCORE:
        sources, preview = _build_sources_and_preview(merged, "semantic")
        return {
            "abstain": True,
            "result": {
                "answer": (
                    f"The best retrieved chunk score ({best_score:.4f}) is below the configured minimum "
                    f"({RAG_MIN_SCORE:.4f}), so I cannot answer confidently from this corpus alone."
                ),
                "query_type": "agent",
                "query_type_label": _query_type_label("agent"),
                "routed_key": routed_key,
                "results_count": len(merged),
                "sources": sources,
                "retrieval_preview": preview,
                "abstained": True,
                "abstain_reason": "below_min_score",
                **extras,
            },
        }

    results = sorted(merged, key=_result_score, reverse=True)

    if themes or author_stats or author_directory or corpus_meta_list:
        extra_sections: list[str] = []
        if corpus_meta_list and isinstance(corpus_meta_list[0], dict):
            extra_sections.append(
                "=== Corpus graph counts ===\n" + _corpus_wide_addon_block(corpus_meta_list[0])
            )
        if themes:
            extra_sections.append(
                "=== Gene mention statistics ===\n" + _themes_context_with_s_labels(themes)
            )
        if author_stats:
            extra_sections.append(
                "=== Author publication counts ===\n" + build_context(author_stats, "author_stats")
            )
        if author_directory:
            extra_sections.append(
                "=== Full author bibliography ===\n"
                + build_context(author_directory, "author_directory")
            )
        chunk_ctx = build_context(results, "semantic")
        user_block = (
            "You may use multiple evidence sections below.\n"
            "- Cite corpus-wide graph totals as [C1]–[C6] when that section is present.\n"
            "- Cite gene statistics as [S1], [S2], … when present.\n"
            "- For author lists, use author names only (no [An] row tags; each line is one author’s paper count).\n"
            "- Cite paper passages as [1], [2], … only inside the passages section.\n"
            "- If the question has several parts, address each part with the right section and citations.\n\n"
            + "\n\n".join(extra_sections)
            + "\n\n=== Numbered passages from papers ===\n---\n"
            f"{chunk_ctx}\n---\n\n"
            f"{conversation_prefix}"
            f"Question: {question}\n\n"
            "Answer only from the sections above. Do not use outside knowledge. "
            "Give a detailed, well-structured answer when the evidence supports it; cite each section appropriately."
        )
        dline = _themes_disclosure_prompt(themes_meta) if themes else ""
        if dline:
            user_block += "\n\n" + dline
        ddir = _author_directory_disclosure_prompt(author_dir_meta) if author_directory else ""
        if ddir:
            user_block += "\n\n" + ddir
        effective_query_type = "agent"
    else:
        context = build_context(results, "semantic")
        user_block = (
            "Numbered passages from Prof. Devreotes' papers:\n---\n"
            f"{context}\n---\n\n"
            f"{conversation_prefix}"
            f"Question: {question}\n\n"
            "Answer only from the passages above. Cite supporting passages as [n]. "
            "For multi-part questions, address each part in turn with the relevant citations."
        )
        effective_query_type = "agent"

    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_block)]
    out = {
        "abstain": False,
        "messages": messages,
        "results": results,
        "effective_query_type": effective_query_type,
        "routed_key": routed_key,
        "tool_calls_log": tool_calls_log,
    }
    if themes_meta is not None:
        out["themes_meta"] = themes_meta
    if agent_plan_dict is not None:
        out["agent_plan"] = agent_plan_dict
    if ev.get("reasoning_log"):
        out["reasoning_log"] = ev["reasoning_log"]
    return out


def _prepare_generation_agent(question: str, chat_history=None):
    _log("[Agent] DEVREOTES_RAG_MODE=agent")
    head = _agent_gather_planner_context(question, chat_history)
    if head["kind"] == "clarify":
        return head["state"]
    ctx = head
    ev = run_evidence_agent(llm, ctx["retrieval_question"], plan_context=ctx["plan_context"])
    return _finalize_agent_state_after_evidence(
        question, chat_history, ctx["conversation_prefix"], ctx["agent_plan_dict"], ev
    )


def _iter_prepare_generation_router(question: str, chat_history=None):
    if _ui_progress_enabled():
        yield _progress_ndjson(
            {
                "type": "agent_status",
                "phase": "retrieving",
                "message": "Finding relevant passages in the corpus…",
            }
        )
    return _prepare_generation_router(question, chat_history=chat_history)


def _iter_prepare_generation_agent(question: str, chat_history=None):
    _log("[Agent] DEVREOTES_RAG_MODE=agent")
    ui = _ui_progress_enabled()
    if ui:
        if explicit_plan_enabled():
            yield _progress_ndjson(
                {
                    "type": "agent_status",
                    "phase": "planning",
                    "message": "Planning how to search the corpus…",
                }
            )
        else:
            yield _progress_ndjson(
                {
                    "type": "agent_status",
                    "phase": "retrieving",
                    "message": "Gathering evidence from the corpus…",
                }
            )
    head = _agent_gather_planner_context(question, chat_history)
    if head["kind"] == "clarify":
        if ui:
            yield _progress_ndjson(
                {
                    "type": "agent_status",
                    "phase": "clarify",
                    "message": "Need a bit more detail before searching…",
                }
            )
        return head["state"]
    ctx = head
    if ctx["agent_plan_dict"] is not None and ui:
        yield _progress_ndjson({"type": "agent_plan", "plan": _agent_plan_ui_payload(ctx["agent_plan_dict"])})
    if ui:
        yield _progress_ndjson(
            {
                "type": "agent_status",
                "phase": "retrieving",
                "message": "Searching the paper library and graph…",
            }
        )
    gen = iter_run_evidence_agent_outer(
        llm,
        ctx["retrieval_question"],
        plan_context=ctx["plan_context"],
        ui_progress=ui,
    )
    try:
        while True:
            yield next(gen)
    except StopIteration as exc:
        ev = exc.value
    if ui:
        yield _progress_ndjson(
            {
                "type": "agent_status",
                "phase": "retrieving",
                "message": "Preparing evidence for the answer…",
            }
        )
    return _finalize_agent_state_after_evidence(
        question, chat_history, ctx["conversation_prefix"], ctx["agent_plan_dict"], ev
    )


def _iter_prepare_generation(question: str, chat_history=None):
    sub = (
        _iter_prepare_generation_agent(question, chat_history)
        if _rag_mode() == "agent"
        else _iter_prepare_generation_router(question, chat_history)
    )
    try:
        while True:
            yield next(sub)
    except StopIteration as exc:
        return exc.value


def _prepare_generation(question: str, chat_history=None):
    it = _iter_prepare_generation(question, chat_history)
    try:
        while True:
            next(it)
    except StopIteration as exc:
        return exc.value


def _stream_chunk_text(chunk) -> str:
    c = getattr(chunk, "content", None)
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts: list[str] = []
        for p in c:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text", "")))
            elif isinstance(p, str):
                parts.append(p)
        return "".join(parts)
    return ""


def iter_answer_ndjson(question: str, chat_history=None):
    """Yield NDJSON lines (stdout only) for the streaming bridge: delta + finish."""
    prep = _iter_prepare_generation(question, chat_history=chat_history)
    try:
        while True:
            yield next(prep)
    except StopIteration as exc:
        state = exc.value

    if state.get("clarification_required"):
        res = state["result"]
        if _ui_progress_enabled():
            yield _progress_ndjson(
                {"type": "agent_status", "phase": "answering", "message": "Replying…"}
            )
        yield json.dumps({"type": "delta", "text": res["answer"]}) + "\n"
        yield json.dumps({"type": "finish", "result": res}) + "\n"
        return
    if state["abstain"]:
        res = state["result"]
        if _ui_progress_enabled():
            yield _progress_ndjson(
                {"type": "agent_status", "phase": "answering", "message": "Finishing up…"}
            )
        yield json.dumps({"type": "delta", "text": res["answer"]}) + "\n"
        yield json.dumps({"type": "finish", "result": res}) + "\n"
        return

    messages = state["messages"]
    results = state["results"]
    effective_query_type = state["effective_query_type"]
    routed_key = state["routed_key"]

    if _ui_progress_enabled():
        yield _progress_ndjson(
            {
                "type": "agent_status",
                "phase": "answering",
                "message": "Writing the answer from the evidence…",
            }
        )

    accumulated: list[str] = []
    for chunk in llm.stream(messages):
        piece = _stream_chunk_text(chunk)
        if piece:
            accumulated.append(piece)
            yield json.dumps({"type": "delta", "text": piece}) + "\n"

    answer = "".join(accumulated)
    preview_kind = "semantic" if effective_query_type == "agent" else effective_query_type
    sources, preview = _build_sources_and_preview(results, preview_kind)
    result = {
        "answer": answer,
        "query_type": effective_query_type,
        "query_type_label": _query_type_label(effective_query_type),
        "routed_key": routed_key,
        "results_count": len(results),
        "sources": sources,
        "retrieval_preview": preview,
        "abstained": False,
        "abstain_reason": None,
    }
    if state.get("tool_calls_log") is not None:
        result["tool_calls_log"] = state["tool_calls_log"]
    if state.get("themes_meta") is not None:
        result["themes_meta"] = state["themes_meta"]
    if state.get("agent_plan") is not None:
        result["agent_plan"] = state["agent_plan"]
    if state.get("reasoning_log") is not None:
        result["reasoning_log"] = state["reasoning_log"]
    yield json.dumps({"type": "finish", "result": result}) + "\n"


def answer_question_with_metadata(question: str, chat_history=None) -> dict:
    state = _prepare_generation(question, chat_history=chat_history)
    if state.get("clarification_required"):
        return state["result"]
    if state["abstain"]:
        return state["result"]

    response = llm.invoke(state["messages"])
    answer = response.content
    eqt = state["effective_query_type"]
    preview_kind = "semantic" if eqt == "agent" else eqt
    sources, preview = _build_sources_and_preview(state["results"], preview_kind)
    out = {
        "answer": answer,
        "query_type": eqt,
        "query_type_label": _query_type_label(eqt),
        "routed_key": state["routed_key"],
        "results_count": len(state["results"]),
        "sources": sources,
        "retrieval_preview": preview,
        "abstained": False,
        "abstain_reason": None,
    }
    if state.get("tool_calls_log") is not None:
        out["tool_calls_log"] = state["tool_calls_log"]
    if state.get("themes_meta") is not None:
        out["themes_meta"] = state["themes_meta"]
    if state.get("agent_plan") is not None:
        out["agent_plan"] = state["agent_plan"]
    if state.get("reasoning_log") is not None:
        out["reasoning_log"] = state["reasoning_log"]
    return out


def answer_question(question: str, chat_history=None) -> str:
    result = answer_question_with_metadata(question, chat_history=chat_history)
    return result["answer"]


def run_chatbot():
    print("=" * 60)
    print("GraphRAG Chatbot - Prof. Devreotes Lab")
    print("Type 'quit' to exit")
    print("=" * 60)

    while True:
        question = input("\nYou: ").strip()
        if question.lower() in {"quit", "exit", "q"}:
            print("Goodbye!")
            break
        if not question:
            continue

        print("\nSearching corpus...")
        answer = answer_question(question)
        print(f"\nAssistant: {answer}")


if __name__ == "__main__":
    run_chatbot()
