from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MessageStyle:
    code: str
    label: str
    rules: tuple[str, ...]
    avoid: tuple[str, ...]


STYLE_VOCABULARY: tuple[MessageStyle, ...] = (
    MessageStyle(
        code="formal_brief",
        label="正式、簡短",
        rules=(
            "Use respectful professional wording.",
            "Keep the message to two or three concise sentences.",
            "Prefer clear direct phrasing over emotional language.",
        ),
        avoid=("slang", "overly warm small talk", "long explanations"),
    ),
    MessageStyle(
        code="warm_brief",
        label="溫暖、簡短",
        rules=(
            "Sound warm and considerate without becoming casual.",
            "Keep the message short and easy to reply to.",
            "Use one soft relationship-building phrase at most.",
        ),
        avoid=("pressure", "excessive enthusiasm", "long greetings"),
    ),
    MessageStyle(
        code="friendly_reminder",
        label="親切提醒",
        rules=(
            "Frame the message as a light reminder.",
            "Use friendly but still professional wording.",
            "Make the requested next step clear.",
        ),
        avoid=("urgent wording", "blame", "repeated reminders"),
    ),
    MessageStyle(
        code="professional_active",
        label="活潑但專業",
        rules=(
            "Use energetic wording while staying businesslike.",
            "Keep the message focused on one useful update.",
            "Avoid sounding like advertising copy.",
        ),
        avoid=("sales hype", "exclamation-heavy wording", "medical claims"),
    ),
    MessageStyle(
        code="gratitude_natural",
        label="感謝、自然",
        rules=(
            "Lead with sincere thanks.",
            "Keep the wording conversational but respectful.",
            "Make the follow-up feel natural and low burden.",
        ),
        avoid=("formal ceremony", "over-thanking", "pressure"),
    ),
    MessageStyle(
        code="low_pressure_care",
        label="低壓力關心",
        rules=(
            "Sound caring and low pressure.",
            "Make it easy for the recipient to respond later.",
            "Avoid implying urgency unless the source data says so.",
        ),
        avoid=("deadlines", "pressure", "fear-based wording"),
    ),
    MessageStyle(
        code="continue_topic",
        label="接續上次話題",
        rules=(
            "Briefly connect to the previous topic.",
            "Do not over-explain context the recipient already knows.",
            "Ask or offer one clear next step.",
        ),
        avoid=("restarting the whole conversation", "new unrelated topics", "long summaries"),
    ),
    MessageStyle(
        code="neutral_professional",
        label="中性專業",
        rules=(
            "Use neutral professional wording.",
            "Keep one clear purpose.",
            "Prefer safe, factual language.",
        ),
        avoid=("casual jokes", "sales hype", "unsupported claims"),
    ),
)


def resolve_message_style(raw_style: str) -> MessageStyle:
    text = _normalize(raw_style)
    if not text:
        return _style("neutral_professional")
    matches = (
        ("warm_brief", ("溫暖", "warm")),
        ("professional_active", ("活潑", "active", "energetic")),
        ("formal_brief", ("正式", "formal")),
        ("warm_brief", ("溫暖", "warm")),
        ("friendly_reminder", ("親切", "提醒", "friendly", "reminder")),
        ("gratitude_natural", ("感謝", "自然", "thanks", "gratitude")),
        ("low_pressure_care", ("低壓力", "關心", "low_pressure", "care")),
        ("continue_topic", ("接續", "上次", "話題", "continue", "topic")),
    )
    for code, keywords in matches:
        if any(keyword in text for keyword in keywords):
            return _style(code)
    return _style("neutral_professional")


def _style(code: str) -> MessageStyle:
    for style in STYLE_VOCABULARY:
        if style.code == code:
            return style
    return STYLE_VOCABULARY[-1]


def _normalize(value: str) -> str:
    return str(value or "").strip().casefold().replace(" ", "_").replace("-", "_")
