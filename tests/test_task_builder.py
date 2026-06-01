import unittest
from datetime import date

from app.reminder_rules import ReminderRules
from app.sheet_source import parse_dy2_rows
from app.task_builder import build_reminder_tasks, build_shipping_notice_tasks, build_test_tasks


class TaskBuilderTest(unittest.TestCase):
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
