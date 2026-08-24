import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.handoff_worker import reclaim_stale_owner, write_worker_owner


class HandoffWorkerOwnerTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / "test_tmp" / uuid4().hex
        self.root.mkdir(parents=True)
        self.owner_path = self.root / "worker_owner.json"
        self.state_path = self.root / "worker_state.json"
        self.profile_dir = self.root / "edge-profile"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_write_worker_owner_records_launch_source(self):
        with patch.dict("os.environ", {"LINE_WORKER_LAUNCH_SOURCE": "test-launcher"}, clear=False):
            write_worker_owner(self.owner_path)

        payload = json.loads(self.owner_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["created_by"], "app.handoff_worker")
        self.assertEqual(payload["launch_source"], "test-launcher")
        self.assertIn("command_line", payload)
        self.assertIn("cwd", payload)
        self.assertIn("argv", payload)

    def test_reclaim_stale_owner_clears_only_dead_worker(self):
        self.owner_path.write_text(
            json.dumps(
                {
                    "created_by": "app.handoff_worker",
                    "pid": 424242,
                }
            ),
            encoding="utf-8",
        )

        with (
            patch("app.handoff_worker.pid_is_running", return_value=False),
            patch("app.handoff_worker.worker_state_is_live", return_value=False),
            patch("app.handoff_worker.prepare_edge_profile_dir") as prepare,
        ):
            result = reclaim_stale_owner(
                owner_path=self.owner_path,
                state_path=self.state_path,
                profile_dir=self.profile_dir,
        )

        self.assertEqual(result["status"], "reclaimed")
        prepare.assert_called_once_with(self.profile_dir)
        self.assertIn("stale worker owner cleared", result["detail"])

    def test_reclaim_stale_owner_refuses_live_owner_pid(self):
        self.owner_path.write_text(
            json.dumps(
                {
                    "created_by": "app.handoff_worker",
                    "pid": 12345,
                }
            ),
            encoding="utf-8",
        )

        with patch("app.handoff_worker.pid_is_running", return_value=True):
            result = reclaim_stale_owner(
                owner_path=self.owner_path,
                state_path=self.state_path,
                profile_dir=self.profile_dir,
            )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("still running", result["detail"])
        self.assertTrue(self.owner_path.exists())

    def test_reclaim_stale_owner_clears_dead_state_without_owner_file(self):
        self.state_path.write_text(
            json.dumps(
                {
                    "pid": 424242,
                    "status": "error",
                    "heartbeat_at": "2026-06-29T22:30:30+00:00",
                }
            ),
            encoding="utf-8",
        )

        with (
            patch("app.handoff_worker.worker_state_is_live", return_value=False),
            patch.object(Path, "unlink", autospec=True) as unlink,
        ):
            result = reclaim_stale_owner(
                owner_path=self.owner_path,
                state_path=self.state_path,
                profile_dir=self.profile_dir,
            )

        self.assertEqual(result["status"], "reclaimed")
        unlink.assert_called_once_with(self.state_path)

    def test_reclaim_stale_owner_refuses_live_state_without_owner_file(self):
        self.state_path.write_text(
            json.dumps(
                {
                    "pid": 12345,
                    "status": "idle",
                    "heartbeat_at": "2026-06-29T22:30:30+00:00",
                }
            ),
            encoding="utf-8",
        )

        with (
            patch("app.handoff_worker.worker_state_is_live", return_value=True),
            patch.object(Path, "unlink", autospec=True) as unlink,
        ):
            result = reclaim_stale_owner(
                owner_path=self.owner_path,
                state_path=self.state_path,
                profile_dir=self.profile_dir,
            )

        self.assertEqual(result["status"], "blocked")
        unlink.assert_not_called()


if __name__ == "__main__":
    unittest.main()
