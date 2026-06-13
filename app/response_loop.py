from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from app.audit import append_jsonl
from app.scenario_engine import ScenarioDraft, taipei_now_iso


RESPONSE_CLASSES = (
    "positive",
    "neutral",
    "negative",
    "read_no_reply",
    "order_intent",
    "material_request",
    "event_interest",
    "do_not_disturb",
)
FOLLOW_UP_DELAYS = (
    ("24h", timedelta(hours=24)),
    ("48h", timedelta(hours=48)),
    ("72h", timedelta(hours=72)),
    ("7d", timedelta(days=7)),
)


@dataclass(frozen=True)
class FollowUpRecord:
    follow_up_id: str
    draft_id: str
    message_id: str
    recipient: str
    sent_at: str
    checkpoint: str
    due_at: str
    status: str = "pending"


@dataclass(frozen=True)
class ResponseIntake:
    intake_id: str
    recorded_at: str
    draft_id: str
    message_id: str
    screenshot_path: str
    screenshot_sha256: str
    response_class: str
    result: str
    next_action: str
    reviewer: str
    response_text: str = ""


@dataclass(frozen=True)
class ObservedMessage:
    group_name: str
    author: str
    text: str
    observed_at: str
    message_id: str = ""

    @property
    def observation_hash(self) -> str:
        value = "|".join(
            (
                self.group_name.strip(),
                self.author.strip(),
                self.text.strip(),
                self.observed_at.strip(),
                self.message_id.strip(),
            )
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


def schedule_follow_ups(
    *,
    draft_id: str,
    message_id: str,
    recipient: str,
    sent_at: str,
) -> tuple[FollowUpRecord, ...]:
    sent = datetime.fromisoformat(sent_at)
    records = []
    for checkpoint, delay in FOLLOW_UP_DELAYS:
        key = f"{draft_id}|{message_id}|{checkpoint}"
        records.append(
            FollowUpRecord(
                follow_up_id=hashlib.sha1(key.encode("utf-8")).hexdigest()[:16],
                draft_id=draft_id,
                message_id=message_id,
                recipient=recipient,
                sent_at=sent_at,
                checkpoint=checkpoint,
                due_at=(sent + delay).replace(microsecond=0).isoformat(),
            )
        )
    return tuple(records)


def append_follow_ups(
    path: str | Path,
    records: Iterable[FollowUpRecord],
) -> int:
    target = Path(path)
    existing = _existing_values(target, "follow_up_id")
    written = 0
    for record in records:
        if record.follow_up_id in existing:
            continue
        append_jsonl(target, asdict(record))
        existing.add(record.follow_up_id)
        written += 1
    return written


def classify_response(
    response_text: str,
    *,
    explicit_class: str = "",
) -> str:
    requested = explicit_class.strip().casefold().replace("-", "_").replace(" ", "_")
    if requested:
        if requested not in RESPONSE_CLASSES:
            raise ValueError(f"Unsupported LINE response class: {explicit_class}")
        return requested

    text = response_text.strip().casefold()
    if not text:
        return "read_no_reply"
    if any(term in text for term in ("不要再", "請勿打擾", "別再傳", "do not disturb")):
        return "do_not_disturb"
    if any(term in text for term in ("下單", "訂購", "幫我留", "order", "幾盒", "幾組")):
        return "order_intent"
    if any(term in text for term in ("資料", "簡報", "型錄", "material", "資訊")):
        return "material_request"
    if any(term in text for term in ("活動", "講座", "報名", "event", "參加")):
        return "event_interest"
    if any(term in text for term in ("不用", "沒興趣", "不需要", "negative", "謝絕")):
        return "negative"
    if any(term in text for term in ("好", "可以", "謝謝", "有興趣", "positive", "ok")):
        return "positive"
    return "neutral"


def record_screenshot_intake(
    ledger_path: str | Path,
    *,
    draft_id: str,
    message_id: str,
    screenshot_path: str | Path,
    result: str,
    next_action: str,
    reviewer: str,
    response_text: str = "",
    response_class: str = "",
) -> ResponseIntake:
    if not draft_id.strip() and not message_id.strip():
        raise ValueError("Screenshot intake requires Draft_ID or message ID")
    screenshot = Path(screenshot_path).expanduser().resolve()
    if not screenshot.is_file():
        raise FileNotFoundError(f"Response screenshot not found: {screenshot}")
    classification = classify_response(
        response_text,
        explicit_class=response_class,
    )
    screenshot_hash = _sha256_file(screenshot)
    key = "|".join((draft_id, message_id, screenshot_hash, classification))
    intake = ResponseIntake(
        intake_id=hashlib.sha1(key.encode("utf-8")).hexdigest()[:16],
        recorded_at=taipei_now_iso(),
        draft_id=draft_id,
        message_id=message_id,
        screenshot_path=str(screenshot),
        screenshot_sha256=screenshot_hash,
        response_class=classification,
        result=result,
        next_action=next_action,
        reviewer=reviewer,
        response_text=response_text,
    )
    if intake.intake_id not in _existing_values(Path(ledger_path), "intake_id"):
        append_jsonl(ledger_path, asdict(intake))
    return intake


class ObservationLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def unseen(
        self,
        observations: Iterable[ObservedMessage],
        *,
        allowed_groups: tuple[str, ...],
    ) -> tuple[ObservedMessage, ...]:
        allowed = {name.strip() for name in allowed_groups if name.strip()}
        seen = _existing_values(self.path, "observation_hash")
        return tuple(
            item
            for item in observations
            if item.group_name in allowed and item.observation_hash not in seen
        )

    def record(
        self,
        observation: ObservedMessage,
        *,
        evidence_snapshot: str | Path,
        response_class: str,
        draft_id: str,
    ) -> None:
        append_jsonl(
            self.path,
            {
                **asdict(observation),
                "observation_hash": observation.observation_hash,
                "evidence_snapshot": str(evidence_snapshot),
                "response_class": response_class,
                "draft_id": draft_id,
                "recorded_at": taipei_now_iso(),
            },
        )


def response_draft_from_observation(
    observation: ObservedMessage,
    *,
    response_class: str | None = None,
) -> ScenarioDraft:
    classification = response_class or classify_response(observation.text)
    draft_id = hashlib.sha1(
        f"response|{observation.observation_hash}".encode("utf-8")
    ).hexdigest()[:16]
    return ScenarioDraft(
        draft_id=draft_id,
        created_at=taipei_now_iso(),
        trigger_type=f"response_{classification}",
        source_sheets=("LINE_Watcher",),
        source_refs={
            "observation_hash": observation.observation_hash,
            "message_id": observation.message_id,
            "author": observation.author,
            "observed_at": observation.observed_at,
        },
        customer_id=observation.group_name,
        customer_name=observation.author,
        line_query=observation.group_name,
        line_contact=observation.group_name,
        product="",
        signal_summary=(
            f"Draft-only watcher classified an observed message as {classification}."
        ),
        draft_message=_response_template(classification),
        risk_level="medium" if classification in {"negative", "do_not_disturb"} else "low",
        safety_flags=("human_review_required",),
        result="watcher draft only; no automatic reply",
    )


def _response_template(response_class: str) -> str:
    templates = {
        "positive": "謝謝您的回覆，我已收到。後續會依您方便的方式整理重點，再請您確認。",
        "neutral": "謝謝您的回覆，我先記下來。若有需要，我可以再整理一份簡短重點供您參考。",
        "negative": "了解，謝謝您直接告知。我先不打擾，後續如有需要再與我聯絡即可。",
        "read_no_reply": "您好，補充確認您是否已收到前一則資訊；若目前不方便回覆也沒關係。",
        "order_intent": "謝謝您，我先依您提到的需求整理品項與數量，確認後再進行後續作業。",
        "material_request": "可以，我會整理適合的資料版本，先確認您想看產品重點、使用方式或活動資訊？",
        "event_interest": "謝謝您的興趣，我會整理活動時間、地點與內容重點，確認後再提供給您。",
        "do_not_disturb": "收到，我會停止後續主動訊息，謝謝您告知。",
    }
    return templates[response_class]


def _existing_values(path: Path, key: str) -> set[str]:
    if not path.exists():
        return set()
    values = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = str(json.loads(line).get(key) or "")
        except json.JSONDecodeError:
            continue
        if value:
            values.add(value)
    return values


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
