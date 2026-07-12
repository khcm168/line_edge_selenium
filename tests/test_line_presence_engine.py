import os
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.line_presence_engine import (
    NOTIFY_LINE_QUERY,
    TRIGGER_TYPE,
    PresenceProfile,
    build_presence_drafts,
    choose_category,
    main,
    parse_presence_profiles,
)
from app.scenario_engine import ScenarioDraft


def settings(ai_enabled=False):
    return replace(Settings.from_env(require_google=False), ai_enabled=ai_enabled)


def profile(**overrides):
    values = {
        "enabled": True,
        "customer_id": "P100",
        "clinic_name": "Clinic A",
        "line_query": "P100",
        "line_contact": "Clinic A LINE",
        "interest_tags": ("sleep",),
        "cadence_days": 1,
        "preferred_send_time": "09:30",
        "last_category": "",
        "last_generated_date": "",
    }
    values.update(overrides)
    return PresenceProfile(**values)


def existing_presence(category="Sleep", presence_date="2026-06-29"):
    return ScenarioDraft(
        draft_id="existing1",
        created_at="2026-06-29T09:00:00+08:00",
        trigger_type=TRIGGER_TYPE,
        source_sheets=("LINE_Presence_Profiles",),
        source_refs={},
        customer_id="P100",
        customer_name="Clinic A",
        line_query="P100",
        product="",
        signal_summary="presence",
        draft_message="message",
        presence_date=presence_date,
        presence_category=category,
    )


class LinePresenceEngineTest(unittest.TestCase):
    def test_parses_enabled_presence_profiles(self):
        parsed = parse_presence_profiles(
            [
                {
                    "Enabled": "yes",
                    "Customer_ID": "P100",
                    "Clinic_Name": "Clinic A",
                    "Line_Query": "P100",
                    "Line_Contact": "Clinic A LINE",
                    "Interest_Tags": "sleep, hypertension",
                    "Cadence_Days": "3",
                    "Preferred_Send_Time": "09:30",
                }
            ]
        )

        self.assertEqual(len(parsed), 1)
        self.assertTrue(parsed[0].enabled)
        self.assertEqual(parsed[0].interest_tags, ("sleep", "hypertension"))
        self.assertEqual(parsed[0].cadence_days, 3)

    def test_category_rotation_avoids_previous_category(self):
        chosen = choose_category(
            profile(last_category="Sleep"),
            existing_drafts=(),
            run_date=date(2026, 6, 30),
        )

        self.assertNotEqual(chosen, "Sleep")

    def test_no_ai_generation_creates_safe_review_only_draft_and_notification(self):
        result = build_presence_drafts(
            (profile(),),
            existing_drafts=(),
            run_date=date(2026, 6, 30),
            settings=settings(ai_enabled=False),
        )

        self.assertEqual(len(result.drafts), 1)
        draft = result.drafts[0]
        self.assertEqual(draft.trigger_type, TRIGGER_TYPE)
        self.assertEqual(draft.status, "pending_review")
        self.assertEqual(draft.send_mode, "review")
        self.assertGreaterEqual(len(draft.draft_message), 120)
        self.assertLessEqual(len(draft.draft_message), 180)
        self.assertEqual(draft.presence_date, "2026-06-30")
        self.assertEqual(draft.preferred_send_time, "09:30")
        self.assertIn("#", draft.hashtag)
        self.assertTrue(draft.image_suggestion)
        self.assertIsNotNone(result.notification)
        self.assertEqual(result.notification.line_query, NOTIFY_LINE_QUERY)
        self.assertEqual(result.notification.send_mode, "review")

    def test_existing_same_day_draft_is_skipped(self):
        result = build_presence_drafts(
            (profile(),),
            existing_drafts=(existing_presence(presence_date="2026-06-30"),),
            run_date=date(2026, 6, 30),
            settings=settings(ai_enabled=False),
        )

        self.assertEqual(result.drafts, ())
        self.assertIsNone(result.notification)
        self.assertIn("already exists", result.events[0].result)

    def test_cli_source_json_dry_run(self):
        source = Path("data") / "fixtures" / "presence_sources_sample.json"
        with (
            patch.dict(os.environ, {"LINE_LOG_DIR": "data/test_tmp/presence_logs"}),
            patch("app.line_presence_engine.append_jsonl"),
        ):
            exit_code = main(["--date", "2026-06-30", "--source-json", str(source), "--no-write", "--no-ai"])

        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
