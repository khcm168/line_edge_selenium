import unittest
from datetime import date

from app.scenario_engine import DRAFT_HEADERS, TRIGGER_TYPES, build_scenario_drafts, draft_from_row, draft_to_log_event, draft_to_row


class ScenarioEngineTest(unittest.TestCase):
    def test_builds_all_manual_trigger_types_from_available_signals(self):
        today = date(2026, 6, 6)
        sources = {
            "DY2": [
                ["product", "customer_name", "sales_date", "customer_id", "new_product_flag", "usage_education_needed", "price_change"],
                ["A+HA", "Clinic A", "2026-06-06", "P100", "Y", "Y", "Y"],
            ],
            "Bridge_Logic": [
                ["product", "customer_id", "interval_days"],
                ["Q10HA", "P101", "35"],
            ],
            "marketing": [
                ["event_name", "customer_id", "status"],
                ["Doctor Day", "P102", "approved"],
            ],
            "推薦": [
                ["customer_id", "referral_event"],
                ["P103", "referred colleague"],
            ],
            "adr": [
                ["customer_id", "created_date"],
                ["P104", "2026-06-06"],
            ],
            "LOST_Recovery": [
                ["product", "customer_id", "interval_days"],
                ["iMuso", "P105", "60"],
            ],
            "Line": [
                ["customer_id", "last_topic", "last_contact_date"],
                ["P106", "HA usage", ""],
                ["P107", "", "2026-05-01"],
            ],
            "Acts": [
                ["", "", "activity_date", "", "medical_unit", "", "product"],
                ["", "", "2026-06-01", "", "Clinic B", "", "A+HA"],
            ],
            "List": [
                ["customer_id", "Line暱稱", "Line風格"],
                ["P100", "Clinic A LINE", "正式、簡短"],
            ],
        }

        result = build_scenario_drafts(sources, today=today, max_per_type=1)

        generated = {draft.trigger_type for draft in result.drafts}
        self.assertEqual(generated, set(TRIGGER_TYPES))
        self.assertTrue(all(draft.status == "pending_review" for draft in result.drafts))
        self.assertTrue(all("human_review_required" in draft.safety_flags for draft in result.drafts))
        logistics = next(draft for draft in result.drafts if draft.customer_id == "P100")
        self.assertEqual(logistics.line_query, "P100")
        self.assertEqual(logistics.line_contact, "Clinic A LINE")
        self.assertEqual(logistics.line_message_style, "正式、簡短")

    def test_missing_required_signal_skips_without_guessing(self):
        result = build_scenario_drafts(
            {"DY2": [["unknown"], ["value"]]},
            today=date(2026, 6, 6),
            trigger_types=("logistics",),
        )

        self.assertEqual(result.drafts, ())
        self.assertEqual(result.events[0].draft_status, "skipped")
        self.assertIn("no matching signal", result.events[0].result)

    def test_draft_round_trips_through_sheet_row(self):
        result = build_scenario_drafts(
            {
                "adr": [
                    ["customer_id", "customer_name", "created_date"],
                    ["P104", "Clinic A", "2026-06-06"],
                ]
            },
            today=date(2026, 6, 6),
            trigger_types=("new_customer",),
        )
        draft = result.drafts[0]

        row = draft_to_row(draft)
        parsed = draft_from_row(dict(zip([
            "Draft_ID",
            "Created_At",
            "Trigger_Type",
            "Source_Sheets",
            "Source_Refs",
            "Customer_ID",
            "Customer_Name",
            "Line_Query",
            "Product",
            "Signal_Summary",
            "Draft_Message",
            "Risk_Level",
            "Safety_Flags",
            "Status",
            "Send_Mode",
            "Approved_By",
            "Approved_At",
            "Sent_At",
            "Result",
            "Error_Message",
        ], row)))

        self.assertEqual(parsed.draft_id, draft.draft_id)
        self.assertEqual(parsed.trigger_type, "new_customer")
        self.assertEqual(parsed.customer_id, "P104")

    def test_draft_round_trips_line_contact_fields(self):
        result = build_scenario_drafts(
            {
                "adr": [
                    ["customer_id", "customer_name", "created_date"],
                    ["P104", "Clinic A", "2026-06-06"],
                ],
                "List": [
                    ["customer_id", "line_contact", "line_message_style"],
                    ["P104", "Clinic A LINE", "warm"],
                ],
            },
            today=date(2026, 6, 6),
            trigger_types=("new_customer",),
        )
        draft = result.drafts[0]

        parsed = draft_from_row(dict(zip(DRAFT_HEADERS, draft_to_row(draft))))

        self.assertEqual(parsed.line_query, "P104")
        self.assertEqual(parsed.line_contact, "Clinic A LINE")
        self.assertEqual(parsed.line_message_style, "warm")

    def test_draft_round_trips_material_label(self):
        draft = build_scenario_drafts(
            {
                "adr": [
                    ["customer_id", "customer_name", "created_date"],
                    ["P104", "Clinic A", "2026-06-06"],
                ]
            },
            today=date(2026, 6, 6),
            trigger_types=("new_customer",),
        ).drafts[0]
        draft = draft.__class__(
            **{
                **draft.__dict__,
                "material_label": "健管師/投影片2.JPG | 健康照護",
            }
        )

        parsed = draft_from_row(dict(zip(DRAFT_HEADERS, draft_to_row(draft))))

        self.assertEqual(
            parsed.material_label,
            "健管師/投影片2.JPG | 健康照護",
        )

    def test_draft_to_log_event_uses_final_risk_and_result(self):
        result = build_scenario_drafts(
            {
                "adr": [
                    ["customer_id", "created_date"],
                    ["P104", "2026-06-06"],
                ]
            },
            today=date(2026, 6, 6),
            trigger_types=("new_customer",),
        )
        draft = result.drafts[0].with_message(
            result.drafts[0].draft_message,
            risk_level="high",
            result="ai_rewrite",
            error_message="",
        )

        event = draft_to_log_event(draft)

        self.assertEqual(event.message_risk_level, "high")
        self.assertEqual(event.result, "ai_rewrite")


if __name__ == "__main__":
    unittest.main()
