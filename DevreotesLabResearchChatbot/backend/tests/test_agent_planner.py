import unittest

from backend.app.agent_planner import (
    AgentPlanModel,
    explicit_plan_enabled,
    format_plan_for_agent,
    sanitize_tool_sequence,
)


class TestAgentPlanner(unittest.TestCase):
    def test_sanitize_tool_sequence_dedupes_and_filters(self):
        valid = {"semantic_search", "corpus_graph_inventory"}
        self.assertEqual(
            sanitize_tool_sequence(
                ["semantic_search", "bogus", "semantic_search", "corpus_graph_inventory"],
                valid=valid,
            ),
            ["semantic_search", "corpus_graph_inventory"],
        )

    def test_format_plan_for_agent(self):
        p = AgentPlanModel(
            subtasks=["Find papers", "Summarize"],
            tool_sequence=["semantic_search"],
            missing_parameters=[],
            needs_user_input=False,
            clarification_prompt="",
            notes="Be careful",
        )
        text = format_plan_for_agent(p)
        self.assertIn("Find papers", text)
        self.assertIn("semantic_search", text)
        self.assertIn("Be careful", text)

    def test_explicit_plan_enabled_env(self):
        import os

        os.environ.pop("DEVREOTES_AGENT_EXPLICIT_PLAN", None)
        self.assertFalse(explicit_plan_enabled())
        os.environ["DEVREOTES_AGENT_EXPLICIT_PLAN"] = "true"
        try:
            self.assertTrue(explicit_plan_enabled())
        finally:
            os.environ.pop("DEVREOTES_AGENT_EXPLICIT_PLAN", None)


if __name__ == "__main__":
    unittest.main()
