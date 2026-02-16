import os
import sys
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:///./smartprocure_test_agent_runtime.db")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.append("smart-procure/backend")

from app.services.agent_runtime import ToolRegistry, get_tool_runtime_stats  # noqa: E402


class TestAgentRuntimeMetrics(unittest.TestCase):
    def test_tool_metrics_count_success_and_failure(self):
        before = get_tool_runtime_stats()

        tools = ToolRegistry()
        tools.register("ok", {"desc": "ok"}, lambda _: {"status": "ok"})

        def _raise(_: dict):
            raise RuntimeError("boom")

        tools.register("bad", {"desc": "bad"}, _raise)

        ok_out = tools.execute("ok", {})
        bad_out = tools.execute("bad", {})
        miss_out = tools.execute("missing", {})

        self.assertTrue(ok_out.get("ok"))
        self.assertFalse(bad_out.get("ok"))
        self.assertFalse(miss_out.get("ok"))

        after = get_tool_runtime_stats()
        self.assertEqual(after["total_calls"] - before["total_calls"], 3)
        self.assertEqual(after["success_calls"] - before["success_calls"], 1)
        self.assertEqual(after["failed_calls"] - before["failed_calls"], 2)


if __name__ == "__main__":
    unittest.main()

