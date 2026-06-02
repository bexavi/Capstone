"""
Regression tests for PDF text sanitization and related metadata heuristics.

Run from DevreotesLabResearchChatbot/:
  PYTHONPATH=. python -m unittest backend.tests.test_extracted_sanitize -v
"""

import unittest

from backend.app.extracted_clean import (
    _is_byline_line,
    _try_interlibrary_article_line,
    metadata_title_is_junk,
    parse_byline_authors,
    sanitize_pdf_extracted_text,
    sanitize_stored_authors_list,
)


class SanitizePdfExtractedTextTests(unittest.TestCase):
    def test_g_protein_and_primes(self):
        raw = (
            "G\x01 in Dictyostelium and G\x02\x01 to the membrane; "
            "3\x01, 5\x01-cyclic AMP"
        )
        out = sanitize_pdf_extracted_text(raw)
        self.assertIn("Gα in", out)
        self.assertIn("Gβγ to", out)
        self.assertIn("3′, 5′-cyclic", out)

    def test_adobe_copyright_pua(self):
        self.assertIn("©2002", sanitize_pdf_extracted_text("Copyright \uf8e92002 by"))

    def test_strips_c0_controls(self):
        self.assertFalse(metadata_title_is_junk(sanitize_pdf_extracted_text("Hello\x01 world")))

    def test_letter_starved_still_junk(self):
        punct = " ! \" #$% \" & ' ( ) * + , - . / "
        self.assertTrue(metadata_title_is_junk(sanitize_pdf_extracted_text(punct * 5)))

    def test_oxford_comma_byline_parsed(self):
        self.assertEqual(
            parse_byline_authors("Ning Zhang, Yu Long, and Peter N. Devreotes*"),
            ["Ning Zhang", "Yu Long", "Peter N. Devreotes"],
        )


class SanitizeStoredAuthorsTests(unittest.TestCase):
    def test_drops_affiliation_and_fax(self):
        out, ch = sanitize_stored_authors_list(
            [
                "School of Medicine",
                "Fax: 207-581-2209",
                "Peter N. Devreotes",
            ]
        )
        self.assertTrue(ch)
        self.assertEqual(out, ["Peter N. Devreotes"])

    def test_splits_multi_comma_list(self):
        out, ch = sanitize_stored_authors_list(
            [
                "Sally H. Zigmond, Michael Joyce, Jane Borleis, Gary M. Bokoch",
            ]
        )
        self.assertTrue(ch)
        self.assertEqual(len(out), 4)

    def test_repair_devreotes_suffix_and_gross_apostrophe(self):
        out, ch = sanitize_stored_authors_list(
            ["Julian Gross'", "Peter N.Devreotes and"],
        )
        self.assertTrue(ch)
        self.assertEqual(out, ["Julian Gross", "Peter N. Devreotes"])


class InterlibraryCatalogTests(unittest.TestCase):
    def test_article_line_the_title(self):
        title, authors = _try_interlibrary_article_line(
            "Article: Insall, R., Borleis, J. and Devreotes, P.N.: The aimless RasGEF is required for x"
        )
        self.assertTrue(title.startswith("The aimless"))
        self.assertGreaterEqual(len(authors), 2)

    def test_article_line_cell_title_hyphen_initial(self):
        title, authors = _try_interlibrary_article_line(
            "Article: Theibert, A., Fontana, D., Wong, T-Y. and Devreotes, P.: Cell-cell interactions in the development of"
        )
        self.assertIn("Cell-cell", title)
        self.assertIn("T-Y. Wong", authors)

    def test_chemistry_headline_not_byline(self):
        self.assertFalse(
            _is_byline_line(
                "Leading-edge research: PtdIns(3,4,5)P3 and directed migration"
            )
        )


if __name__ == "__main__":
    unittest.main()
