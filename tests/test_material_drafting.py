import unittest
from types import SimpleNamespace

from app.material_catalog import MaterialCatalog, MaterialRecord
from app.material_drafting import build_material_draft, choose_material


class FailingProvider:
    def rewrite(self, _draft):
        raise RuntimeError("Ollama unavailable")


def record(**overrides):
    values = {
        "material_id": "MAT-001",
        "filename": "001.jpg",
        "sha256": "a" * 64,
        "duplicate_of": "",
        "product": "HA",
        "topic": "product education",
        "audience": "clinic",
        "visual_summary": "simple product overview",
        "internal_comment": "safe",
        "customer_caption": "您好，這張圖整理了產品重點，提供您參考。",
        "risk_level": "low",
        "safety_flags": (),
        "sendability": "sendable",
        "review_status": "approved",
        "test_result": "reviewed",
        "campaigns": ("education",),
        "trigger_types": ("material_followup",),
    }
    values.update(overrides)
    return MaterialRecord(**values)


class MaterialDraftingTest(unittest.TestCase):
    def settings(self):
        return SimpleNamespace(
            openai_model="unused",
            ai_enabled=True,
            ai_provider="ollama",
            ollama_base_url="http://127.0.0.1:11434",
            ollama_model="gemma4:latest",
            ollama_timeout_seconds=1,
        )

    def test_selects_by_product_audience_campaign_and_trigger(self):
        catalog = MaterialCatalog(
            version=1,
            records=(
                record(),
                record(
                    material_id="MAT-002",
                    filename="002.jpg",
                    sha256="b" * 64,
                    campaigns=("other",),
                ),
            ),
        )

        selected = choose_material(
            catalog,
            product="HA",
            audience="clinic",
            campaign="education",
            trigger_type="material_followup",
        )

        self.assertEqual(selected.material_id, "MAT-001")

    def test_ollama_failure_keeps_deterministic_approved_caption(self):
        catalog = MaterialCatalog(version=1, records=(record(),))

        draft = build_material_draft(
            catalog,
            settings=self.settings(),
            line_query="001N1備份區",
            material_id="MAT-001",
            provider=FailingProvider(),
        )

        self.assertEqual(
            draft.draft_message,
            "您好，這張圖整理了產品重點，提供您參考。",
        )
        self.assertEqual(draft.message_kind, "image_text")
        self.assertEqual(draft.material_id, "MAT-001")
        self.assertEqual(draft.image_path, "001.jpg")
        self.assertIn("ai_fallback", draft.safety_flags)
        self.assertIn("Ollama unavailable", draft.error_message)


if __name__ == "__main__":
    unittest.main()
