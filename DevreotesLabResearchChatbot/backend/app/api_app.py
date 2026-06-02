"""
FastAPI HTTP surface for Devreotes GraphRAG — long-lived process (warm Neo4j driver + embeddings).

Run from project root:
  uvicorn backend.app.api_app:app --host 127.0.0.1 --port 8765
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .paths import load_project_dotenv

load_project_dotenv()


def _check_api_secret(x_devreotes_key: str | None) -> None:
    secret = os.getenv("DEVREOTES_API_SECRET", "").strip()
    if not secret:
        return
    if (x_devreotes_key or "").strip() != secret:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Devreotes-Key")


app = FastAPI(title="Devreotes GraphRAG API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health(
    x_devreotes_key: str | None = Header(None, alias="X-Devreotes-Key"),
) -> dict:
    """Liveness probe. Does not import retrieval/embeddings (keeps checks cheap)."""
    _check_api_secret(x_devreotes_key)
    return {"ok": True}


class ChatTurn(BaseModel):
    role: str
    content: str


class MessageBody(BaseModel):
    message: str = Field(..., min_length=1)
    # Optional conversational context for multi-turn support.
    # These fields are ignored by the backend if not provided.
    summary: Optional[str] = None
    messages: Optional[list[ChatTurn]] = None


@app.post("/chat/stream")
def chat_stream(
    body: MessageBody,
    x_devreotes_key: str | None = Header(None, alias="X-Devreotes-Key"),
) -> StreamingResponse:
    _check_api_secret(x_devreotes_key)
    from .chatbot import iter_answer_ndjson

    chat_history = None
    if body.summary is not None or body.messages is not None:
        chat_history = {
            "summary": body.summary,
            "messages": None
            if body.messages is None
            else [{"role": m.role, "content": m.content} for m in body.messages],
        }

    def ndjson_lines():
        for line in iter_answer_ndjson(body.message.strip(), chat_history=chat_history):
            if not line.endswith("\n"):
                yield line + "\n"
            else:
                yield line

    return StreamingResponse(
        ndjson_lines(),
        media_type="application/x-ndjson",
    )


@app.post("/chat")
def chat_sync(
    body: MessageBody,
    x_devreotes_key: str | None = Header(None, alias="X-Devreotes-Key"),
) -> dict:
    _check_api_secret(x_devreotes_key)
    from .chatbot import answer_question_with_metadata

    chat_history = None
    if body.summary is not None or body.messages is not None:
        chat_history = {
            "summary": body.summary,
            "messages": None
            if body.messages is None
            else [{"role": m.role, "content": m.content} for m in body.messages],
        }

    return answer_question_with_metadata(body.message.strip(), chat_history=chat_history)
