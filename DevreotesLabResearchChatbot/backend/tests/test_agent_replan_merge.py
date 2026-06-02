import unittest

from backend.app.agent_replan import replan_rounds_cap
from backend.app.agent_tools import (
    _final_evidence_from_merged,
    _merge_evidence_piece,
    compact_observation_summary,
)


class TestAgentReplanMerge(unittest.TestCase):
    def test_merge_accumulates_chunks_and_tools(self):
        merged = {
            "used_tools": False,
            "raw_chunks": [],
            "tool_calls_log": [],
            "reasoning_log": [],
            "themes": None,
            "author_stats": None,
            "author_directory": None,
            "author_directory_meta": {},
            "corpus_meta": None,
            "themes_meta": {},
        }
        p1 = {
            "used_tools": True,
            "raw_chunks": [{"chunk_id": "c1", "paper_id": "p1"}],
            "tool_calls_log": [{"name": "semantic_search", "args": {"query": "x"}}],
            "reasoning_log": None,
            "themes": None,
            "author_stats": None,
            "author_directory": None,
            "author_directory_meta": None,
            "corpus_meta": None,
            "themes_meta": {},
        }
        _merge_evidence_piece(merged, p1)
        p2 = {
            "used_tools": True,
            "raw_chunks": [{"chunk_id": "c2", "paper_id": "p2"}],
            "tool_calls_log": [{"name": "corpus_graph_inventory", "args": {}}],
            "reasoning_log": [{"kind": "think", "text": "need counts"}],
            "themes": None,
            "author_stats": None,
            "author_directory": None,
            "author_directory_meta": None,
            "corpus_meta": [{"paper_count": 5}],
            "themes_meta": {},
        }
        _merge_evidence_piece(merged, p2)
        out = _final_evidence_from_merged(merged)
        self.assertEqual(len(out["raw_chunks"]), 2)
        self.assertEqual(len(out["tool_calls_log"]), 2)
        self.assertEqual(len(out["reasoning_log"]), 1)
        self.assertIsNotNone(out["corpus_meta"])

    def test_compact_observation_summary(self):
        ev = {
            "tool_calls_log": [{"name": "a"}, {"name": "b"}],
            "raw_chunks": [{"paper_id": "x"}, {"paper_id": "y"}],
            "themes": [{"gene": "G"}],
        }
        s = compact_observation_summary(ev)
        self.assertIn("Tool calls so far", s)
        self.assertIn("Chunk rows accumulated: 2", s)

    def test_replan_rounds_cap_env(self):
        import os

        os.environ.pop("DEVREOTES_AGENT_REPLAN_ROUNDS", None)
        self.assertEqual(replan_rounds_cap(), 0)
        os.environ["DEVREOTES_AGENT_REPLAN_ROUNDS"] = "2"
        try:
            self.assertEqual(replan_rounds_cap(), 2)
        finally:
            os.environ.pop("DEVREOTES_AGENT_REPLAN_ROUNDS", None)


if __name__ == "__main__":
    unittest.main()
