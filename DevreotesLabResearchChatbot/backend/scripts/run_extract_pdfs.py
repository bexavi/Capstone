import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.extract_pdfs import extract_one_pdf, extract_text_from_pdfs


if __name__ == "__main__":
    # Usage: python backend/scripts/run_extract_pdfs.py           # all papers
    #        python backend/scripts/run_extract_pdfs.py 139       # papers/139.pdf
    #        python backend/scripts/run_extract_pdfs.py papers/139.pdf
    if len(sys.argv) >= 2:
        extract_one_pdf(sys.argv[1])
    else:
        extract_text_from_pdfs()
