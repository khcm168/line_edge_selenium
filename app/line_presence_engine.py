from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol
from urllib import request

from app.ai_drafter import normalize_risk, normalize_safety_flags, validate_message
from app.audit import append_jsonl, build_audit_record, utc_stamp
from app.bmp_safety import sanitize_bmp_text
from app.config import Settings
from app.scenario_engine import (
    DRAFT_STATUS_PENDING,
    SEND_MODE_REVIEW,
    ScenarioDraft,
    ScenarioEvent,
    draft_from_row,
    draft_to_log_event,
    taipei_now_iso,
)
from app.sheet_gateway import SheetGateway


TRIGGER_TYPE = "presence"
NOTIFICATION_TRIGGER_TYPE = "presence_notification"
NOTIFY_LINE_QUERY = "洪啓明"

PRESENCE_CATEGORIES = (
    "Health Knowledge",
    "Lifestyle",
    "Nutrition",
    "Exercise",
    "Sleep",
    "Festival",
    "Weather",
    "Season",
    "Clinic Story",
    "Interesting Facts",
    "Medical News",
    "Patient Education",
    "Doctor Appreciation",
    "Positive Thinking",
    "Motivation",
    "Human Warmth",
    "Small Happiness",
    "Taiwan Events",
    "Holiday Greetings",
    "Local Food",
    "Travel",
    "Behind the Scene",
    "Product Education Soft",
    "Disease Prevention",
    "FAQ",
)

DEFAULT_IMAGE_KEYWORDS = {
    "Health Knowledge": "clinic, doctor, health knowledge",
    "Lifestyle": "morning, nature, healthy routine",
    "Nutrition": "healthy breakfast, fruit, water",
    "Exercise": "exercise, stretching, sunrise",
    "Sleep": "sleep, night, calm bedroom",
    "Festival": "festival, Taiwan, warm greeting",
    "Weather": "weather, umbrella, morning",
    "Season": "season, nature, sunlight",
    "Clinic Story": "clinic, doctor, behind the scene",
    "Interesting Facts": "health knowledge, simple illustration",
    "Medical News": "doctor, newspaper, easy health news",
    "Patient Education": "doctor, patient education, clinic",
    "Doctor Appreciation": "doctor, appreciation, clinic",
    "Positive Thinking": "sunrise, small happiness, nature",
    "Motivation": "morning, walking, light",
    "Human Warmth": "parents, elderly, clinic",
    "Small Happiness": "coffee, morning, small happiness",
    "Taiwan Events": "Taiwan, street, daily life",
    "Holiday Greetings": "holiday, greeting, family",
    "Local Food": "Taiwan food, breakfast, local market",
    "Travel": "Taiwan travel, nature, road",
    "Behind the Scene": "clinic, behind the scene, doctor",
    "Product Education Soft": "health knowledge, simple product education",
    "Disease Prevention": "prevention, healthy lifestyle, doctor",
    "FAQ": "question, clinic, health knowledge",
}

PROFILE_TAB_NAME = "LINE_Presence_Profiles"


class PresenceProvider(Protocol):
    def generate(self, prompt: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class PresenceProfile:
    enabled: bool
    customer_id: str
    clinic_name: str
    line_query: str
    line_contact: str = ""
    line_message_style: str = ""
    interest_tags: tuple[str, ...] = ()
    cadence_days: int = 1
    preferred_send_time: str = ""
    last_category: str = ""
    last_generated_date: str = ""
    remark: str = ""


@dataclass(frozen=True)
class PresenceDraftResult:
    drafts: tuple[ScenarioDraft, ...]
    notification: ScenarioDraft | None
    events: tuple[ScenarioEvent, ...]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate draft-only LINE Presence Engine rows.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Taipei local YYYY-MM-DD date.")
    parser.add_argument("--max-clinics", type=int, default=0, help="Limit generated clinic drafts.")
    parser.add_argument("--source-json", help="Read profile and draft tabs from local JSON instead of Google Sheets.")
    parser.add_argument("--no-ai", action="store_true", help="Use deterministic safe fallback copy.")
    parser.add_argument("--no-write", action="store_true", help="Generate and audit without writing Sheets.")
    parser.add_argument("--no-notification", action="store_true", help="Do not create the draft-only 洪啓明 notice.")
    args = parser.parse_args(argv)

    settings = Settings.from_env(require_google=not bool(args.source_json))
    if args.no_ai:
        settings = settings.__class__(**{**settings.__dict__, "ai_enabled": False})
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    run_date = date.fromisoformat(args.date)
    gateway = None if args.source_json else SheetGateway.from_settings(settings)
    if args.source_json:
        sources = load_sources_from_json(args.source_json)
        profile_rows = rows_to_dicts(sources.get(settings.presence_profile_sheet_name) or sources.get(PROFILE_TAB_NAME) or [])
        existing_draft_rows = rows_to_dicts(sources.get(settings.draft_sheet_name) or [])
    else:
        assert gateway is not None
        profile_rows = gateway.read_presence_profile_rows()
        existing_draft_rows = [row.raw for row in gateway.read_draft_rows()]

    profiles = parse_presence_profiles(profile_rows)
    existing_drafts = tuple(draft_from_row(row) for row in existing_draft_rows)
    result = build_presence_drafts(
        profiles,
        existing_drafts=existing_drafts,
        run_date=run_date,
        settings=settings,
        max_clinics=args.max_clinics,
        include_notification=not args.no_notification,
    )
    drafts_to_write = result.drafts + ((result.notification,) if result.notification else ())
    log_events = tuple(draft_to_log_event(draft) for draft in drafts_to_write) + result.events

    draft_count = 0
    log_count = 0
    if gateway is not None and not args.no_write:
        draft_count = gateway.append_drafts(drafts_to_write)
        log_count = gateway.append_log_events(log_events)

    audit_path = settings.log_dir / f"line_presence_engine_{utc_stamp()}.jsonl"
    append_jsonl(
        audit_path,
        build_audit_record(
            action="build_line_presence_drafts",
            status="preview" if args.no_write else "written",
            detail=f"generated {len(result.drafts)} clinic drafts; wrote {draft_count} rows",
            source={
                "date": run_date.isoformat(),
                "profile_count": len(profiles),
                "generated_draft_count": len(result.drafts),
                "notification_generated": result.notification is not None,
                "draft_count": draft_count,
                "log_count": log_count,
                "draft_sheet": settings.draft_sheet_name,
                "presence_profile_sheet": settings.presence_profile_sheet_name,
                "source_json": args.source_json or "",
            },
        ),
    )
    print(f"generated_draft_count={len(result.drafts)}")
    print(f"notification_generated={str(result.notification is not None).lower()}")
    print(f"event_count={len(log_events)}")
    print(f"audit={audit_path}")
    if args.no_write:
        print("sheets_written=false")
    else:
        print(f"draft_count={draft_count}")
        print(f"log_count={log_count}")
        print(f"draft_sheet={settings.draft_sheet_name}")
        print(f"presence_profile_sheet={settings.presence_profile_sheet_name}")
    return 0


def build_presence_drafts(
    profiles: tuple[PresenceProfile, ...],
    *,
    existing_drafts: tuple[ScenarioDraft, ...],
    run_date: date,
    settings: Settings,
    max_clinics: int = 0,
    provider: PresenceProvider | None = None,
    include_notification: bool = True,
) -> PresenceDraftResult:
    drafts: list[ScenarioDraft] = []
    events: list[ScenarioEvent] = []
    for profile in profiles:
        if not profile.enabled:
            continue
        if not profile.customer_id or not profile.line_query:
            events.append(_event(profile, "skipped", "missing customer id or line query"))
            continue
        if _already_generated(profile, existing_drafts, run_date):
            events.append(_event(profile, "skipped", "presence draft already exists for date"))
            continue
        if _cadence_blocks(profile, run_date):
            events.append(_event(profile, "skipped", "cadence window not reached"))
            continue
        category = choose_category(profile, existing_drafts, run_date)
        draft = _draft_for_profile(
            profile,
            category=category,
            run_date=run_date,
            settings=settings,
            provider=provider,
        )
        drafts.append(draft)
        events.append(_event(profile, "generated", f"{category}: {draft.presence_theme}"))
        if max_clinics > 0 and len(drafts) >= max_clinics:
            break

    notification = build_notification_draft(drafts, run_date=run_date) if include_notification and drafts else None
    return PresenceDraftResult(tuple(drafts), notification, tuple(events))


def parse_presence_profiles(rows: list[dict[str, str]]) -> tuple[PresenceProfile, ...]:
    profiles = []
    for row in rows:
        normalized = {_canonical_header(key): value for key, value in row.items()}
        customer_id = _first(normalized, "customer_id", "code")
        line_query = _first(normalized, "line_query", "customer_id", "code")
        clinic_name = _first(normalized, "clinic_name", "customer_name", "clinic", "name") or customer_id
        profiles.append(
            PresenceProfile(
                enabled=_truthy(_first(normalized, "enabled")),
                customer_id=customer_id,
                clinic_name=clinic_name,
                line_query=line_query,
                line_contact=_first(normalized, "line_contact"),
                line_message_style=_first(normalized, "line_message_style"),
                interest_tags=_split_tags(_first(normalized, "interest_tags", "profile_tags", "tags")),
                cadence_days=_int_or_default(_first(normalized, "cadence_days"), 1),
                preferred_send_time=_first(normalized, "preferred_send_time", "send_time"),
                last_category=_first(normalized, "last_category"),
                last_generated_date=_first(normalized, "last_generated_date"),
                remark=_first(normalized, "remark"),
            )
        )
    return tuple(profiles)


def choose_category(
    profile: PresenceProfile,
    existing_drafts: tuple[ScenarioDraft, ...],
    run_date: date,
) -> str:
    avoided = _latest_category(profile, existing_drafts)
    preferred = _category_from_tags(profile.interest_tags)
    ordered = _rotated_categories(profile.customer_id or profile.line_query, run_date)
    if preferred:
        ordered = (preferred,) + tuple(category for category in ordered if category != preferred)
    for category in ordered:
        if category != avoided:
            return category
    return ordered[0]


def build_notification_draft(
    drafts: list[ScenarioDraft] | tuple[ScenarioDraft, ...],
    *,
    run_date: date,
) -> ScenarioDraft | None:
    if not drafts:
        return None
    first = drafts[0]
    total_length = sum(len(draft.draft_message) for draft in drafts)
    average_length = round(total_length / len(drafts))
    clinic = first.customer_name if len(drafts) == 1 else f"{len(drafts)} clinics"
    message = (
        "Today's Draft Generated\n"
        f"Clinic: {clinic}\n"
        f"Category: {first.presence_category}\n"
        f"Length: {average_length} chars\n"
        "Status: Ready for Review"
    )
    key = f"presence-notify|{run_date.isoformat()}|{len(drafts)}|{first.draft_id}"
    return ScenarioDraft(
        draft_id=hashlib.sha1(key.encode("utf-8")).hexdigest()[:16],
        created_at=taipei_now_iso(),
        trigger_type=NOTIFICATION_TRIGGER_TYPE,
        source_sheets=(PROFILE_TAB_NAME,),
        source_refs={
            "date": run_date.isoformat(),
            "clinic_draft_count": len(drafts),
            "first_draft_id": first.draft_id,
            "notice_type": "draft_only",
        },
        customer_id=NOTIFY_LINE_QUERY,
        customer_name=NOTIFY_LINE_QUERY,
        line_query=NOTIFY_LINE_QUERY,
        product="",
        signal_summary="Draft-only Presence Engine generation notice.",
        draft_message=message,
        presence_date=run_date.isoformat(),
        presence_category="Notification",
        presence_theme="Presence draft generated",
        image_suggestion="",
        hashtag="",
        preferred_send_time="",
        remark="Draft-only notice; human approval required before any LINE send.",
        risk_level="low",
        safety_flags=("human_review_required",),
        status=DRAFT_STATUS_PENDING,
        send_mode=SEND_MODE_REVIEW,
        result="presence_notification_draft",
    )


def rows_to_dicts(values: list[list[str]]) -> list[dict[str, str]]:
    if len(values) < 2:
        return []
    headers = [str(cell).strip() for cell in values[0]]
    return [
        {
            headers[index]: str(value).strip()
            for index, value in enumerate(row)
            if index < len(headers) and headers[index]
        }
        for row in values[1:]
    ]


def load_sources_from_json(path: str | None) -> dict[str, list[list[str]]]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("--source-json must contain an object mapping tab names to rows.")
    return {str(tab): rows for tab, rows in data.items() if isinstance(rows, list)}


def _draft_for_profile(
    profile: PresenceProfile,
    *,
    category: str,
    run_date: date,
    settings: Settings,
    provider: PresenceProvider | None,
) -> ScenarioDraft:
    prompt = _presence_prompt(profile, category, run_date)
    raw = _generate_raw(prompt, settings=settings, provider=provider)
    content = _normalize_generation(raw, profile=profile, category=category)
    key = f"presence|{run_date.isoformat()}|{profile.customer_id}|{category}"
    return ScenarioDraft(
        draft_id=hashlib.sha1(key.encode("utf-8")).hexdigest()[:16],
        created_at=taipei_now_iso(),
        trigger_type=TRIGGER_TYPE,
        source_sheets=(PROFILE_TAB_NAME,),
        source_refs={
            "profile_customer_id": profile.customer_id,
            "interest_tags": list(profile.interest_tags),
            "category": content["category"],
            "theme": content["theme"],
            "ai_rationale": content["rationale"],
        },
        customer_id=profile.customer_id,
        customer_name=profile.clinic_name,
        line_query=profile.line_query,
        line_contact=profile.line_contact,
        line_message_style=profile.line_message_style,
        product="",
        signal_summary=f"Presence touchpoint: {content['category']} / {content['theme']}",
        draft_message=sanitize_bmp_text(content["message"]),
        presence_date=run_date.isoformat(),
        presence_category=content["category"],
        presence_theme=content["theme"],
        image_suggestion=content["image_suggestion"],
        hashtag="\n".join(content["hashtags"]),
        preferred_send_time=profile.preferred_send_time,
        remark=profile.remark,
        risk_level=content["risk_level"],
        safety_flags=content["safety_flags"],
        status=DRAFT_STATUS_PENDING,
        send_mode=SEND_MODE_REVIEW,
        result=content["result"],
    )


def _generate_raw(
    prompt: dict[str, Any],
    *,
    settings: Settings,
    provider: PresenceProvider | None,
) -> dict[str, Any]:
    if not settings.ai_enabled:
        return _fallback_generation(prompt, "AI disabled")
    try:
        if provider is not None:
            return provider.generate(prompt)
        if settings.ai_provider == "openai":
            return _openai_generate(prompt, model=settings.openai_model)
        return _ollama_generate(
            prompt,
            model=settings.ollama_model or settings.openai_model,
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
    except Exception as exc:
        return _fallback_generation(prompt, f"{type(exc).__name__}: {exc}")


def _normalize_generation(raw: dict[str, Any], *, profile: PresenceProfile, category: str) -> dict[str, Any]:
    fallback = _fallback_generation(
        _presence_prompt(profile, category, date.today()),
        "fallback after invalid AI output",
    )
    message = sanitize_bmp_text(str(raw.get("message") or "").strip())
    if not (120 <= len(message) <= 180):
        raw = fallback
        message = raw["message"]
    risk_level, flags = validate_message(
        message,
        requested_risk=normalize_risk(str(raw.get("risk_level") or "low")),
        requested_flags=normalize_safety_flags(raw.get("safety_flags") or ("human_review_required",)),
    )
    if "human_review_required" not in flags:
        flags = flags + ("human_review_required",)
    hashtags = _normalize_hashtags(raw.get("hashtags") or raw.get("hashtag") or ())
    if not (3 <= len(hashtags) <= 6):
        hashtags = _default_hashtags(str(raw.get("category") or category))
    image_suggestion = str(raw.get("image_suggestion") or raw.get("image_keywords") or "").strip()
    if not image_suggestion:
        image_suggestion = DEFAULT_IMAGE_KEYWORDS.get(category, "health knowledge, clinic, nature")
    result = str(raw.get("result") or "").strip()
    if not result:
        result = "ai_generation" if raw.get("used_ai", True) else "template_fallback"
    return {
        "category": str(raw.get("category") or category).strip() or category,
        "theme": str(raw.get("theme") or _default_theme(category)).strip() or _default_theme(category),
        "message": message,
        "image_suggestion": image_suggestion,
        "hashtags": hashtags,
        "risk_level": risk_level,
        "safety_flags": flags,
        "rationale": str(raw.get("rationale") or "").strip(),
        "result": result,
    }


def _fallback_generation(prompt: dict[str, Any], reason: str) -> dict[str, Any]:
    category = str(prompt.get("category") or "Health Knowledge")
    theme = _default_theme(category)
    message = _fallback_message(category)
    return {
        "category": category,
        "theme": theme,
        "message": message,
        "image_suggestion": DEFAULT_IMAGE_KEYWORDS.get(category, "health knowledge, clinic, nature"),
        "hashtags": _default_hashtags(category),
        "risk_level": "low",
        "safety_flags": ["human_review_required"],
        "rationale": reason,
        "result": f"template_fallback: {reason}",
        "used_ai": False,
    }


def _presence_prompt(profile: PresenceProfile, category: str, run_date: date) -> dict[str, Any]:
    return {
        "date": run_date.isoformat(),
        "clinic_name": profile.clinic_name,
        "line_contact": profile.line_contact,
        "line_message_style": profile.line_message_style,
        "interest_tags": list(profile.interest_tags),
        "category": category,
        "reference_style": {
            "source": "Provided Instagram screenshot and local Material library",
            "imitate": ["concise educational rhythm", "warm closing", "visual storytelling"],
            "do_not_copy": True,
        },
        "rules": [
            "Write Traditional Chinese for Taiwan.",
            "Length must be 120 to 180 Chinese characters.",
            "Use hook, useful content, friendly ending.",
            "Sound like a light relationship touchpoint, not marketing.",
            "Avoid hard selling, medical claims, politics, religion, and fear-based emotion.",
            "Return JSON with category, theme, message, image_suggestion, hashtags, risk_level, safety_flags, rationale.",
        ],
    }


def _openai_generate(prompt: dict[str, Any], *, model: str) -> dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")
    try:
        from openai import OpenAI
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("openai package is not installed") from exc
    client = OpenAI()
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": "Generate safe, warm, draft-only Traditional Chinese LINE relationship content. Return JSON only.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        text={"format": {"type": "json_object"}},
    )
    text = getattr(response, "output_text", "") or ""
    return json.loads(text)


def _ollama_generate(
    prompt: dict[str, Any],
    *,
    model: str,
    base_url: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": "Generate safe, warm Traditional Chinese LINE relationship content. Return JSON only.",
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


def _fallback_message(category: str) -> str:
    messages = {
        "Sleep": "今天忽然想到一個小提醒：睡眠不是等忙完才補的事，而是每天幫身體整理的時間。晚上少一點滑手機、讓燈光暗一點，隔天精神通常會舒服許多。若最近比較忙，也可以先從固定上床時間開始，不必一次改很多，只要每天穩一點就好。希望這個小知識剛好派上用場，也祝今天一切順順的。",
        "Nutrition": "今天想分享一個很日常的小觀念：營養不一定要很複雜，先把水喝夠、每餐留一點蔬菜和蛋白質，就是照顧身體的基本功。忙的時候也別忘了好好吃飯，少一點匆忙，多一點穩定。若今天行程很滿，也可以先從一杯水開始，再替自己留一份簡單但踏實的餐。願這個提醒讓今天更舒服一點。",
        "Exercise": "今天想到一個簡單提醒：身體不一定需要很劇烈的運動才算照顧，走一小段路、伸展肩頸、讓呼吸慢下來，都能讓一整天比較鬆。若坐得久了，起身活動三分鐘也很好，不需要特別準備。小小活動累積起來，也是在替身體保留彈性，別忘了補水。希望這個方法陪你把忙碌放輕一點。",
    }
    return messages.get(
        category,
        "今天忽然想到一個小知識：健康照顧常常不是一次做很多，而是每天留一點點空間給身體。喝水、伸展、好好吃飯、早點休息，都是很小卻有力量的累積。忙的時候更需要把節奏放穩一點，不必完美，只要多照顧自己一點。希望這則提醒剛好陪你一下，也祝今天平安順心。",
    )


def _default_theme(category: str) -> str:
    return {
        "Sleep": "睡眠與日常修復",
        "Nutrition": "日常營養小提醒",
        "Exercise": "輕量活動與身體舒展",
        "Health Knowledge": "健康照顧的小累積",
        "Patient Education": "容易理解的健康觀念",
        "Human Warmth": "日常關心與陪伴感",
    }.get(category, f"{category} daily touchpoint")


def _default_hashtags(category: str) -> tuple[str, ...]:
    base = {
        "Sleep": ("#健康生活", "#好好睡覺", "#今天也要照顧自己", "#診所日常"),
        "Nutrition": ("#健康生活", "#均衡飲食", "#今天也要照顧自己", "#營養小提醒"),
        "Exercise": ("#健康生活", "#輕鬆活動", "#今天也要照顧自己", "#日常保養"),
    }
    return base.get(category, ("#健康生活", "#預防醫學", "#今天也要照顧自己", "#診所日常"))


def _normalize_hashtags(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        pieces = value.replace("\n", " ").split()
    else:
        pieces = [str(item) for item in value or ()]
    tags = []
    for piece in pieces:
        tag = piece.strip()
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = f"#{tag}"
        tags.append(tag)
    return tuple(dict.fromkeys(tags))[:6]


def _already_generated(profile: PresenceProfile, drafts: tuple[ScenarioDraft, ...], run_date: date) -> bool:
    for draft in drafts:
        if draft.trigger_type != TRIGGER_TYPE:
            continue
        if draft.customer_id == profile.customer_id and draft.presence_date == run_date.isoformat():
            return True
    return False


def _cadence_blocks(profile: PresenceProfile, run_date: date) -> bool:
    if not profile.last_generated_date:
        return False
    try:
        previous = date.fromisoformat(profile.last_generated_date)
    except ValueError:
        return False
    return (run_date - previous).days < max(profile.cadence_days, 1)


def _latest_category(profile: PresenceProfile, drafts: tuple[ScenarioDraft, ...]) -> str:
    latest = profile.last_category
    latest_date = profile.last_generated_date
    for draft in drafts:
        if draft.trigger_type != TRIGGER_TYPE or draft.customer_id != profile.customer_id:
            continue
        if draft.presence_date >= latest_date:
            latest = draft.presence_category
            latest_date = draft.presence_date
    return latest


def _category_from_tags(tags: tuple[str, ...]) -> str:
    text = " ".join(tags).casefold()
    matches = (
        ("Sleep", ("sleep", "睡眠")),
        ("Nutrition", ("nutrition", "diet", "food", "營養", "飲食")),
        ("Exercise", ("exercise", "rehabilitation", "orthopedics", "運動", "復健", "骨科")),
        ("Disease Prevention", ("diabetes", "hypertension", "prevention", "糖尿", "高血壓", "預防")),
        ("Patient Education", ("pediatrics", "ent", "family medicine", "兒科", "耳鼻喉", "家醫")),
    )
    for category, keywords in matches:
        if any(keyword in text for keyword in keywords):
            return category
    return ""


def _rotated_categories(seed: str, run_date: date) -> tuple[str, ...]:
    digest = hashlib.sha1(f"{seed}|{run_date.isoformat()}".encode("utf-8")).hexdigest()
    offset = int(digest[:4], 16) % len(PRESENCE_CATEGORIES)
    return PRESENCE_CATEGORIES[offset:] + PRESENCE_CATEGORIES[:offset]


def _event(profile: PresenceProfile, status: str, result: str) -> ScenarioEvent:
    return ScenarioEvent(
        timestamp=taipei_now_iso(),
        trigger_type=TRIGGER_TYPE,
        source_sheets=(PROFILE_TAB_NAME,),
        customer_id=profile.customer_id,
        customer_name=profile.clinic_name,
        draft_status=status,
        message_risk_level="low",
        result=result,
    )


def _canonical_header(value: str) -> str:
    return (
        str(value or "")
        .strip()
        .casefold()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def _first(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(_canonical_header(name), "").strip()
        if value:
            return value
    return ""


def _truthy(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "y", "on", "enabled"}


def _split_tags(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.replace(";", ",").split(",") if item.strip())


def _int_or_default(value: str, default: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


if __name__ == "__main__":
    raise SystemExit(main())
