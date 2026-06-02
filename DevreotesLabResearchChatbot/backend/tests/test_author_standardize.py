"""Tests for ORCID normalization and author ingest resolution."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.app.author_standardize import (
    author_records_for_ingest,
    load_author_alias_map,
    normalize_author_key,
)
from backend.app.crossref_metadata import normalize_orcid_url_or_id, orcid_from_structured_author_row


class OrcidNormalizeTests(unittest.TestCase):
    def test_url(self) -> None:
        self.assertEqual(
            normalize_orcid_url_or_id("https://orcid.org/0000-0002-1825-0097"),
            "0000-0002-1825-0097",
        )

    def test_raw_id(self) -> None:
        self.assertEqual(normalize_orcid_url_or_id("0000-0001-2345-6789"), "0000-0001-2345-6789")

    def test_row_helper(self) -> None:
        self.assertEqual(
            orcid_from_structured_author_row({"ORCID": "https://orcid.org/0000-0001-2345-6789"}),
            "0000-0001-2345-6789",
        )
        self.assertIsNone(orcid_from_structured_author_row({"given": "A"}))


class AuthorAliasTests(unittest.TestCase):
    def test_load_flat_and_wrapped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.json"
            p.write_text(json.dumps({"canonical_names": {"Foo Bar": "Foo Q. Bar"}}), encoding="utf-8")
            m = load_author_alias_map(p)
            self.assertEqual(m["foo bar"], "Foo Q. Bar")

    def test_records_alias_and_orcid_key(self) -> None:
        paper = {
            "paper_id": "010",
            "authors": ["peter devreotes", "Jane Doe"],
            "crossref": {
                "authors": [
                    {"given": "Peter", "family": "Devreotes", "orcid": "0000-0001-2345-6789"},
                    {"given": "Jane", "family": "Doe"},
                ]
            },
        }
        aliases = {"peter devreotes": "Peter N. Devreotes"}
        recs = author_records_for_ingest(paper, aliases)
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["author_key"], "orcid:0000-0001-2345-6789")
        self.assertEqual(recs[0]["name"], "Peter N. Devreotes")
        self.assertEqual(recs[0]["orcid"], "0000-0001-2345-6789")
        self.assertEqual(recs[1]["author_key"], "jane_doe")
        self.assertIsNone(recs[1]["orcid"])

    def test_normalize_author_key_slug(self) -> None:
        self.assertEqual(normalize_author_key("Foo Q. Bar"), "foo_q_bar")


if __name__ == "__main__":
    unittest.main()
