import shutil
import unittest
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from app.line_group_watcher import run_once
from app.response_loop import (
    ObservationLedger,
    ObservedMessage,
    RESPONSE_CLASSES,
    classify_response,
    record_screenshot_intake,
    response_draft_from_observation,
    schedule_follow_ups,
)


class ResponseLoopTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("data/test_tmp") / str(uuid.uuid4())
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_schedules_24_48_72_hours_and_7_days(self):
        records = schedule_follow_ups(
            draft_id="draft-1",
            message_id="message-1",
            recipient="001N1備份區",
            sent_at="2026-06-13T10:00:00+08:00",
        )

        self.assertEqual(
            [item.checkpoint for item in records],
            ["24h", "48h", "72h", "7d"],
        )
        self.assertEqual(
            [datetime.fromisoformat(item.due_at).day for item in records],
            [14, 15, 16, 20],
        )

    def test_supports_all_declared_response_classes(self):
        for response_class in RESPONSE_CLASSES:
            self.assertEqual(
                classify_response("", explicit_class=response_class),
                response_class,
            )

    def test_screenshot_intake_is_keyed_and_hashed(self):
        screenshot = self.root / "response.png"
        screenshot.write_bytes(b"png-evidence")
        ledger = self.root / "intake.jsonl"

        intake = record_screenshot_intake(
            ledger,
            draft_id="draft-1",
            message_id="message-1",
            screenshot_path=screenshot,
            response_text="可以，請給我資料",
            result="customer replied",
            next_action="prepare reviewed material",
            reviewer="tester",
        )

        self.assertEqual(intake.response_class, "material_request")
        self.assertEqual(len(intake.screenshot_sha256), 64)
        self.assertIn("draft-1", ledger.read_text(encoding="utf-8"))

    def test_watcher_filters_groups_and_deduplicates_hashes(self):
        ledger = ObservationLedger(self.root / "watcher.jsonl")
        allowed = ObservedMessage(
            "001N1備份區",
            "Tester",
            "可以，謝謝",
            "2026-06-13T10:00:00+08:00",
            "m1",
        )
        blocked = ObservedMessage(
            "Other Group",
            "Tester",
            "hello",
            "2026-06-13T10:00:00+08:00",
            "m2",
        )

        unseen = ledger.unseen(
            [allowed, blocked],
            allowed_groups=("001N1備份區",),
        )
        self.assertEqual(unseen, (allowed,))

        draft = response_draft_from_observation(allowed)
        ledger.record(
            allowed,
            evidence_snapshot=self.root / "evidence.json",
            response_class="positive",
            draft_id=draft.draft_id,
        )
        self.assertEqual(
            ledger.unseen([allowed], allowed_groups=("001N1備份區",)),
            (),
        )
        self.assertEqual(draft.status, "pending_review")
        self.assertEqual(draft.send_mode, "review")
        self.assertIn("no automatic reply", draft.result)

    def test_watcher_is_disabled_by_default_gate(self):
        settings = SimpleNamespace(
            response_watcher_enabled=False,
            response_watch_groups=("001N1備份區",),
        )

        with self.assertRaisesRegex(RuntimeError, "disabled"):
            run_once(
                client=None,
                gateway=None,
                settings=settings,
            )


if __name__ == "__main__":
    unittest.main()
