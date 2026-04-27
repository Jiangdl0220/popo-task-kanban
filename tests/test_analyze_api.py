import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


class AnalyzeHelpersTest(unittest.TestCase):
    def test_normalize_analyzed_candidates_list(self):
        raw = [
            {"title": "A", "description": "x", "priority": "high", "due_date": "2026-04-20"},
            {"title": "", "description": "skip"},
            {"name": "Alias title", "priority": "bogus"},
        ]
        out = app.normalize_analyzed_candidates(raw)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["title"], "A")
        self.assertEqual(out[0]["priority"], "high")
        self.assertEqual(out[1]["title"], "Alias title")
        self.assertEqual(out[1]["priority"], "medium")

    def test_normalize_wrapped_tasks_key(self):
        raw = {"tasks": [{"title": "T1"}]}
        out = app.normalize_analyzed_candidates(raw)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["title"], "T1")

    def test_analyze_rejects_oversized_text(self):
        client = app.app.test_client()
        huge = "x" * (app.ANALYZE_MAX_TEXT_CHARS + 1)
        r = client.post("/api/analyze", json={"text": huge})
        self.assertEqual(r.status_code, 400)
        self.assertIn("过长", r.get_json().get("error", ""))


if __name__ == "__main__":
    unittest.main()
