import os
import sys
import json
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:///./smartprocure_test_llm.db")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.append("smart-procure/backend")

from app.core import llm  # noqa: E402


class TestLlmGateway(unittest.TestCase):
    def test_extract_first_json(self):
        text = "```json\n{\"action\":\"ASK\",\"content\":\"ok\"}\n```"
        out = llm._extract_first_json(text)
        self.assertEqual(out, "{\"action\":\"ASK\",\"content\":\"ok\"}")

    def test_call_llm_mock_when_no_api_key(self):
        old = llm.settings.API_KEY
        try:
            llm.settings.API_KEY = ""
            out = llm.call_llm("system", "第2行 100 含税")
            payload = json.loads(out)
            self.assertIn("action", payload)
        finally:
            llm.settings.API_KEY = old

    def test_sanitize_json_content(self):
        content = "random\n{\"action\":\"ASK\",\"content\":\"x\"}\ntext"
        normalized = llm._sanitize_json_content(content)
        self.assertIsNotNone(normalized)
        payload = json.loads(normalized)
        self.assertEqual(payload.get("action"), "ASK")

    def test_gateway_stats_shape(self):
        stats = llm.get_llm_gateway_stats()
        self.assertIn("total_requests", stats)
        self.assertIn("success_requests", stats)
        self.assertIn("fallback_requests", stats)
        self.assertIn("parse_failure_rate", stats)


if __name__ == "__main__":
    unittest.main()
