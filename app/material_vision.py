from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


DEFAULT_VISION_MODEL = "gemma3:12b"
VISION_FLAGS = {
    "medical_overclaim_risk",
    "patient_privacy_risk",
    "prescription_drug_content",
    "dense_clinical_reference",
    "competitor_comparison_risk",
}


@dataclass(frozen=True)
class VisionAnalysis:
    visual_summary: str
    visible_text: str
    topic: str
    audience: str
    tags: tuple[str, ...]
    risk_level: str
    safety_flags: tuple[str, ...]
    risk_reasons: tuple[str, ...]
    neutral_caption: str


def analyze_material_image(
    image_path: str | Path,
    *,
    folder_name: str,
    model: str = DEFAULT_VISION_MODEL,
    base_url: str = "http://127.0.0.1:11434",
    timeout_seconds: int = 300,
    num_gpu: int = 0,
    num_thread: int = 4,
) -> VisionAnalysis:
    source = Path(image_path)
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    prompt = {
        "task": (
            "Inspect the supplied image pixels as a proposed LINE educational "
            "material. Return one JSON object only."
        ),
        "context": {
            "folder_name": folder_name,
            "filename": source.name,
            "language": "Traditional Chinese used in Taiwan",
        },
        "required_fields": {
            "visual_summary": "objective 1-2 sentence visual description",
            "visible_text": "important readable text; empty if unreadable",
            "topic": "short searchable topic",
            "audience": "likely audience, stated conservatively",
            "tags": "3-8 short searchable terms without #",
            "risk_level": "low, medium, or high",
            "safety_flags": (
                "zero or more of medical_overclaim_risk, patient_privacy_risk, "
                "prescription_drug_content, dense_clinical_reference, "
                "competitor_comparison_risk"
            ),
            "risk_reasons": "brief reasons grounded only in visible content",
            "neutral_caption": (
                "1-2 sentence neutral Traditional Chinese caption; do not "
                "promise efficacy, diagnose, prescribe, or identify a patient"
            ),
        },
        "rules": [
            "Write every descriptive field and every tag in Traditional Chinese, "
            "except unavoidable brand names or technical abbreviations.",
            "Each tags array item must be one short concept, not a sentence or "
            "a space-separated list.",
            "Do not infer facts from the filename alone.",
            "Describe only objects and people actually visible in the pixels.",
            "Do not approve the material for sending.",
            "Flag faces, names, charts, prescriptions, drug doses, treatment "
            "claims, before/after claims, and guaranteed outcomes conservatively.",
            "If the image cannot be read, use high risk and explain why.",
        ],
    }
    parse_error: ValueError | json.JSONDecodeError | None = None
    for attempt in range(2):
        payload = {
            "model": model,
            "prompt": json.dumps(prompt, ensure_ascii=False),
            "images": [encoded],
            "stream": False,
            "keep_alive": 0,
            "format": "json",
            "options": {
                "num_ctx": 4096,
                "num_predict": 1024,
                "temperature": 0,
                "num_gpu": max(0, num_gpu),
                "num_thread": max(1, num_thread),
            },
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            f"{base_url.rstrip('/')}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama vision HTTP {exc.code}: {detail}") from exc
        raw = str(result.get("response") or "").strip()
        try:
            return parse_vision_analysis(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            parse_error = exc
            if attempt == 0:
                continue
    raise RuntimeError(
        f"Ollama vision returned invalid JSON twice: {parse_error}"
    ) from parse_error


def parse_vision_analysis(raw: str) -> VisionAnalysis:
    payload = _json_object(raw)
    summary = _required_text(payload, "visual_summary")
    topic = _required_text(payload, "topic")
    caption = _required_text(payload, "neutral_caption")
    risk = str(payload.get("risk_level") or "high").strip().casefold()
    if risk not in {"low", "medium", "high"}:
        risk = "high"
    flags = _string_tuple(payload.get("safety_flags"))
    flags = tuple(flag for flag in flags if flag in VISION_FLAGS)
    tags = _normalize_tags(_string_tuple(payload.get("tags")))
    if not tags:
        tags = (topic,)
    return VisionAnalysis(
        visual_summary=summary,
        visible_text=str(payload.get("visible_text") or "").strip(),
        topic=topic,
        audience=str(payload.get("audience") or "需人工判斷").strip(),
        tags=tags,
        risk_level=risk,
        safety_flags=flags,
        risk_reasons=_string_tuple(payload.get("risk_reasons")),
        neutral_caption=caption,
    )


def _json_object(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("Ollama vision response must be one JSON object")
    return payload


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = str(payload.get(field) or "").strip()
    if not value:
        raise ValueError(f"Ollama vision response is missing {field}")
    return value


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _normalize_tags(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = []
    for value in values:
        cleaned = value.strip().lstrip("#")
        if not cleaned:
            continue
        if len(values) == 1 and len(cleaned.split()) > 2:
            normalized.extend(cleaned.split())
        else:
            normalized.append(cleaned)
    return tuple(dict.fromkeys(normalized))[:8]
