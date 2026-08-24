from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OWNER_PROJECTS = {"psr-aios-v1", "ARM", "line_edge_selenium", "easyflow", "CRM"}
OWNER_AGENTS = {"monitor", "diagnose", "repair", "summary", "delivery", "arbiter"}
SCOPES = {"browser", "queue_preview", "deployment", "message_delivery", "local_runtime"}
STATUSES = {"held", "released", "expired", "failed"}
LINE_DELIVERY_LOCKS = ("browser:line-primary", "delivery:line:hqming")


class LeaseValidationError(ValueError):
    """Raised when an agent lease cannot authorize the requested action."""


@dataclass(frozen=True)
class LeaseExpectation:
    lock_key: str | None = None
    owner_project: str | None = None
    owner_agent: str | None = None
    scope: str | None = None
    require_held: bool = True


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise LeaseValidationError("timestamp must be a non-empty string")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise LeaseValidationError(f"invalid timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise LeaseValidationError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def lease_filename(lock_key: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", lock_key.strip())
    if not safe:
        raise LeaseValidationError("lock_key must not be empty")
    return f"{safe}.json"


def lease_path(lease_dir: str | Path, lock_key: str) -> Path:
    return Path(lease_dir) / lease_filename(lock_key)


def read_lease(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LeaseValidationError(f"invalid lease json: {path}") from exc
    if not isinstance(data, dict):
        raise LeaseValidationError("lease document must be a JSON object")
    return data


def write_lease(path: str | Path, lease: dict[str, Any]) -> Path:
    validate_lease(lease, expectation=LeaseExpectation(require_held=False))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(lease, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def validate_lease(
    lease: dict[str, Any],
    *,
    expectation: LeaseExpectation | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    expectation = expectation or LeaseExpectation()
    required = {
        "lock_key",
        "owner_project",
        "owner_agent",
        "run_id",
        "host",
        "pid",
        "started_at",
        "expires_at",
        "scope",
        "reentrant",
        "status",
    }
    missing = sorted(required - set(lease))
    if missing:
        raise LeaseValidationError(f"missing lease fields: {', '.join(missing)}")

    _require_string(lease, "lock_key")
    _require_string(lease, "run_id")
    _require_string(lease, "host")
    _require_enum(lease, "owner_project", OWNER_PROJECTS)
    _require_enum(lease, "owner_agent", OWNER_AGENTS)
    _require_enum(lease, "scope", SCOPES)
    _require_enum(lease, "status", STATUSES)

    if not isinstance(lease["pid"], int) or lease["pid"] < 1:
        raise LeaseValidationError("pid must be a positive integer")
    if not isinstance(lease["reentrant"], bool):
        raise LeaseValidationError("reentrant must be a boolean")

    started_at = parse_timestamp(lease["started_at"])
    expires_at = parse_timestamp(lease["expires_at"])
    if expires_at <= started_at:
        raise LeaseValidationError("expires_at must be after started_at")

    current = now.astimezone(timezone.utc) if now else utc_now()
    if expectation.require_held and lease["status"] != "held":
        raise LeaseValidationError("lease status must be held")
    if expectation.require_held and expires_at <= current:
        raise LeaseValidationError("lease is expired")

    if expectation.lock_key and lease["lock_key"] != expectation.lock_key:
        raise LeaseValidationError("lease lock_key does not match requested action")
    if expectation.owner_project and lease["owner_project"] != expectation.owner_project:
        raise LeaseValidationError("lease owner_project does not match requested action")
    if expectation.owner_agent and lease["owner_agent"] != expectation.owner_agent:
        raise LeaseValidationError("lease owner_agent does not match requested action")
    if expectation.scope and lease["scope"] != expectation.scope:
        raise LeaseValidationError("lease scope does not match requested action")

    return lease


def require_line_delivery_leases(
    lease_dir: str | Path,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    expectations = (
        LeaseExpectation(
            lock_key="browser:line-primary",
            owner_project="line_edge_selenium",
            scope="browser",
        ),
        LeaseExpectation(
            lock_key="delivery:line:hqming",
            owner_project="line_edge_selenium",
            owner_agent="delivery",
            scope="message_delivery",
        ),
    )
    leases: list[dict[str, Any]] = []
    for expectation in expectations:
        path = lease_path(lease_dir, expectation.lock_key or "")
        if not path.exists():
            raise LeaseValidationError(f"missing required lease: {expectation.lock_key}")
        leases.append(validate_lease(read_lease(path), expectation=expectation, now=now))
    return leases


def _require_string(lease: dict[str, Any], field: str) -> None:
    if not isinstance(lease[field], str) or not lease[field].strip():
        raise LeaseValidationError(f"{field} must be a non-empty string")


def _require_enum(lease: dict[str, Any], field: str, allowed: set[str]) -> None:
    if lease[field] not in allowed:
        raise LeaseValidationError(f"{field} has unsupported value: {lease[field]}")


