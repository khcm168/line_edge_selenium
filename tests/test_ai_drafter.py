import unittest
import json

import app.ai_drafter as ai_drafter
from app.ai_drafter import constrained_rewrite, normalize_safety_flags
from app.scenario_engine import ScenarioDraft


class FakeProvider:
    def __init__(self, response=None, error=None):
        self.response = response or {}
        self.error = error

    def rewrite(self, draft):
        if self.error:
            raise self.error
        return self.response


class FakeOllamaResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def sample_draft(message="醫師您好，這是安全範本。"):
    return ScenarioDraft(
        draft_id="draft1",
        created_at="2026-06-06T09:00:00+08:00",
        trigger_type="usage_reminder",
        source_sheets=("DY2",),
        source_refs={"tab": "DY2", "row": 2},
        customer_id="P100",
        customer_name="Clinic A",
        line_query="P100",
        product="A+HA",
        signal_summary="usage signal",
        draft_message=message,
        line_contact="Clinic A LINE",
        line_message_style="warm",
    )


class AiDrafterTest(unittest.TestCase):
    def test_accepts_structured_provider_response(self):
        review = constrained_rewrite(
            sample_draft(),
            model="test-model",
            provider=FakeProvider(
                {
                    "message": "醫師您好，這是一則更自然但仍安全的提醒。",
                    "risk_level": "low",
                    "safety_flags": ["human_review_required"],
                    "rationale": "polished",
                }
            ),
        )

        self.assertTrue(review.used_ai)
        self.assertEqual(review.risk_level, "low")
        self.assertIn("更自然", review.message)

    def test_falls_back_when_provider_fails(self):
        review = constrained_rewrite(
            sample_draft("原始範本"),
            model="test-model",
            provider=FakeProvider(error=RuntimeError("offline")),
        )

        self.assertFalse(review.used_ai)
        self.assertEqual(review.message, "原始範本")
        self.assertIn("ai_fallback", review.safety_flags)
        self.assertIn("offline", review.error_message)

    def test_flags_medical_overclaim(self):
        review = constrained_rewrite(
            sample_draft(),
            model="test-model",
            provider=FakeProvider(
                {
                    "message": "醫師您好，這個產品保證有效。",
                    "risk_level": "low",
                    "safety_flags": [],
                    "rationale": "",
                }
            ),
        )

        self.assertEqual(review.risk_level, "high")
        self.assertIn("medical_overclaim_risk", review.safety_flags)

    def test_ollama_provider_parses_json_response(self):
        original = ai_drafter.request.urlopen

        def fake_urlopen(http_request, timeout):
            return FakeOllamaResponse(
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "message": "醫師您好，這邊用簡短方式提醒您確認資料。",
                                "risk_level": "low",
                                "safety_flags": ["human_review_required"],
                                "rationale": "matched style",
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            )

        ai_drafter.request.urlopen = fake_urlopen
        try:
            review = constrained_rewrite(
                sample_draft(),
                model="unused-openai-model",
                ai_provider="ollama",
                ollama_model="local-test",
            )
        finally:
            ai_drafter.request.urlopen = original

        self.assertTrue(review.used_ai)
        self.assertEqual(review.risk_level, "low")
        self.assertIn("簡短", review.message)

    def test_ollama_provider_falls_back_on_error(self):
        original = ai_drafter.request.urlopen

        def fake_urlopen(http_request, timeout):
            raise RuntimeError("ollama offline")

        ai_drafter.request.urlopen = fake_urlopen
        try:
            review = constrained_rewrite(
                sample_draft("template text"),
                model="unused-openai-model",
                ai_provider="ollama",
                ollama_model="local-test",
            )
        finally:
            ai_drafter.request.urlopen = original

        self.assertFalse(review.used_ai)
        self.assertEqual(review.message, "template text")
        self.assertIn("ollama offline", review.error_message)

    def test_safety_flags_ignore_tone_labels(self):
        flags = normalize_safety_flags(["Warm Tone", "human_review_required", "General Info Sharing"])

        self.assertEqual(flags, ("human_review_required",))

    def test_prompt_uses_resolved_message_style(self):
        prompt = ai_drafter._rewrite_prompt(sample_draft())

        self.assertEqual(prompt["line_message_style_raw"], "warm")
        self.assertEqual(prompt["message_style"]["code"], "warm_brief")
        self.assertIn("rules", prompt["message_style"])


if __name__ == "__main__":
    unittest.main()
