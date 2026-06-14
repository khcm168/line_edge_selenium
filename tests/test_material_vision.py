import unittest

from app.material_vision import parse_vision_analysis


class MaterialVisionTest(unittest.TestCase):
    def test_parses_json_and_normalizes_tags_and_flags(self):
        result = parse_vision_analysis(
            """
            {
              "visual_summary": "血壓衛教圖表",
              "visible_text": "高血壓",
              "topic": "血壓管理",
              "audience": "一般成人",
              "tags": ["#高血壓", "血壓管理", "高血壓"],
              "risk_level": "medium",
              "safety_flags": ["medical_overclaim_risk", "unknown"],
              "risk_reasons": ["含療效文字"],
              "neutral_caption": "分享一張血壓管理參考圖，實際情況請依專業評估。"
            }
            """
        )

        self.assertEqual(result.tags, ("高血壓", "血壓管理"))
        self.assertEqual(result.safety_flags, ("medical_overclaim_risk",))
        self.assertEqual(result.risk_level, "medium")

    def test_requires_grounded_description_and_caption(self):
        with self.assertRaisesRegex(ValueError, "visual_summary"):
            parse_vision_analysis('{"topic":"血壓","neutral_caption":"參考"}')

    def test_splits_single_space_separated_tag_phrase(self):
        result = parse_vision_analysis(
            """
            {
              "visual_summary": "衛教封面",
              "topic": "健康管理",
              "tags": ["sales training healthcare"],
              "risk_level": "low",
              "neutral_caption": "分享一張健康管理參考圖。"
            }
            """
        )

        self.assertEqual(result.tags, ("sales", "training", "healthcare"))


if __name__ == "__main__":
    unittest.main()
