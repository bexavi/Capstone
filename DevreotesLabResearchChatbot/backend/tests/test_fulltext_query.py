"""Unit tests for Lucene full-text query building (no Neo4j)."""

import unittest

from backend.app.fulltext_query import build_fulltext_lucene_query


class FulltextQueryTests(unittest.TestCase):
    def test_half_life_myotubes_includes_keywords(self):
        q = (
            "What half-life do surface ACh receptors show in chick and rat myotubes, "
            "and under what culture conditions?"
        )
        ft = build_fulltext_lucene_query(q)
        self.assertIsNotNone(ft)
        self.assertIn(r"half\-life", ft)
        self.assertIn("myotubes", ft)
        self.assertIn("receptors", ft)
        self.assertIn("surface", ft)
        self.assertIn("chick", ft)
        self.assertIn("ach", ft)

    def test_empty_returns_none(self):
        self.assertIsNone(build_fulltext_lucene_query(""))
        self.assertIsNone(build_fulltext_lucene_query("   "))

    def test_only_stopwords_returns_none(self):
        self.assertIsNone(build_fulltext_lucene_query("What is the of and in to?"))


if __name__ == "__main__":
    unittest.main()
