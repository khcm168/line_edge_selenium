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
            "template": "{product} 預計三個工作天（{arrival_date}）到貨，先跟您提醒，請再留意一下。",
        },
        "feedback": {
            "enabled": True,
            "days_after_delivery": 2,
            "template": "{product} 應該已經收到一陣子了，想跟您確認使用上是否都順利；若有需要，我也可以再補充簡短說明。",
        },
        "free_goods": {
            "enabled": True,
            "template": "{product} 贈品或搭配品項想再跟您確認一下，方便的話請幫我看是否已經收到、數量是否正確。",
        },
        "usage": {
            "enabled": True,
            "template": "{product} 使用上小提醒：建議依照既有建議方式持續觀察狀態；若想要我整理重點給您，我可以再補一版簡短說明。",
        },
        "activity_followup": {
            "enabled": True,
            "lookback_days": 14,
            "template": "謝謝 {medical_unit} 近期參與 {activity_type}。想跟您簡單追蹤後續狀況，也確認 {products} 是否有需要我再補充資料。",
        },
        "repurchase": {
            "enabled": True,
            "days_after_sale": 30,
            "template": "{product} 先前購買到現在約一個月，想關心目前庫存是否還足夠；若需要，我可以協助確認下一次備貨。",
        },
        "app": {
            "enabled": True,
            "template": "小提醒：若您方便，也可以透過 App 查看相關紀錄或更新資訊；有任何操作問題我再協助您。",
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
