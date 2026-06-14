import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.rate_limiter import MessageQuota, RandomDelay, RateLimitSettings
from app.task_builder import MessageTask


class RateLimiterTest(unittest.TestCase):
    def test_delay_refreshes_heartbeat_without_extending_selected_wait(self):
        heartbeat_calls = []
        monotonic_values = iter([0.0, 0.0, 30.0, 60.0, 90.0])
        delay = RandomDelay(
            RateLimitSettings(delay_min_seconds=90, delay_max_seconds=90)
        )

        with (
            patch("app.rate_limiter.time.monotonic", side_effect=monotonic_values),
            patch("app.rate_limiter.time.sleep") as sleep,
        ):
            waited = delay.wait(
                heartbeat=lambda: heartbeat_calls.append(True),
                heartbeat_interval_seconds=30,
            )

        self.assertEqual(waited, 90)
        self.assertEqual(sleep.call_count, 3)
        self.assertEqual(len(heartbeat_calls), 3)

    def test_quota_blocks_second_message_to_same_recipient(self):
        path = Path("data") / "test_tmp" / f"quota_{uuid4().hex}.json"
        quota = MessageQuota(
            path,
            RateLimitSettings(daily_message_quota=3, per_recipient_daily_quota=1),
        )
        task = MessageTask(
            action="send_message",
            query="洪啓明",
            match_policy="exact_friend",
            message="hello",
        )

        self.assertEqual(quota.check(task, day=date(2026, 6, 1))[0], True)
        quota.record(task, day=date(2026, 6, 1), status="sent")

        allowed, detail = quota.check(task, day=date(2026, 6, 1))

        self.assertFalse(allowed)
        self.assertIn("recipient quota", detail)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["days"]["2026-06-01"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
