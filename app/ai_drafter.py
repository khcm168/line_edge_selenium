from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import request

from app.config import Settings
from app.message_style import resolve_message_style
from app.scenario_engine import ScenarioDraft


HIGH_RISK_TERMS = (
    "治癒",
    "痊癒",
    "保證有效",
    "療效保證",
    " cure ",
    "guaranteed",
)
PATIENT_PRIVACY_TERMS = ("病患姓名", "病歷", "診斷", "個案資料")


ALLOWED_SAFETY_FLAGS = {
    "human_review_required",
    "manual_review_required",
    "message_too_long",
    "medical_overclaim_risk",
    "patient_privacy_risk",
}


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
        ai_provider=settings.ai_provider,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        ollama_timeout_seconds=settings.ollama_timeout_seconds,
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
    ai_provider: str = "ollama",
    ollama_base_url: str = "http://127.0.0.1:11434",
    ollama_model: str = "",
    ollama_timeout_seconds: int = 180,
) -> DraftReview:
    fallback = _fallback_review(draft, "AI disabled")
    if not enabled:
        return fallback
    try:
        if provider is not None:
            raw = provider.rewrite(draft)
        elif ai_provider == "openai":
            raw = _openai_rewrite(draft, model=model)
        else:
            raw = _ollama_rewrite(
                draft,
                model=ollama_model or model,
                base_url=ollama_base_url,
                timeout_seconds=ollama_timeout_seconds,
            )
        message = str(raw.get("message") or "").strip()
        risk_level = normalize_risk(str(raw.get("risk_level") or draft.risk_level))
        rationale = str(raw.get("rationale") or "").strip()
        flags = normalize_safety_flags(raw.get("safety_flags") or [])
        if not message:
            return _fallback_review(draft, "AI returned blank message")
        if _has_unexpected_script(message):
            return _fallback_review(draft, "AI returned unexpected script characters")
        risk_level, flags = validate_message(
            message,
            requested_risk=risk_level,
            requested_flags=flags,
        )
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


def normalize_safety_flags(values: Any) -> tuple[str, ...]:
    if isinstance(values, str):
        values = [values]
    normalized = []
    for item in values or []:
        flag = str(item).strip().casefold().replace(" ", "_").replace("-", "_")
        if flag in ALLOWED_SAFETY_FLAGS:
            normalized.append(flag)
    return tuple(dict.fromkeys(normalized))


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
    prompt = _rewrite_prompt(draft)
    prompt["rules"].append("Use LINE風格 only as tone guidance; do not let it override safety rules.")
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
                "schema": _review_schema(),
            }
        },
    )
    text = getattr(response, "output_text", "") or ""
    if not text:
        text = _extract_text(getattr(response, "output", None))
    return json.loads(text)


def _ollama_rewrite(
    draft: ScenarioDraft,
    *,
    model: str,
    base_url: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    prompt = _rewrite_prompt(draft)
    prompt["rules"].append("Return a single JSON object with keys: message, risk_level, safety_flags, rationale.")
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": "Rewrite approved LINE templates into safe, warm Traditional Chinese. Return JSON only.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    http_request = request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=timeout_seconds) as response:
        result = json.loads(response.read().decode("utf-8"))
    content = str((result.get("message") or {}).get("content") or "").strip()
    if not content:
        content = str(result.get("response") or "").strip()
    return json.loads(content)


def _rewrite_prompt(draft: ScenarioDraft) -> dict[str, Any]:
    style = resolve_message_style(draft.line_message_style)
    return {
        "trigger_type": draft.trigger_type,
        "product": draft.product,
        "customer_id": draft.customer_id,
        "customer_name": draft.customer_name,
        "line_query": draft.line_query,
        "line_nickname": draft.line_contact,
        "line_style_raw": draft.line_message_style,
        "line_message_style_raw": draft.line_message_style,
        "message_style": {
            "code": style.code,
            "label": style.label,
            "rules": list(style.rules),
            "avoid": list(style.avoid),
        },
        "signal_summary": draft.signal_summary,
        "approved_template": draft.draft_message,
        "rules": [
            "Use Traditional Chinese suitable for Taiwan medical business relationships.",
            "Keep one clear purpose only.",
            "Do not include identifiable patient information.",
            "Do not claim cure rate, guaranteed efficacy, or patient outcomes.",
            "Preserve the approved template intent and do not invent facts.",
            "Reference LINE暱稱 only to make the wording feel personally addressed; do not expose internal IDs unless needed.",
            "Use the resolved LINE風格 rules exactly; do not invent a new tone category.",
            "safety_flags must use only: human_review_required, manual_review_required, message_too_long, medical_overclaim_risk, patient_privacy_risk.",
        ],
    }


def _review_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "message": {"type": "string"},
            "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
            "safety_flags": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(ALLOWED_SAFETY_FLAGS)},
            },
            "rationale": {"type": "string"},
        },
        "required": ["message", "risk_level", "safety_flags", "rationale"],
    }


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_extract_text(item) for item in value)
    if isinstance(value, dict):
        return _extract_text(value.get("content", "")) or str(value.get("text", ""))
    return ""


def _has_unexpected_script(message: str) -> bool:
    for char in message:
        code = ord(char)
        if 0x0E00 <= code <= 0x0E7F:
            return True
        if 0x0900 <= code <= 0x097F:
            return True
        if 0x3040 <= code <= 0x30FF:
            return True
    return False


def _sentences(message: str) -> list[str]:
    return [part for part in re.split(r"[。！？!?；;\n]+", message) if part.strip()]
