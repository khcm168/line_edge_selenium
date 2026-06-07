import unittest

from app.message_style import resolve_message_style


class MessageStyleTest(unittest.TestCase):
    def test_resolves_warm_brief_before_generic_brief(self):
        style = resolve_message_style("溫暖、簡短")

        self.assertEqual(style.code, "warm_brief")
        self.assertIn("warm", " ".join(style.rules).casefold())

    def test_resolves_known_customer_style_labels(self):
        self.assertEqual(resolve_message_style("正式、簡短").code, "formal_brief")
        self.assertEqual(resolve_message_style("親切提醒").code, "friendly_reminder")
        self.assertEqual(resolve_message_style("低壓力關心").code, "low_pressure_care")
        self.assertEqual(resolve_message_style("接續上次話題").code, "continue_topic")

    def test_unknown_style_uses_neutral_professional(self):
        self.assertEqual(resolve_message_style("something unusual").code, "neutral_professional")


if __name__ == "__main__":
    unittest.main()
