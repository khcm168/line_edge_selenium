from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REMINDER_TYPES = (
    "shipping",
    "feedback",
    "free_goods",
    "usage",
    "activity_followup",
    "repurchase",
    "app",
)


DEFAULT_RULES: dict[str, Any] = {
    "defaults": {
        "daily_message_quota": 20,
        "per_recipient_daily_quota": 1,
        "delay_min_seconds": 45,
        "delay_max_seconds": 120,
    },
    "reminders": {
        "shipping": {
            "enabled": True,
            "days": 1,
            "template": "{product}產品預計三個工作天({arrival_date})到貨，請留意",
        },
        "feedback": {
            "enabled": True,
            "days_after_delivery": 2,
            "template": "{product}使用後若有回饋或問題，請協助回覆，謝謝",
        },
        "free_goods": {
            "enabled": True,
            "template": "{product}贈品提醒，請協助確認是否已收到並完成後續使用安排",
        },
        "usage": {
            "enabled": True,
            "template": "{product}使用提醒：請依照適應症與建議劑量使用，如有疑問請回覆確認",
        },
        "activity_followup": {
            "enabled": True,
            "lookback_days": 14,
            "template": "{medical_unit}{activity_type}活動後續追蹤提醒，產品：{products}",
        },
        "repurchase": {
            "enabled": True,
            "days_after_sale": 30,
            "template": "{product}回購提醒，若需要補貨或安排後續服務，請回覆確認",
        },
        "app": {
            "enabled": True,
            "template": "免費下載 高峰健康御守",
        },
    },
}


@dataclass(frozen=True)
class ReminderRules:
    data: dict[str, Any]

    @classmethod
    def load(cls, path: str | Path) -> "ReminderRules":
        target = Path(path)
        if not target.exists():
            return cls(DEFAULT_RULES)
        loaded = json.loads(target.read_text(encoding="utf-8"))
        merged = _deep_merge(DEFAULT_RULES, loaded)
        return cls(merged)

    def enabled(self, reminder_type: str) -> bool:
        return bool(self.reminder(reminder_type).get("enabled", False))

    def reminder(self, reminder_type: str) -> dict[str, Any]:
        return dict(self.data.get("reminders", {}).get(reminder_type, {}))

    def template(self, reminder_type: str) -> str:
        return str(self.reminder(reminder_type).get("template", "")).strip()

    def default_int(self, name: str, default: int) -> int:
        value = self.data.get("defaults", {}).get(name, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


def write_default_rules(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(
            json.dumps(DEFAULT_RULES, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return target


def normalize_types(value: str) -> tuple[str, ...]:
    if not value or value == "all":
        return REMINDER_TYPES
    selected = tuple(item.strip() for item in value.split(",") if item.strip())
    unknown = [item for item in selected if item not in REMINDER_TYPES]
    if unknown:
        raise ValueError(f"Unsupported reminder type(s): {', '.join(unknown)}")
    return selected


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in base.items():
        result[key] = _deep_merge(value, {}) if isinstance(value, dict) else value
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
