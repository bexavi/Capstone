import json
import os
import sys
from pathlib import Path


def _parse_stdin_payload(raw: str) -> tuple[str, dict | None]:
    """
    Returns (message, chat_history or None).
    Legacy: whole stdin is the user message (plain text).
    JSON: {"message": str, "summary"?: str|null, "messages"?: list|null}
    """
    text = (raw or "").strip()
    if not text:
        return "", None
    if not text.startswith("{"):
        return text, None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return text, None
    if not isinstance(obj, dict):
        return text, None
    msg = obj.get("message")
    if not isinstance(msg, str) or not msg.strip():
        return "", None
    summary = obj.get("summary")
    messages = obj.get("messages")
    chat_history = None
    if summary is not None or messages is not None:
        chat_history = {
            "summary": summary if isinstance(summary, str) else None,
            "messages": messages if isinstance(messages, list) else None,
        }
    return msg.strip(), chat_history


def main() -> int:
    raw_in = sys.stdin.read() or ""
    question, chat_history = _parse_stdin_payload(raw_in)
    if not question:
        err = json.dumps({"error": "Empty question"})
        print(err, file=sys.stderr, flush=True)
        print(err, flush=True)
        return 1

    # Allow override via env, default to parent project folder.
    devreotes_root = Path(
        os.getenv("DEVREOTES_ROOT", str(Path(__file__).resolve().parents[3]))
    ).resolve()
    # Keep retrieval stable on machines with constrained GPU memory.
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    os.chdir(devreotes_root)
    sys.path.insert(0, str(devreotes_root))
    backend_path = devreotes_root / "backend"
    sys.path.insert(0, str(backend_path))

    try:
        if os.getenv("DEVREOTES_STREAM", "").lower() in ("1", "true", "yes", "on"):
            from backend.app.chatbot import iter_answer_ndjson

            try:
                for line in iter_answer_ndjson(question, chat_history=chat_history):
                    sys.stdout.write(line)
                    sys.stdout.flush()
            except Exception as stream_exc:
                err = json.dumps({"error": str(stream_exc)})
                print(err, file=sys.stderr, flush=True)
                print(err, flush=True)
                return 2
            return 0

        from backend.app.chatbot import answer_question_with_metadata

        result = answer_question_with_metadata(question, chat_history=chat_history)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception as exc:  # pragma: no cover - runtime bridge safety
        err = json.dumps({"error": str(exc)})
        print(err, file=sys.stderr, flush=True)
        print(err, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
