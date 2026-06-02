import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.chatbot import answer_question


demo_questions = [
    "Which genes are mentioned most often across Prof. Devreotes' papers?",
    "Which papers discuss the PTEN gene and its role in cell signaling?",
    "How has the lab's work on chemotaxis changed over time?",
    "Which collaborators appear most often in the lab's publications?",
    "Which papers should a newcomer to this research area read first?",
]

print("=" * 70)
print("DEMO TEST RUN")
print("=" * 70)

for i, question in enumerate(demo_questions, start=1):
    print(f"\n[Q{i}] {question}")
    print("-" * 50)
    answer = answer_question(question)
    print(answer[:500] + "..." if len(answer) > 500 else answer)
    print()
