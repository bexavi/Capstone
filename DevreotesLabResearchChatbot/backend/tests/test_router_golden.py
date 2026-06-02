"""
Golden expectations for classify_query (keyword router).

Run from DevreotesLabResearchChatbot/:
  PYTHONPATH=. python -m unittest backend.tests.test_router_golden -v
"""

import json
import unittest
from pathlib import Path

from backend.app.paths import PROJECT_ROOT
from backend.app.router import classify_query, extract_gene_from_question, wants_corpus_inventory_addon

_HGNC_PATH = PROJECT_ROOT / "hgnc_lookup.json"
_HGNC = json.loads(_HGNC_PATH.read_text(encoding="utf-8")) if _HGNC_PATH.is_file() else {}


class RouterGoldenTests(unittest.TestCase):
    """Regression tests: change routing logic only with intentional golden updates."""

    def test_corpus_meta(self):
        for q in (
            "How many papers are in the corpus?",
            "How many papers does the corpus have?",
            "What is the size of the corpus?",
            "How many chunks are indexed?",
            "How many genes are in the graph?",
            "How many authors are in the database?",
            "total number of publications in the corpus",
        ):
            with self.subTest(q=q):
                self.assertEqual(
                    classify_query(q),
                    "corpus_meta",
                    msg=f"expected corpus_meta for: {q!r}",
                )

    def test_corpus_meta_not_gene_frequency(self):
        """Gene prevalence questions stay on themes, not raw graph counts."""
        for q in (
            "What genes are most mentioned in the corpus?",
            "Which kinases are most common across papers?",
            "Most frequent receptors in this corpus?",
        ):
            with self.subTest(q=q):
                self.assertEqual(classify_query(q), "themes")

    def test_author_stats(self):
        for q in (
            "Which authors appear on multiple papers?",
            "What researchers show up across several publications?",
        ):
            with self.subTest(q=q):
                self.assertEqual(classify_query(q), "author_stats")

    def test_author_directory(self):
        for q in (
            "Give me the full list of authors in the corpus",
            "List of all authors from the graph with their paper counts",
            "Every author who authored a paper in this database",
        ):
            with self.subTest(q=q):
                self.assertEqual(
                    classify_query(q),
                    "author_directory",
                    msg=f"expected author_directory for: {q!r}",
                )

    def test_combined_author_list_and_corpus_paper_count_addon(self):
        q = (
            "List all authors in the corpus and also tell me how many papers are in the corpus"
        )
        self.assertEqual(classify_query(q), "author_directory")
        self.assertTrue(
            wants_corpus_inventory_addon(q),
            msg="combined questions should attach corpus-wide paper totals beside the author table",
        )

    def test_author_route(self):
        for q in (
            "papers by Devreotes",
            "publications by Peter Devreotes",
            "What did Devreotes publish about chemotaxis?",
        ):
            with self.subTest(q=q):
                self.assertEqual(classify_query(q), "author")

    def test_gene_route(self):
        for q in (
            "What is the role of PTEN in chemotaxis?",
            "PI3K signaling in Dictyostelium",
        ):
            with self.subTest(q=q):
                self.assertEqual(classify_query(q), "gene")

    def test_themes_route(self):
        for q in (
            "What are the main research themes in these papers?",
            "Overview of the papers on chemotaxis",
            "Gene frequency across the corpus",
        ):
            with self.subTest(q=q):
                self.assertEqual(classify_query(q), "themes")

    def test_semantic_fallback(self):
        for q in (
            "Explain how cells sense chemical gradients",
            "What is chemotaxis?",
        ):
            with self.subTest(q=q):
                self.assertEqual(classify_query(q), "semantic")

    def test_paper_mention_not_corpus_inventory(self):
        """Do not treat 'how many papers mention X' as total corpus size."""
        q = "How many papers mention PTEN?"
        self.assertNotEqual(classify_query(q), "corpus_meta")

    @unittest.skipUnless(_HGNC, "hgnc_lookup.json not present")
    def test_extract_gene_skips_auxiliary_do(self):
        q = "What half-life do surface ACh receptors show in chick and rat myotubes?"
        self.assertNotEqual(extract_gene_from_question(q, _HGNC), "DO")

    @unittest.skipUnless(_HGNC, "hgnc_lookup.json not present")
    def test_extract_gene_finds_pten(self):
        q = "How does PTEN regulate cell polarity?"
        self.assertEqual(extract_gene_from_question(q, _HGNC), "PTEN")


if __name__ == "__main__":
    unittest.main()
