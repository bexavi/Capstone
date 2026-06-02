"""
Optional replan step after a batch of retrieval tools (DEVREOTES_AGENT_REPLAN_ROUNDS).
"""

from __future__ import annotations

import os
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field


class ReplanDecision(BaseModel):
    action: Literal["sufficient", "continue"] = Field(
        description='Use "sufficient" if current observations are enough to answer; '
        '"continue" only if a clear retrieval gap remains.'
    )
    guidance: str = Field(
        default="",
        description="Short instructions for the retrieval agent when action is continue.",
    )


REPLAN_SYSTEM = """You supervise a biomedical literature retrieval agent (Neo4j corpus of lab papers).

You receive:
1) The user's question.
2) A compact summary of tools already run and rough result sizes (not full text).

Decide:
- action=sufficient — stop further retrieval; the pipeline will draft an answer from what was gathered.
- action=continue — more tools should run; give concrete guidance (which angle: gene, author, semantic, corpus stats, etc.).

Be conservative: prefer "sufficient" if the question is likely answerable from typical retrieval or if repeated rounds would not help."""


def replan_rounds_cap() -> int:
    raw = int(os.getenv("DEVREOTES_AGENT_REPLAN_ROUNDS", "0"))
    return max(0, min(raw, 4))


def run_replan_decision(llm, user_question: str, observation_summary: str) -> ReplanDecision:
    structured = llm.with_structured_output(ReplanDecision)
    messages = [
        SystemMessage(content=REPLAN_SYSTEM),
        HumanMessage(
            content=(
                f"User question:\n{user_question.strip()}\n\n"
                f"Observations so far:\n{observation_summary.strip()}\n\n"
                "Return structured JSON only."
            )
        ),
    ]
    out: ReplanDecision = structured.invoke(messages)
    if out.action == "continue" and not (out.guidance or "").strip():
        return ReplanDecision(action="sufficient", guidance="")
    return out
