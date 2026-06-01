from __future__ import annotations

import json
from dataclasses import is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def json_safe(value: Any) -> Any:
    if is_dataclass(value):
        data = {
            field: getattr(value, field)
            for field in value.__dataclass_fields__
            if field != "element"
        }
        return json_safe(data)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def append_jsonl(path: str | Path, record: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(json_safe(record), ensure_ascii=False, sort_keys=True))
        handle.write("\n")
    return target


def build_audit_record(
    *,
    action: str,
    status: str,
    query: str = "",
    policy: str = "",
    message: str = "",
    detail: str = "",
    source: dict[str, Any] | None = None,
    candidates: list[Any] | None = None,
    selected: Any = None,
    snapshot: str | Path | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "status": status,
        "query": query,
        "policy": policy,
        "message": message,
        "detail": detail,
        "source": source or {},
        "candidates": json_safe(candidates or []),
        "selected": json_safe(selected),
        "snapshot": str(snapshot) if snapshot else "",
    }


class SnapshotWriter:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        *,
        label: str,
        payload: dict[str, Any],
        driver: Any | None = None,
    ) -> Path:
        safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)
        base = self.root / f"{utc_stamp()}_{safe_label}"
        data = dict(payload)
        if driver is not None:
            screenshot_path = base.with_suffix(".png")
            try:
                driver.save_screenshot(str(screenshot_path))
                data["screenshot"] = str(screenshot_path)
            except Exception as exc:
                data["screenshot_error"] = type(exc).__name__
            try:
                data["url"] = driver.current_url
                data["title"] = driver.title
            except Exception:
                pass
        json_path = base.with_suffix(".json")
        json_path.write_text(
            json.dumps(json_safe(data), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return json_path
