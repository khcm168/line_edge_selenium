import json
import unittest
from pathlib import Path
from uuid import uuid4

from app.agent_audit import (
    AgentAuditError,
    append_agent_audit_event,
    build_agent_audit_event,
    validate_agent_audit_event,
)


class AgentAuditEventTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / "test_tmp" / uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        for path in sorted(self.root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        self.root.rmdir()

    def test_builds_schema_compatible_event(self):
        event = build_agent_audit_event(
            project="line_edge_selenium",
            agent="delivery",
            run_id="nightly-health-2026-07-15",
            event="delivery_blocked",
            status="blocked",
            scope="shared_runtime",
            reason_code="worker_not_live",
            detail_short="Worker was not live after one approved start attempt.",
            lock_key="delivery:line:hqming",
            ts="2026-07-15T00:00:00+00:00",
        )

        self.assertEqual(event["project"], "line_edge_selenium")
        self.assertEqual(event["lock_key"], "delivery:line:hqming")

    def test_rejects_unknown_event(self):
        with self.assertRaisesRegex(AgentAuditError, "event"):
            validate_agent_audit_event(
                {
                    "ts": "2026-07-15T00:00:00+00:00",
                    "host": "Z13",
                    "project": "line_edge_selenium",
                    "agent": "delivery",
                    "run_id": "nightly-health-2026-07-15",
                    "event": "sent_anyway",
                    "status": "blocked",
                    "scope": "shared_runtime",
                    "reason_code": "worker_not_live",
                    "detail_short": "Worker was not live.",
                }
            )

    def test_appends_jsonl_event(self):
        path = self.root / "agent_audit.jsonl"
        event = build_agent_audit_event(
            project="line_edge_selenium",
            agent="summary",
            run_id="nightly-health-2026-07-15",
            event="summary_emitted",
            status="ok",
            scope="project_local",
            reason_code="summary_ready",
            detail_short="Nightly summary artifact created.",
            ts="2026-07-15T00:00:00+00:00",
        )

        append_agent_audit_event(path, event)
        parsed = json.loads(path.read_text(encoding="utf-8").strip())

        self.assertEqual(parsed["event"], "summary_emitted")
        self.assertEqual(parsed["status"], "ok")


if __name__ == "__main__":
    unittest.main()
