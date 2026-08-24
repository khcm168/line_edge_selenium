import unittest
from dataclasses import replace

from app.approved_draft_sender import (
    can_continue_after_presend_failure,
    is_successful_send_status,
    loggable_skip_events,
    rate_limit_settings_for_profile,
    select_approved_drafts,
    skip_reason,
)
from app.reminder_rules import ReminderRules
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
        line_query="Clinic A LINE",
        line_contact="Clinic A LINE",
        line_message_style="warm",
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
        self.assertEqual(selection.approved[0].task.query, "Clinic A LINE")
        self.assertEqual(selection.approved[0].task.customer_id, "P100")
        self.assertEqual(selection.approved[0].task.line_contact, "Clinic A LINE")
        self.assertEqual(selection.approved[0].task.match_policy, "unique_contains_friend")
        self.assertEqual(len(selection.skipped), 4)

    def test_live_send_uses_line_contact_to_avoid_short_query_ambiguity(self):
        selection = select_approved_drafts(
            [
                DraftSheetRow(
                    2,
                    draft(line_query="Chao", line_contact="Chao Yi Clinic LINE"),
                    {},
                )
            ]
        )

        self.assertEqual(selection.approved[0].task.query, "Chao Yi Clinic LINE")
        self.assertEqual(selection.approved[0].task.source["line_contact"], "Chao Yi Clinic LINE")

    def test_routine_skips_are_not_logged(self):
        rows = [
            DraftSheetRow(2, draft(status="pending_review"), {}),
            DraftSheetRow(3, draft(draft_id="draft2", sent_at="2026-06-06T10:00:00+08:00"), {}),
            DraftSheetRow(4, draft(draft_id="draft3", risk_level="high"), {}),
        ]

        selection = select_approved_drafts(rows)

        self.assertEqual(
            [event.result for event in loggable_skip_events(selection.skipped)],
            ["high risk blocked"],
        )

    def test_allows_known_group_targets_only(self):
        blocked = draft(line_query="001N1備份區")
        allowed = draft(draft_id="draft2", line_query="001N1備份區")

        blocked = replace(blocked, line_contact=blocked.line_query)
        allowed = replace(allowed, line_contact=allowed.line_query)

        self.assertEqual(skip_reason(blocked, allowed_group_targets=()), "group target blocked")
        selection = select_approved_drafts(
            [DraftSheetRow(2, allowed, {})],
            allowed_group_targets=("001N1備份區",),
        )

        self.assertEqual(len(selection.approved), 1)
        self.assertTrue(selection.approved[0].task.allow_group)
        self.assertEqual(selection.approved[0].task.match_policy, "unique_contains_group")

    def test_blocks_rows_without_customer_query_even_when_approved(self):
        self.assertEqual(
            skip_reason(draft(line_query="")),
            "missing line query",
        )

    def test_blocks_privacy_and_overclaim_flags(self):
        self.assertEqual(
            skip_reason(draft(safety_flags=("patient_privacy_risk",))),
            "high risk blocked",
        )
        self.assertEqual(
            skip_reason(draft(safety_flags=("medical_overclaim_risk",))),
            "high risk blocked",
        )

    def test_image_drafts_require_catalog_identity_and_hash(self):
        self.assertEqual(
            skip_reason(draft(message_kind="image", draft_message="")),
            "missing material id",
        )
        self.assertEqual(
            skip_reason(
                draft(
                    message_kind="image_text",
                    material_id="MAT-001",
                    image_path="001.jpg",
                )
            ),
            "missing material hash",
        )
        self.assertEqual(
            skip_reason(
                draft(
                    message_kind="image_text",
                    material_id="MAT-001",
                    image_path="001.jpg",
                    material_sha256="a" * 64,
                )
            ),
            "",
        )

    def test_blocks_unresolved_message_placeholder(self):
        self.assertEqual(
            skip_reason(
                draft(
                    draft_message="您好，[LINE暱稱]，這張資料提供您參考。",
                )
            ),
            "unresolved message placeholder",
        )

    def test_can_select_one_exact_draft_id(self):
        selection = select_approved_drafts(
            [
                DraftSheetRow(2, draft(draft_id="older"), {}),
                DraftSheetRow(3, draft(draft_id="acceptance"), {}),
            ],
            draft_ids=("acceptance",),
        )

        self.assertEqual(
            [item.draft.draft_id for item in selection.approved],
            ["acceptance"],
        )

    def test_only_sent_status_counts_as_successful_live_send(self):
        self.assertTrue(is_successful_send_status("sent"))
        self.assertFalse(is_successful_send_status("ambiguous"))
        self.assertFalse(is_successful_send_status("no_match"))
        self.assertFalse(is_successful_send_status("composer_missing"))

    def test_vaccine_quota_profile_overrides_daily_cap_only(self):
        rules = ReminderRules(
            {
                "defaults": {
                    "daily_message_quota": 20,
                    "per_recipient_daily_quota": 1,
                    "delay_min_seconds": 45,
                    "delay_max_seconds": 120,
                },
                "quota_profiles": {
                    "vaccine": {
                        "daily_message_quota": 100,
                    }
                },
            }
        )

        settings = rate_limit_settings_for_profile(rules, "vaccine")

        self.assertEqual(settings.daily_message_quota, 100)
        self.assertEqual(settings.per_recipient_daily_quota, 1)
        self.assertEqual(settings.delay_min_seconds, 45)

    def test_presend_ui_failures_can_continue_but_uncertain_send_failures_stop(self):
        self.assertTrue(
            can_continue_after_presend_failure(
                RuntimeError("LINE profile page did not expose a visible chat button")
            )
        )
        self.assertTrue(
            can_continue_after_presend_failure(
                RuntimeError("LINE opened an unexpected chat after profile fallback")
            )
        )
        self.assertFalse(
            can_continue_after_presend_failure(
                RuntimeError("LINE image submission is uncertain after Enter")
            )
        )


if __name__ == "__main__":
    unittest.main()
