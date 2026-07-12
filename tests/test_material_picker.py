import unittest

from app.material_catalog import MaterialRecord, material_hashtags
from app.material_catalog import material_label
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
        "tags": (),
    }
    values.update(overrides)
    return MaterialRecord(**values)


class MaterialPickerTest(unittest.TestCase):
    def test_material_label_is_human_readable(self):
        item = record(filename="健管師/投影片2.JPG", topic="健康照護")

        self.assertEqual(
            material_label(item),
            "健管師/投影片2.JPG | 健康照護",
        )

    def test_material_label_adds_product_for_legacy_basenames(self):
        item = record(filename="投影片6.JPG", product="品牌/全產品", topic="企業願景")

        self.assertEqual(
            material_label(item),
            "品牌/全產品 | 投影片6.JPG | 企業願景",
        )

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

    def test_searches_explicit_vision_tags(self):
        item = record(tags=("高血壓", "血壓管理"))

        self.assertIn("#高血壓", material_hashtags(item))
        self.assertEqual(find_materials((item,), search="#高血壓"), (item,))


if __name__ == "__main__":
    unittest.main()
