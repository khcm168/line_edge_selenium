import unittest

from app.material_catalog import MaterialRecord, material_hashtags
from app.material_picker import find_materials


def record(**overrides):
    values = {
        "material_id": "MAT-001",
        "filename": "001.jpg",
        "sha256": "a" * 64,
        "duplicate_of": "",
        "product": "Sleep HA",
        "topic": "sleep quality",
        "audience": "clinic",
        "visual_summary": "simple overview",
        "internal_comment": "reviewed",
        "customer_caption": "Approved caption",
        "risk_level": "low",
        "safety_flags": (),
        "sendability": "sendable",
        "review_status": "approved",
        "test_result": "reviewed",
        "campaigns": ("daily followup",),
        "trigger_types": ("material_followup",),
    }
    values.update(overrides)
    return MaterialRecord(**values)


class MaterialPickerTest(unittest.TestCase):
    def test_hashtags_are_searchable_and_human_readable(self):
        item = record()

        self.assertIn("#Sleep_HA", material_hashtags(item))
        self.assertEqual(
            find_materials((item,), search="#Sleep_HA"),
            (item,),
        )

    def test_live_only_excludes_pending_review(self):
        approved = record()
        pending = record(
            material_id="MAT-002",
            filename="002.jpg",
            review_status="pending_review",
        )

        self.assertEqual(
            find_materials((approved, pending), live_only=True),
            (approved,),
        )

    def test_searches_topic_and_product(self):
        item = record()

        self.assertEqual(find_materials((item,), search="quality"), (item,))
        self.assertEqual(find_materials((item,), product="sleep"), (item,))


if __name__ == "__main__":
    unittest.main()
