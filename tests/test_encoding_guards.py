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


def cjk_count(text: str) -> int:
    return sum("\u4e00" <= char <= "\u9fff" for char in text)


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
                self.assertGreaterEqual(cjk_count(template), 4)
                self.assertNotIn("\ufffd", template)

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
                "\u8056\u5149\u8a3a\u6240",
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
        self.assertEqual(set(messages_by_type), {"shipping", "feedback", "activity_followup", "repurchase", "app"})
        for reminder_type, message in messages_by_type.items():
            with self.subTest(reminder_type=reminder_type):
                self.assertGreaterEqual(cjk_count(message), 4)
                self.assertNotIn("{", message)
                self.assertNotIn("}", message)
                self.assertNotIn("\ufffd", message)


if __name__ == "__main__":
    unittest.main()
