import unittest
from datetime import date

from app.config import Settings
from app.line_profile import LineProfile
from app.reminder_rules import ReminderRules
from app.sheet_source import parse_dy2_rows
from app.task_builder import MessageTask, build_reminder_tasks, build_shipping_notice_tasks, build_test_tasks, tasks_to_drafts


class FakeDraftProvider:
    def rewrite(self, draft):
        return {
            "message": f"{draft.line_contact}您好，{draft.product} 已依照{draft.line_message_style}風格提醒。",
            "risk_level": "low",
            "safety_flags": ["human_review_required"],
            "rationale": "used line profile",
        }


class TaskBuilderTest(unittest.TestCase):
    def test_reads_legacy_text_task_with_picture_defaults(self):
        task = MessageTask(
            action="send_message",
            query="P100",
            match_policy="unique_contains_friend",
            message="hello",
        )

        self.assertEqual(task.message_kind, "text")
        self.assertEqual(task.material_id, "")
        self.assertEqual(task.image_path, "")
        self.assertEqual(task.material_sha256, "")

    def test_test_tasks_are_limited_targets(self):
        tasks = build_test_tasks()

        self.assertEqual([task.query for task in tasks], ["洪啓明", "P103003", "001N1備份區", "Ya.ping"])
        self.assertEqual(tasks[0].match_policy, "unique_contains_friend")
        self.assertEqual(tasks[1].match_policy, "unique_contains_friend")
        self.assertTrue(tasks[2].allow_group)
        self.assertEqual(tasks[2].match_policy, "unique_contains_group")

    def test_shipping_tasks_match_by_customer_code(self):
        rows = parse_dy2_rows(
            [
                ["品名", "", "", "", "", "", "", "", "銷售日期"] + [""] * 20 + ["代號"],
                ["A+HA", "", "", "", "", "", "", "", "2026/5/29"] + [""] * 20 + ["P104062"],
            ]
        )

        tasks = build_shipping_notice_tasks(rows, today=date(2026, 5, 29))

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].query, "P104062")
        self.assertEqual(tasks[0].match_policy, "unique_contains_friend")
        self.assertFalse(tasks[0].allow_group)
        self.assertEqual(tasks[0].source["tab"], "DY2")
        self.assertEqual(tasks[0].reminder_type, "shipping")

    def test_shipping_tasks_keep_customer_code_query_when_profile_exists(self):
        rows = parse_dy2_rows(
            [
                ["product", "", "", "", "", "", "", "", "sales_date"] + [""] * 20 + ["customer_id"],
                ["A+HA", "", "", "", "", "", "", "", "2026/5/29"] + [""] * 20 + ["P104062"],
            ]
        )

        tasks = build_shipping_notice_tasks(
            rows,
            today=date(2026, 5, 29),
            line_profiles={
                "P104062": LineProfile(
                    customer_id="P104062",
                    line_contact="Dr. Wu LINE",
                    line_message_style="formal",
                )
            },
        )

        self.assertEqual(tasks[0].query, "P104062")
        self.assertEqual(tasks[0].customer_id, "P104062")
        self.assertEqual(tasks[0].line_contact, "Dr. Wu LINE")
        self.assertEqual(tasks[0].line_message_style, "formal")

    def test_shipping_tasks_can_use_ai_personalization_with_line_profile(self):
        rows = parse_dy2_rows(
            [
                ["product", "", "", "", "", "", "", "", "sales_date"] + [""] * 20 + ["customer_id"],
                ["A+HA", "", "", "", "", "", "", "", "2026/5/29"] + [""] * 20 + ["P104062"],
            ]
        )

        tasks = build_shipping_notice_tasks(
            rows,
            today=date(2026, 5, 29),
            line_profiles={
                "P104062": LineProfile(
                    customer_id="P104062",
                    line_contact="王醫師",
                    line_message_style="親切提醒",
                )
            },
            ai_settings=Settings.from_env(require_google=False),
            draft_provider=FakeDraftProvider(),
        )

        self.assertEqual(tasks[0].message, "王醫師您好，A+HA 已依照親切提醒風格提醒。")
        self.assertEqual(tasks[0].source["message_draft"]["result"], "ai_rewrite")
        self.assertEqual(tasks[0].source["message_draft"]["line_nickname"], "王醫師")
        self.assertEqual(tasks[0].source["message_draft"]["line_style"], "親切提醒")

    def test_converts_message_tasks_to_line_drafts(self):
        drafts = tasks_to_drafts(
            [
                MessageTask(
                    action="send_message",
                    query="Dr. Wu",
                    match_policy="unique_contains_friend",
                    message="Shipping notice text",
                    customer_id="P100",
                    line_contact="Dr. Wu",
                    line_message_style="friendly",
                    source={
                        "tab": "DY2",
                        "row": 12,
                        "product": "A+HA",
                        "message_draft": {
                            "result": "ai_rewrite",
                            "risk_level": "low",
                            "safety_flags": ["human_review_required"],
                            "rationale": "matched style",
                        },
                    },
                    reminder_type="shipping",
                    due_date="2026-06-08",
                    manual_required=True,
                )
            ],
            created_at="2026-06-08T10:00:00+08:00",
        )

        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].draft_id, "shipping:P100:2026-06-08:12")
        self.assertEqual(drafts[0].draft_message, "Shipping notice text")
        self.assertEqual(drafts[0].line_contact, "Dr. Wu")
        self.assertEqual(drafts[0].line_message_style, "friendly")
        self.assertEqual(drafts[0].risk_level, "low")
        self.assertEqual(drafts[0].result, "ai_rewrite: matched style")

    def test_template_fallback_keeps_line_contact_greeting(self):
        rows = parse_dy2_rows(
            [
                ["product", "", "", "", "", "", "", "", "sales_date"] + [""] * 20 + ["customer_id"],
                ["A+HA", "", "", "", "", "", "", "", "2026/5/29"] + [""] * 20 + ["P104062"],
            ]
        )

        settings = Settings.from_env(require_google=False)
        settings = settings.__class__(**{**settings.__dict__, "ai_enabled": False})
        tasks = build_shipping_notice_tasks(
            rows,
            today=date(2026, 5, 29),
            line_profiles={
                "P104062": LineProfile(
                    customer_id="P104062",
                    line_contact="Dr. Wu",
                    line_message_style="friendly",
                )
            },
            ai_settings=settings,
        )

        self.assertTrue(tasks[0].message.startswith("Dr. Wu您好，"))
        self.assertEqual(tasks[0].source["message_draft"]["result"], "template_fallback")

    def test_build_all_reminder_tasks_from_dy2_and_acts(self):
        dy2_rows = parse_dy2_rows(
            [
                ["品名", "", "", "", "", "", "", "", "銷售日期"] + [""] * 20 + ["代號"],
                ["A+HA", "", "", "", "", "", "", "", "2026/6/3"] + [""] * 20 + ["P104062"],
                ["Q10HA", "", "", "", "", "", "", "", "2026/5/27"] + [""] * 20 + ["P247010"],
                ["iMuso", "", "", "", "", "", "", "", "2026/5/4"] + [""] * 20 + ["S247008"],
            ]
        )
        acts_rows = [
            ["", "", "日期", "PSR", "醫療單位", "活動類型", "產品一", "產品二", "產品三", "講師", "餐飲費用", "樣品費", "講師費", "兩季銷售額"],
            ["", "", "2026/5/25", "N1", "聖光診所", "seminar", "iMuso", "A+HA", "Q10HA", "Kevin", "2,000", "1,800", "", "10,500"],
        ]
        from app.sheet_source import parse_acts_rows

        tasks = build_reminder_tasks(
            dy2_rows=dy2_rows,
            acts_rows=parse_acts_rows(acts_rows),
            today=date(2026, 6, 3),
            reminder_types=("shipping", "feedback", "activity_followup", "repurchase", "app"),
            rules=ReminderRules.load("missing_rules_for_test.json"),
        )

        types = [task.reminder_type for task in tasks]
        self.assertIn("shipping", types)
        self.assertIn("feedback", types)
        self.assertIn("activity_followup", types)
        self.assertIn("repurchase", types)
        self.assertIn("app", types)
        self.assertTrue(all(task.manual_required for task in tasks))


if __name__ == "__main__":
    unittest.main()
