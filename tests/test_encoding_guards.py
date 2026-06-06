import json
import unittest
from datetime import date
from pathlib import Path

from app.reminder_rules import DEFAULT_RULES, ReminderRules
from app.sheet_source import ActivityRow, ShipmentRow
from app.task_builder import build_reminder_tasks


TEXT_FILES_WITH_CHINESE_MESSAGES = (
    Path("app/reminder_rules.py"),
    Path("app/sheet_source.py"),
    Path("app/task_builder.py"),
    Path("data/reminder_rules.json"),
    Path("tests/test_sheet_source.py"),
    Path("tests/test_task_builder.py"),
)


class EncodingGuardTest(unittest.TestCase):
    def test_chinese_message_files_are_utf8_without_mojibake_markers(self):
        for path in TEXT_FILES_WITH_CHINESE_MESSAGES:
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("\ufffd", text)
                self.assertFalse(any(0xE000 <= ord(char) <= 0xF8FF for char in text))

    def test_checked_in_rules_match_readable_python_defaults(self):
        checked_in = json.loads(Path("data/reminder_rules.json").read_text(encoding="utf-8"))
        self.assertEqual(
            checked_in["reminders"]["shipping"]["template"],
            DEFAULT_RULES["reminders"]["shipping"]["template"],
        )
        for reminder_type, rule in DEFAULT_RULES["reminders"].items():
            with self.subTest(reminder_type=reminder_type):
                template = str(rule["template"])
                self.assertGreaterEqual(sum("\u4e00" <= char <= "\u9fff" for char in template), 4)
                self.assertNotIn("?", template)

    def test_default_dy2_and_acts_reminders_render_readable_messages(self):
        dy2_rows = [
            ShipmentRow("DY2", 2, "A+HA", date(2026, 6, 3), "P104062"),
            ShipmentRow("DY2", 3, "Q10HA", date(2026, 5, 27), "P247010"),
            ShipmentRow("DY2", 4, "iMuso", date(2026, 5, 4), "S247008"),
        ]
        acts_rows = [
            ActivityRow(
                "Acts",
                2,
                date(2026, 5, 25),
                "N1",
                "聖光診所",
                "seminar",
                ("iMuso", "A+HA", "Q10HA"),
                "Kevin",
                "2,000",
                "1,800",
                "",
                "10,500",
            )
        ]

        tasks = build_reminder_tasks(
            dy2_rows=dy2_rows,
            acts_rows=acts_rows,
            today=date(2026, 6, 3),
            reminder_types=("shipping", "feedback", "activity_followup", "repurchase", "app"),
            rules=ReminderRules(DEFAULT_RULES),
        )

        messages_by_type = {task.reminder_type: task.message for task in tasks}
        self.assertEqual(
            messages_by_type["shipping"],
            "A+HA產品預計三個工作天(2026-06-08)到貨，請留意",
        )
        self.assertEqual(messages_by_type["feedback"], "Q10HA使用後若有回饋或問題，請協助回覆，謝謝")
        self.assertEqual(
            messages_by_type["activity_followup"],
            "聖光診所seminar活動後續追蹤提醒，產品：iMuso、A+HA、Q10HA",
        )
        self.assertEqual(messages_by_type["repurchase"], "iMuso回購提醒，若需要補貨或安排後續服務，請回覆確認")
        self.assertEqual(messages_by_type["app"], "免費下載 高峰健康御守")


if __name__ == "__main__":
    unittest.main()
