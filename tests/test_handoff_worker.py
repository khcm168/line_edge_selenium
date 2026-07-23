import argparse
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.agent_lease import lease_path, write_lease
from app.handoff_worker import (
    classify_request_error,
    check_submit_send_leases,
    line_agent_lease_mode,
    read_worker_state,
    request_rate_settings,
    submit_request,
    worker_state_is_live,
    write_worker_state,
)
from app.rate_limiter import RateLimitSettings


class HandoffWorkerTest(unittest.TestCase):
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

    def lease(self, lock_key, owner_agent, scope):
        return {
            "lock_key": lock_key,
            "owner_project": "line_edge_selenium",
            "owner_agent": owner_agent,
            "run_id": "nightly-health-2026-07-15",
            "host": "Z13",
            "pid": 22164,
            "started_at": "2026-07-15T00:00:00+00:00",
            "expires_at": "2099-07-15T00:10:00+00:00",
            "scope": scope,
            "reentrant": False,
            "status": "held",
        }

    def fake_settings(self):
        return type("FakeSettings", (), {"task_dir": self.root / "tasks"})()

    def test_observation_request_never_implies_send(self):
        args = argparse.Namespace(
            stop=False,
            observe=True,
            tasks=None,
            test_targets=False,
            manual_approve=False,
            send=False,
            delay_min_seconds=None,
            delay_max_seconds=None,
            per_recipient_quota=None,
            daily_message_quota=None,
        )

        request_path = submit_request(args=args, inbox=self.root)
        request = json.loads(request_path.read_text(encoding="utf-8"))

        self.assertTrue(request["observe"])
        self.assertFalse(request["send"])
        self.assertEqual(request["tasks"], "")

    def test_line_agent_lease_mode_defaults_to_observe_only(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(line_agent_lease_mode(), "observe_only")

    def test_submit_send_lease_observe_only_warns_but_allows_missing_lease(self):
        settings = self.fake_settings()

        allowed = check_submit_send_leases(settings=settings, mode="observe_only")

        self.assertTrue(allowed)
        audits = list((self.root / "audit").glob("agent_lease_*.jsonl"))
        self.assertEqual(len(audits), 1)
        record = json.loads(audits[0].read_text(encoding="utf-8").strip())
        self.assertEqual(record["event"], "lease_checked")
        self.assertEqual(record["status"], "warn")

    def test_submit_send_lease_warn_block_preview_blocks_missing_lease(self):
        settings = self.fake_settings()

        allowed = check_submit_send_leases(settings=settings, mode="warn_block_preview")

        self.assertFalse(allowed)
        audits = list((self.root / "audit").glob("agent_lease_*.jsonl"))
        self.assertEqual(len(audits), 1)
        record = json.loads(audits[0].read_text(encoding="utf-8").strip())
        self.assertEqual(record["status"], "blocked")

    def test_submit_send_lease_enforce_live_allows_valid_leases(self):
        settings = self.fake_settings()
        lease_dir = self.root / "leases"
        write_lease(
            lease_path(lease_dir, "browser:line-primary"),
            self.lease("browser:line-primary", "arbiter", "browser"),
        )
        write_lease(
            lease_path(lease_dir, "delivery:line:hqming"),
            self.lease("delivery:line:hqming", "delivery", "message_delivery"),
        )

        allowed = check_submit_send_leases(settings=settings, mode="enforce_live")

        self.assertTrue(allowed)
        audits = list((self.root / "audit").glob("agent_lease_*.jsonl"))
        self.assertEqual(len(audits), 1)
        record = json.loads(audits[0].read_text(encoding="utf-8").strip())
        self.assertEqual(record["status"], "ok")

    def test_worker_state_heartbeat_reports_live(self):
        path = self.root / "worker_state.json"
        write_worker_state(path, status="idle")
        state = read_worker_state(path)

        self.assertTrue(worker_state_is_live(state))
        stale_now = (
            datetime.fromisoformat(str(state["heartbeat_at"]))
            + timedelta(seconds=181)
        )
        self.assertFalse(worker_state_is_live(state, now=stale_now))

    def test_worker_state_retries_transient_windows_file_lock(self):
        path = self.root / "worker_state.json"
        original_replace = Path.replace
        attempts = []

        def replace_with_one_lock(source, target):
            attempts.append(target)
            if len(attempts) == 1:
                raise PermissionError("temporary lock")
            return original_replace(source, target)

        with (
            patch.object(Path, "replace", autospec=True, side_effect=replace_with_one_lock),
            patch("app.handoff_worker.time.sleep") as sleep,
        ):
            write_worker_state(path, status="idle")

        self.assertEqual(len(attempts), 2)
        sleep.assert_called_once_with(0.05)
        self.assertEqual(read_worker_state(path)["status"], "idle")

    def test_request_scoped_spacing_and_quota(self):
        settings = request_rate_settings(
            {
                "delay_min_seconds": 180,
                "delay_max_seconds": 300,
                "per_recipient_quota": 3,
                "daily_message_quota": 20,
            },
            defaults=RateLimitSettings(),
        )

        self.assertEqual(settings.delay_min_seconds, 180)
        self.assertEqual(settings.delay_max_seconds, 300)
        self.assertEqual(settings.per_recipient_daily_quota, 3)

    def test_request_rejects_reversed_delay_range(self):
        with self.assertRaisesRegex(ValueError, "delay_max_seconds"):
            request_rate_settings(
                {
                    "delay_min_seconds": 300,
                    "delay_max_seconds": 180,
                },
                defaults=RateLimitSettings(),
            )

    def test_classify_request_error_flags_bom_json_decode(self):
        exc = json.JSONDecodeError(
            "Unexpected UTF-8 BOM (decode using utf-8-sig)",
            "\ufeff[]",
            0,
        )

        self.assertEqual(classify_request_error(exc), "task_encoding_invalid")


if __name__ == "__main__":
    unittest.main()

