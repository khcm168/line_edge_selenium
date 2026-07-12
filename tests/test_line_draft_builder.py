import io
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app import line_draft_builder
from app.config import Settings
from app.scenario_engine import build_scenario_drafts


class FakeWorksheet:
    def __init__(self, values):
        self.values = values

    def get_all_values(self):
        return self.values


class FakeGateway:
    def __init__(self, sources, existing_draft_ids):
        self.sources = sources
        self.draft_sheet = FakeWorksheet([["Draft_ID"]] + [[draft_id] for draft_id in existing_draft_ids])
        self.appended_drafts = ()
        self.appended_log_events = ()

    def fetch_sources(self, tab_names):
        return {
            tab_name: self.sources[tab_name]
            for tab_name in tab_names
            if tab_name in self.sources
        }

    def _maybe_worksheet(self, title):
        if title == "LINE_Drafts":
            return self.draft_sheet
        return None

    def append_drafts(self, drafts):
        self.appended_drafts = tuple(drafts)
        return len(self.appended_drafts)

    def append_log_events(self, events):
        self.appended_log_events = tuple(events)
        return len(self.appended_log_events)


class LineDraftBuilderTest(unittest.TestCase):
    def test_existing_draft_ids_are_skipped_before_ai_rewrite(self):
        run_date = "2026-06-06"
        sources = {
            "adr": [
                ["customer_id", "customer_name", "created_date"],
                ["P104", "Clinic A", run_date],
                ["P105", "Clinic B", run_date],
            ]
        }
        generated = build_scenario_drafts(
            sources,
            today=date.fromisoformat(run_date),
            trigger_types=("new_customer",),
        ).drafts
        existing_id = generated[0].draft_id
        gateway = FakeGateway(sources, existing_draft_ids=(existing_id,))

        settings = replace(Settings.from_env(require_google=False), log_dir=Path("."))
        called_ids = []

        def fake_draft_with_ai(draft, *, settings):
            self.assertNotEqual(draft.draft_id, existing_id)
            called_ids.append(draft.draft_id)
            return draft.with_message(draft.draft_message, result="mock_ai")

        output = io.StringIO()
        with (
            patch.object(line_draft_builder.Settings, "from_env", return_value=settings),
            patch.object(line_draft_builder.SheetGateway, "from_settings", return_value=gateway),
            patch.object(line_draft_builder, "draft_with_ai", side_effect=fake_draft_with_ai),
            patch.object(line_draft_builder, "append_jsonl"),
            redirect_stdout(output),
        ):
            exit_code = line_draft_builder.main(["--date", run_date, "--types", "new_customer", "--no-write"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(called_ids, [generated[1].draft_id])
        self.assertEqual(gateway.appended_drafts, ())
        text = output.getvalue()
        self.assertIn("generated_draft_count=2", text)
        self.assertIn("existing_draft_skip_count=1", text)
        self.assertIn("new_draft_count=1", text)
        self.assertIn("ai_progress=0/1", text)
        self.assertIn("ai_progress=1/1", text)
        self.assertIn("draft_count=0", text)
        self.assertIn("log_count=0", text)
        self.assertIn("draft_sheet=LINE_Drafts", text)
        self.assertIn("sheets_written=false", text)

if __name__ == "__main__":
    unittest.main()
