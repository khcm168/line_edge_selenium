import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from app.project_health import (
    append_line_attempt,
    build_gmail_payload,
    build_line_task,
    default_project_health_ledger,
    finalize_delivery_state,
    load_registry_validation,
    parse_orchestrator_output,
    should_retry_line_attempt,
    summarize_handoff_result,
)
from app.task_builder import read_tasks, write_tasks


class ProjectHealthTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / "test_tmp" / uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _registry_path(self) -> Path:
        path = self.root / "arm_webapp_registry.json"
        path.write_text(
            json.dumps(
                {
                    "ownerRepo": "psr-gas",
                    "releaseWorkflow": "tools/arm_webapp_release.py",
                    "projects": [
                        {"name": "psr-aios-v1"},
                        {"name": "ARM"},
                        {"name": "line_edge_selenium"},
                        {"name": "easyflow"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def test_registry_validation_requires_exact_four_projects(self):
        ok, projects, missing, unexpected = load_registry_validation(self._registry_path())

        self.assertTrue(ok)
        self.assertEqual(projects, ("psr-aios-v1", "ARM", "line_edge_selenium", "easyflow"))
        self.assertEqual(missing, ())
        self.assertEqual(unexpected, ())

    def test_parse_orchestrator_output_marks_red_on_http_error(self):
        summary = parse_orchestrator_output(
            taipei_day="2026-07-01",
            stdout_text=(
                "[OK] Live ARM Shared WebApp API 2.0.0 release 37\n"
                "[PASSED] psr-aios-v1: import endpoint doctor\n"
                "[PASSED] ARM: contract health\n"
                "[PASSED] line_edge_selenium: shared spreadsheet compatibility\n"
                "[PASSED] easyflow: shared spreadsheet compatibility\n"
                "[ERROR] WebApp audit-log request failed: HTTP Error 404: Not Found\n"
            ),
            stderr_text="",
            exit_code=1,
            registry_ok=True,
            registry_projects=("psr-aios-v1", "ARM", "line_edge_selenium", "easyflow"),
            missing_projects=(),
            unexpected_projects=(),
        )

        self.assertEqual(summary.summary_status, "red")
        self.assertIn("HTTP Error 404", summary.summary_reason)
        self.assertEqual(summary.webapp_release, "37")
        self.assertEqual(summary.projects[0].status, "passed")

    def test_parse_orchestrator_output_marks_projects_not_run_when_global_failure_happens_first(self):
        summary = parse_orchestrator_output(
            taipei_day="2026-07-07",
            stdout_text="[ERROR] WebApp health request failed: connection refused\n",
            stderr_text="",
            exit_code=1,
            registry_ok=True,
            registry_projects=("psr-aios-v1", "ARM", "line_edge_selenium", "easyflow"),
            missing_projects=(),
            unexpected_projects=(),
        )

        self.assertEqual(summary.summary_status, "red")
        self.assertEqual(
            [project.status for project in summary.projects],
            ["not_run", "not_run", "not_run", "not_run"],
        )
        self.assertTrue(all("before project probes ran" in project.detail for project in summary.projects))

    def test_parse_orchestrator_output_names_release_registry_mismatch(self):
        summary = parse_orchestrator_output(
            taipei_day="2026-07-12",
            stdout_text=(
                "[FAIL] health releaseVersion=44; expected 37\n"
                "[BLOCKED] Candidate endpoint contract did not match the registry.\n"
            ),
            stderr_text="",
            exit_code=1,
            registry_ok=True,
            registry_projects=("psr-aios-v1", "ARM", "line_edge_selenium", "easyflow"),
            missing_projects=(),
            unexpected_projects=(),
        )

        self.assertEqual(summary.summary_status, "red")
        self.assertEqual(summary.webapp_release, "44")
        self.assertIn("psr-gas canonical registry/deploy mismatch", summary.summary_reason)
        self.assertIn("live release 44 != registry 37", summary.summary_reason)

    def test_line_task_uses_exact_friend_and_roundtrips_query(self):
        summary = parse_orchestrator_output(
            taipei_day="2026-07-01",
            stdout_text="[OK] Live ARM Shared WebApp API 2.0.0 release 37\n",
            stderr_text="",
            exit_code=0,
            registry_ok=True,
            registry_projects=("psr-aios-v1", "ARM", "line_edge_selenium", "easyflow"),
            missing_projects=(),
            unexpected_projects=(),
        )
        task = build_line_task(summary, worker_live=True, worker_status="idle")
        path = self.root / "project_health_task.json"
        write_tasks(path, [task])

        tasks = read_tasks(path)

        self.assertEqual(tasks[0].query, "洪啓明")
        self.assertEqual(tasks[0].line_contact, "洪啓明")
        self.assertEqual(tasks[0].match_policy, "exact_friend")

    def test_gmail_payload_targets_self_account(self):
        summary = parse_orchestrator_output(
            taipei_day="2026-07-01",
            stdout_text="[OK] Live ARM Shared WebApp API 2.0.0 release 37\n",
            stderr_text="",
            exit_code=0,
            registry_ok=True,
            registry_projects=("psr-aios-v1", "ARM", "line_edge_selenium", "easyflow"),
            missing_projects=(),
            unexpected_projects=(),
        )

        payload = build_gmail_payload(summary, worker_live=True, worker_status="idle")

        self.assertEqual(payload["to"], "khcm168@gmail.com")
        self.assertIn("每日專案健康報告 2026-07-01", payload["subject"])

    def test_safe_retry_stops_after_second_attempt(self):
        summary = parse_orchestrator_output(
            taipei_day="2026-07-01",
            stdout_text="[OK] Live ARM Shared WebApp API 2.0.0 release 37\n",
            stderr_text="",
            exit_code=0,
            registry_ok=True,
            registry_projects=("psr-aios-v1", "ARM", "line_edge_selenium", "easyflow"),
            missing_projects=(),
            unexpected_projects=(),
        )
        ledger = default_project_health_ledger(
            summary,
            registry_path="registry.json",
            project_root="C:\\Dev\\psr-gas",
            gmail_payload=build_gmail_payload(summary, worker_live=True, worker_status="idle"),
        )

        append_line_attempt(
            ledger,
            attempt_number=1,
            request_path="req1.json",
            result_path="done1.json",
            audit_path="audit1.jsonl",
            summary={
                "final_status": "no_match",
                "final_phase": "match",
                "sent_count": 0,
                "sent": False,
                "can_safe_retry": True,
                "retry_reason": "no matching row",
            },
        )
        self.assertTrue(should_retry_line_attempt(ledger))

        append_line_attempt(
            ledger,
            attempt_number=2,
            request_path="req2.json",
            result_path="done2.json",
            audit_path="audit2.jsonl",
            summary={
                "final_status": "no_match",
                "final_phase": "match",
                "sent_count": 0,
                "sent": False,
                "can_safe_retry": True,
                "retry_reason": "no matching row",
            },
        )
        self.assertFalse(should_retry_line_attempt(ledger))
        self.assertEqual(ledger["line"]["status"], "retryable_failure")
        self.assertEqual(finalize_delivery_state(ledger), "delivery_failed")

    def test_summarize_handoff_result_uses_phase_and_sent_status(self):
        audit_path = self.root / "handoff.jsonl"
        audit_path.write_text(
            "\n".join(
                [
                    json.dumps({"status": "no_match", "phase": "match", "detail": "no matching row"}, ensure_ascii=False),
                    json.dumps({"status": "sent", "phase": "send", "detail": "sent via text"}, ensure_ascii=False),
                ]
            ),
            encoding="utf-8",
        )

        summary = summarize_handoff_result({"status": "ok", "audit": str(audit_path), "error": ""}, str(audit_path))

        self.assertEqual(summary["final_status"], "sent")
        self.assertEqual(summary["final_phase"], "send")
        self.assertTrue(summary["sent"])
        self.assertFalse(summary["can_safe_retry"])


if __name__ == "__main__":
    unittest.main()
