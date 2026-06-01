import json
import unittest
from uuid import uuid4
from pathlib import Path

from app.audit import append_jsonl, build_audit_record


class AuditTest(unittest.TestCase):
    def test_append_jsonl_record_shape(self):
        path = Path("data") / "test_tmp" / f"audit_{uuid4().hex}.jsonl"
        record = build_audit_record(
            action="send_message",
            status="preview_matched",
            query="洪啓明",
            policy="exact_friend",
            message="hello",
            source={"tab": "DY2", "row": 3033},
        )

        append_jsonl(path, record)
        parsed = json.loads(path.read_text(encoding="utf-8").strip())

        self.assertEqual(parsed["action"], "send_message")
        self.assertEqual(parsed["status"], "preview_matched")
        self.assertEqual(parsed["source"]["row"], 3033)
        self.assertIn("timestamp", parsed)


if __name__ == "__main__":
    unittest.main()
