import unittest

from app.line_profile import apply_line_profile, is_line_contact_eligible, parse_line_profiles


class LineProfileTest(unittest.TestCase):
    def test_parses_list_profiles_with_chinese_headers(self):
        profiles = parse_line_profiles(
            [
                ["Customer_ID", "Line暱稱", "Line風格"],
                ["P247068", "Dr. Wu LINE", "正式、簡短"],
            ]
        )

        self.assertEqual(profiles["P247068"].line_contact, "Dr. Wu LINE")
        self.assertEqual(profiles["P247068"].line_message_style, "正式、簡短")

    def test_applies_line_contact_as_query_when_present(self):
        profiles = parse_line_profiles(
            [
                ["customer_id", "line_contact", "line_message_style"],
                ["P100", "Clinic Contact", "friendly"],
            ]
        )

        query, contact, style = apply_line_profile(
            customer_id="P100",
            fallback_query="P100",
            profiles=profiles,
        )

        self.assertEqual(query, "Clinic Contact")
        self.assertEqual(contact, "Clinic Contact")
        self.assertEqual(style, "friendly")
        self.assertTrue(is_line_contact_eligible("P100", contact))


if __name__ == "__main__":
    unittest.main()
