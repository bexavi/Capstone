#!/usr/bin/env python3
"""Fix venv launcher scripts that point at an old folder name (spaces vs DevreotesLabResearchChatbot)."""
from __future__ import annotations

import os

BAD = b"Devreotes Lab Research Chatbot"
GOOD = b"DevreotesLabResearchChatbot"


def main() -> None:
    root = os.path.join(os.path.dirname(__file__), "..", ".venv", "bin")
    root = os.path.normpath(root)
    fixed = 0
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if BAD not in data:
            continue
        with open(path, "wb") as f:
            f.write(data.replace(BAD, GOOD))
        fixed += 1
        print("fixed:", path)
    print("total:", fixed)


if __name__ == "__main__":
    main()
