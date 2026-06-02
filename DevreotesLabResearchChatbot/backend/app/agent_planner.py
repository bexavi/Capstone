"""
Optional structured planning step before the evidence agent (DEVREOTES_AGENT_EXPLICIT_PLAN).
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .agent_tools import DEVREOTES_RETRIEVAL_TOOLS

PLANNER_TOOL_NAMES: tuple[str, ...] = tuple(t.name for t in DEVREOTES_RETRIEVAL_TOOLS)


class AgentPlanModel(BaseModel):
    subtasks: list[str] = Field(
        default_factory=list,
        description="Plain-language steps to satisfy the question",
    )
    tool_sequence: list[str] = Field(
        default_factory=list,
        description="Retrieval tool names in suggested call order",
    )
    missing_parameters: list[str] = Field(
        default_factory=list,
        description="Ambiguous or missing slots (gene symbol, author name, etc.)",
    )
    needs_user_input: bool = Field(
        default=False,
        description="True only if the question cannot be executed without clarification",
    )
    clarification_prompt: str = Field(
        default="",
        description="Short message to show the user when needs_user_input is true",
    )
    notes: str = Field(
        default="",
        description="Hints for the retrieval agent",
    )


PLANNER_SYSTEM_TEMPLATE = """You are a planning module for a biomedical literature retrieval assistant.
The corpus is Prof. Devreotes' lab papers in Neo4j (chunks, genes, authors, graph counts).

Given the user question (and any conversation context in the same message), emit a structured plan.

Allowed retrieval tool names — use these exact strings in tool_sequence only:
{tool_list}

Guidelines:
- Set needs_user_input true only when the question is too ambiguous to choose sensible tools, or a critical
  detail is missing (which gene, which author, which paper) and cannot be inferred from the message or context.
- When needs_user_input is true, write clarification_prompt (1–3 sentences, friendly) for the user.
- tool_sequence lists tools the evidence step should call, in rough order. Leave empty if needs_user_input.
- subtasks are short plain-language steps (for logging / UI).
- notes: optional hints for the retrieval agent (constraints, disambiguation).
"""


def explicit_plan_enabled() -> bool:
    return os.getenv("DEVREOTES_AGENT_EXPLICIT_PLAN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def allow_clarification() -> bool:
    v = os.getenv("DEVREOTES_AGENT_ALLOW_CLARIFY", "true").strip().lower()
    return v not in ("0", "false", "no", "off")


def sanitize_tool_sequence(names: list[str], valid: set[str] | None = None) -> list[str]:
    v = valid or set(PLANNER_TOOL_NAMES)
    out: list[str] = []
    for n in names:
        if isinstance(n, str) and n in v and n not in out:
            out.append(n)
    return out


def format_plan_for_agent(plan: AgentPlanModel) -> str:
    lines: list[str] = []
    if plan.subtasks:
        lines.append("Subtasks:")
        for i, s in enumerate(plan.subtasks, 1):
            lines.append(f"  {i}. {s}")
    if plan.tool_sequence:
        lines.append("Suggested tools (order): " + ", ".join(plan.tool_sequence))
    if plan.missing_parameters:
        lines.append("Possibly missing: " + "; ".join(plan.missing_parameters))
    if plan.notes.strip():
        lines.append("Planner notes: " + plan.notes.strip())
    return "\n".join(lines) if lines else "(Planner produced no structured text.)"


def run_agent_planner(llm, retrieval_question: str) -> tuple[AgentPlanModel | None, str | None]:
    """
    When explicit planning is disabled, returns (None, None).
    On LLM/schema failure, returns (None, error_message).
    """
    if not explicit_plan_enabled():
        return None, None
    tool_list = ", ".join(PLANNER_TOOL_NAMES)
    system = PLANNER_SYSTEM_TEMPLATE.format(tool_list=tool_list)
    messages = [
        SystemMessage(content=system),
        HumanMessage(content=(retrieval_question or "").strip()),
    ]
    try:
        structured = llm.with_structured_output(AgentPlanModel)
        plan: AgentPlanModel = structured.invoke(messages)
    except Exception as exc:  # pragma: no cover - network/model dependent
        return None, str(exc)

    seq = sanitize_tool_sequence(list(plan.tool_sequence))
    plan = plan.model_copy(update={"tool_sequence": seq})
    return plan, None
