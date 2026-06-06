import unittest
from dataclasses import replace

from app.approved_draft_sender import select_approved_drafts, skip_reason
from app.scenario_engine import DRAFT_STATUS_APPROVED, SEND_MODE_LIVE, ScenarioDraft
from app.sheet_gateway import DraftSheetRow


def draft(**overrides):
    base = ScenarioDraft(
        draft_id="draft1",
        created_at="2026-06-06T09:00:00+08:00",
        trigger_type="new_customer",
        source_sheets=("adr",),
        source_refs={"tab": "adr", "row": 2},
        customer_id="P100",
        customer_name="Clinic A",
        line_query="P100",
        product="",
        signal_summary="new customer",
        draft_message="您好，這是一則已審核訊息。",
        status=DRAFT_STATUS_APPROVED,
        send_mode=SEND_MODE_LIVE,
    )
    return replace(base, **overrides)


class ApprovedDraftSenderTest(unittest.TestCase):
    def test_selects_only_approved_live_safe_rows(self):
        rows = [
            DraftSheetRow(2, draft(), {}),
            DraftSheetRow(3, draft(draft_id="draft2", status="pending_review"), {}),
            DraftSheetRow(4, draft(draft_id="draft3", risk_level="high"), {}),
            DraftSheetRow(5, draft(draft_id="draft4", draft_message=""), {}),
            DraftSheetRow(6, draft(draft_id="draft5", sent_at="2026-06-06T10:00:00+08:00"), {}),
        ]

        selection = select_approved_drafts(rows)

        self.assertEqual(len(selection.approved), 1)
        self.assertEqual(selection.approved[0].task.query, "P100")
        self.assertEqual(selection.approved[0].task.match_policy, "unique_contains_friend")
        self.assertEqual(len(selection.skipped), 4)

    def test_allows_known_group_targets_only(self):
        blocked = draft(line_query="001N1備份區")
        allowed = draft(draft_id="draft2", line_query="001N1備份區")

        self.assertEqual(skip_reason(blocked, allowed_group_targets=()), "group target blocked")
        selection = select_approved_drafts(
            [DraftSheetRow(2, allowed, {})],
            allowed_group_targets=("001N1備份區",),
        )

        self.assertEqual(len(selection.approved), 1)
        self.assertTrue(selection.approved[0].task.allow_group)
        self.assertEqual(selection.approved[0].task.match_policy, "unique_contains_group")

    def test_blocks_privacy_and_overclaim_flags(self):
        self.assertEqual(
            skip_reason(draft(safety_flags=("patient_privacy_risk",))),
            "high risk blocked",
        )
        self.assertEqual(
            skip_reason(draft(safety_flags=("medical_overclaim_risk",))),
            "high risk blocked",
        )


if __name__ == "__main__":
    unittest.main()
