from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from app.task_builder import MessageTask


@dataclass(frozen=True)
class RateLimitSettings:
    delay_min_seconds: int = 45
    delay_max_seconds: int = 120
    daily_message_quota: int = 20
    per_recipient_daily_quota: int = 1


class RandomDelay:
    def __init__(self, settings: RateLimitSettings) -> None:
        self.settings = settings

    def wait(
        self,
        *,
        heartbeat: Callable[[], None] | None = None,
        heartbeat_interval_seconds: float = 30.0,
    ) -> float:
        minimum = max(0, self.settings.delay_min_seconds)
        maximum = max(minimum, self.settings.delay_max_seconds)
        seconds = random.uniform(minimum, maximum)
        if heartbeat is None:
            time.sleep(seconds)
            return seconds

        interval = max(0.1, heartbeat_interval_seconds)
        deadline = time.monotonic() + seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))
            heartbeat()
        return seconds


class MessageQuota:
    def __init__(self, path: str | Path, settings: RateLimitSettings) -> None:
        self.path = Path(path)
        self.settings = settings

    def check(self, task: MessageTask, *, day: date) -> tuple[bool, str]:
        data = self._read()
        day_key = day.isoformat()
        query = task.query
        day_total = int(data.get("days", {}).get(day_key, {}).get("total", 0))
        recipient_total = int(
            data.get("recipients", {}).get(day_key, {}).get(query, 0)
        )
        if day_total >= self.settings.daily_message_quota:
            return False, f"daily quota reached: {day_total}"
        if recipient_total >= self.settings.per_recipient_daily_quota:
            return False, f"recipient quota reached for {query}: {recipient_total}"
        return True, "quota ok"

    def record(self, task: MessageTask, *, day: date, status: str) -> None:
        if status != "sent":
            return
        data = self._read()
        day_key = day.isoformat()
        data.setdefault("days", {}).setdefault(day_key, {"total": 0})
        data.setdefault("recipients", {}).setdefault(day_key, {})
        data["days"][day_key]["total"] = int(data["days"][day_key].get("total", 0)) + 1
        data["recipients"][day_key][task.query] = (
            int(data["recipients"][day_key].get(task.query, 0)) + 1
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {"days": {}, "recipients": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))
