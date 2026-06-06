from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import Settings
from app.scenario_engine import ScenarioDraft


HIGH_RISK_TERMS = (
    "治癒",
    "療效保證",
    "保證有效",
    "治療成功",
    " cure ",
    "guaranteed",
)
PATIENT_PRIVACY_TERMS = ("病人姓名", "身分證", "病歷號", "電話號碼")


class DraftProvider(Protocol):
    def rewrite(self, draft: ScenarioDraft) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class DraftReview:
    message: str
    risk_level: str
    safety_flags: tuple[str, ...]
    rationale: str
    used_ai: bool
    error_message: str = ""


def draft_with_ai(
    draft: ScenarioDraft,
    *,
    settings: Settings,
    provider: DraftProvider | None = None,
) -> ScenarioDraft:
    review = constrained_rewrite(
        draft,
        model=settings.openai_model,
        enabled=settings.ai_enabled,
        provider=provider,
    )
    result = "ai_rewrite" if review.used_ai else "template_fallback"
    if review.rationale:
        result = f"{result}: {review.rationale}"
    return draft.with_message(
        review.message,
        risk_level=review.risk_level,
        safety_flags=review.safety_flags,
        result=result,
        error_message=review.error_message,
    )


def constrained_rewrite(
    draft: ScenarioDraft,
    *,
    model: str,
    enabled: bool = True,
    provider: DraftProvider | None = None,
) -> DraftReview:
    fallback = _fallback_review(draft, "AI disabled")
    if not enabled:
        return fallback
    try:
        raw = provider.rewrite(draft) if provider is not None else _openai_rewrite(draft, model=model)
        message = str(raw.get("message") or "").strip()
        risk_level = normalize_risk(str(raw.get("risk_level") or draft.risk_level))
        rationale = str(raw.get("rationale") or "").strip()
        flags = tuple(str(item).strip() for item in raw.get("safety_flags", []) if str(item).strip())
        if not message:
            return _fallback_review(draft, "AI returned blank message")
        risk_level, flags = validate_message(message, requested_risk=risk_level, requested_flags=flags)
        if "human_review_required" not in flags:
            flags = flags + ("human_review_required",)
        return DraftReview(message, risk_level, flags, rationale, True)
    except Exception as exc:
        return _fallback_review(draft, f"{type(exc).__name__}: {exc}")


def normalize_risk(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized in {"low", "medium", "high"}:
        return normalized
    return "medium"


def validate_message(
    message: str,
    *,
    requested_risk: str = "low",
    requested_flags: tuple[str, ...] = (),
) -> tuple[str, tuple[str, ...]]:
    flags = list(requested_flags)
    risk = normalize_risk(requested_risk)
    lowered = f" {message.casefold()} "
    if any(term.casefold() in lowered for term in HIGH_RISK_TERMS):
        risk = "high"
        flags.append("medical_overclaim_risk")
    if any(term.casefold() in lowered for term in PATIENT_PRIVACY_TERMS):
        risk = "high"
        flags.append("patient_privacy_risk")
    if len(_sentences(message)) > 5:
        flags.append("message_too_long")
        if risk == "low":
            risk = "medium"
    if not flags:
        flags.append("manual_review_required")
    return risk, tuple(dict.fromkeys(flags))


def _fallback_review(draft: ScenarioDraft, reason: str) -> DraftReview:
    risk_level, flags = validate_message(
        draft.draft_message,
        requested_risk=draft.risk_level,
        requested_flags=draft.safety_flags,
    )
    if "ai_fallback" not in flags:
        flags = flags + ("ai_fallback",)
    return DraftReview(
        message=draft.draft_message,
        risk_level=risk_level,
        safety_flags=flags,
        rationale=reason,
        used_ai=False,
        error_message="" if reason == "AI disabled" else reason,
    )


def _openai_rewrite(draft: ScenarioDraft, *, model: str) -> dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")
    try:
        from openai import OpenAI
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("openai package is not installed") from exc

    client = OpenAI()
    prompt = {
        "trigger_type": draft.trigger_type,
        "product": draft.product,
        "customer_id": draft.customer_id,
        "customer_name": draft.customer_name,
        "signal_summary": draft.signal_summary,
        "approved_template": draft.draft_message,
        "rules": [
            "Use Traditional Chinese suitable for Taiwan medical business relationships.",
            "Keep one clear purpose only.",
            "Do not include identifiable patient information.",
            "Do not claim cure rate, guaranteed efficacy, or patient outcomes.",
            "Preserve the approved template intent and do not invent facts.",
        ],
    }
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "message": {"type": "string"},
            "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
            "safety_flags": {"type": "array", "items": {"type": "string"}},
            "rationale": {"type": "string"},
        },
        "required": ["message", "risk_level", "safety_flags", "rationale"],
    }
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": "You rewrite approved LINE message templates into safe, warm Traditional Chinese. Return JSON only.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "line_draft_review",
                "strict": True,
                "schema": schema,
            }
        },
    )
    text = getattr(response, "output_text", "") or ""
    if not text:
        output = getattr(response, "output", None)
        text = _extract_text(output)
    return json.loads(text)


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_extract_text(item) for item in value)
    if isinstance(value, dict):
        return _extract_text(value.get("content", "")) or str(value.get("text", ""))
    return ""


def _sentences(message: str) -> list[str]:
    return [part for part in re.split(r"[。！？!?]+", message) if part.strip()]
