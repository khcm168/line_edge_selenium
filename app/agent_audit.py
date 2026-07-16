from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audit import append_jsonl

PROJECTS = {"psr-aios-v1", "ARM", "line_edge_selenium", "easyflow", "CRM"}
AGENTS = {"monitor", "diagnose", "repair", "summary", "delivery", "arbiter"}
EVENTS = {
    "probe_started",
    "probe_finished",
    "lease_checked",
    "repair_attempted",
    "repair_succeeded",
    "repair_failed",
    "delivery_blocked",
    "summary_emitted",
}
STATUSES = {"ok", "warn", "error", "blocked"}
SCOPES = {
    "project_local",
    "shared_config",
    "shared_runtime",
    "external_dependency",
    "human_required",
}


class AgentAuditError(ValueError):
    """Raised when an agent audit event is not schema-compatible."""


def build_agent_audit_event(
    *,
    project: str,
    agent: str,
    run_id: str,
    event: str,
    status: str,
    scope: str,
    reason_code: str,
    detail_short: str,
    lock_key: str = "",
    host: str = "Z13",
    ts: str | None = None,
) -> dict[str, Any]:
    record = {
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "host": host,
        "project": project,
        "agent": agent,
        "run_id": run_id,
        "event": event,
        "status": status,
        "scope": scope,
        "reason_code": reason_code,
        "detail_short": detail_short,
    }
    if lock_key:
        record["lock_key"] = lock_key
    validate_agent_audit_event(record)
    return record


def validate_agent_audit_event(record: dict[str, Any]) -> dict[str, Any]:
    required = {
        "ts",
        "host",
        "project",
        "agent",
        "run_id",
        "event",
        "status",
        "scope",
        "reason_code",
        "detail_short",
    }
    missing = sorted(required - set(record))
    if missing:
        raise AgentAuditError(f"missing audit fields: {', '.join(missing)}")

    _require_string(record, "ts")
    _require_string(record, "host")
    _require_string(record, "run_id")
    _require_string(record, "reason_code")
    _require_string(record, "detail_short")
    _require_enum(record, "project", PROJECTS)
    _require_enum(record, "agent", AGENTS)
    _require_enum(record, "event", EVENTS)
    _require_enum(record, "status", STATUSES)
    _require_enum(record, "scope", SCOPES)

    if "lock_key" in record and not isinstance(record["lock_key"], str):
        raise AgentAuditError("lock_key must be a string")
    return record


def append_agent_audit_event(path: str | Path, record: dict[str, Any]) -> Path:
    validate_agent_audit_event(record)
    return append_jsonl(path, record)


def _require_string(record: dict[str, Any], field: str) -> None:
    if not isinstance(record[field], str) or not record[field].strip():
        raise AgentAuditError(f"{field} must be a non-empty string")


def _require_enum(record: dict[str, Any], field: str, allowed: set[str]) -> None:
    if record[field] not in allowed:
        raise AgentAuditError(f"{field} has unsupported value: {record[field]}")



