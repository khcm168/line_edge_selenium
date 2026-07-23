from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from app.config import ROOT
from app.task_builder import MessageTask


EXPECTED_PROJECTS = (
    "psr-aios-v1",
    "ARM",
    "line_edge_selenium",
    "easyflow",
)
LINE_TARGET_QUERY = "洪啓明"
LINE_TARGET_POLICY = "exact_friend"
LINE_TARGET_CUSTOMER_ID = "nightly_project_health"
AUTOMATION_ID = "line"
GMAIL_SELF_ADDRESS = "khcm168@gmail.com"
PROJECT_HEALTH_DIR = ROOT / "data" / "project_health"
PROJECT_HEALTH_TASK_DIR = ROOT / "data" / "tasks"
PROJECT_HEALTH_TMP_DIR = ROOT / "data" / "tmp"
LINE_SAFE_RETRY_STATUSES = {
    "no_match",
    "ambiguous",
    "composer_missing",
    "current_chat_missing",
    "current_chat_mismatch",
    "login_state_failed",
    "search_box_missing",
    "request_submit_failed",
    "worker_not_live",
    "worker_start_failed",
    "worker_status_failed",
    "result_timeout",
}
MOJIBAKE_MARKERS = ("???", "\ufffd")


@dataclass(frozen=True)
class ProbeProjectStatus:
    name: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class ProbeSummary:
    taipei_date: str
    registry_ok: bool
    registry_projects: tuple[str, ...]
    missing_projects: tuple[str, ...]
    unexpected_projects: tuple[str, ...]
    orchestrator_exit_code: int
    api_version: str
    webapp_release: str
    run_id: str
    audit_log_row: str
    summary_status: str
    summary_reason: str
    projects: tuple[ProbeProjectStatus, ...] = field(default_factory=tuple)
    stdout_path: str = ""
    stderr_path: str = ""


PROJECT_STATUS_LABELS = {
    "passed": "通過",
    "failed": "失敗",
    "not_run": "未執行",
    "unknown": "未回報",
}


def project_health_paths(taipei_day: str) -> dict[str, Path]:
    return {
        "ledger": PROJECT_HEALTH_DIR / f"{taipei_day}.json",
        "task": PROJECT_HEALTH_TASK_DIR / f"project_health_{taipei_day}.json",
        "stdout": PROJECT_HEALTH_TMP_DIR / f"project_health_{taipei_day}_orchestrator_stdout.txt",
        "stderr": PROJECT_HEALTH_TMP_DIR / f"project_health_{taipei_day}_orchestrator_stderr.txt",
    }


def load_registry_validation(registry_path: str | Path) -> tuple[bool, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    data = json.loads(Path(registry_path).read_text(encoding="utf-8-sig").lstrip("\ufeff"))
    projects = tuple(
        str(project.get("name") or "")
        for project in data.get("projects", [])
        if isinstance(project, dict) and project.get("name")
    )
    expected = set(EXPECTED_PROJECTS)
    current = set(projects)
    missing = tuple(name for name in EXPECTED_PROJECTS if name not in current)
    unexpected = tuple(name for name in projects if name not in expected)
    owner_ok = (
        data.get("ownerRepo") == "psr-gas"
        and data.get("releaseWorkflow") == "tools/arm_webapp_release.py"
    )
    ok = not missing and not unexpected and len(projects) == len(EXPECTED_PROJECTS) and owner_ok
    return ok, projects, missing, unexpected


def parse_orchestrator_output(
    *,
    taipei_day: str,
    stdout_text: str,
    stderr_text: str,
    exit_code: int,
    registry_ok: bool,
    registry_projects: tuple[str, ...],
    missing_projects: tuple[str, ...],
    unexpected_projects: tuple[str, ...],
    stdout_path: str = "",
    stderr_path: str = "",
) -> ProbeSummary:
    project_statuses: dict[str, ProbeProjectStatus] = {
        name: ProbeProjectStatus(name=name, status="unknown", detail="probe not reported")
        for name in EXPECTED_PROJECTS
    }
    api_version = ""
    release = ""
    run_id = ""
    audit_log_row = ""
    error_lines: list[str] = []
    fail_lines: list[str] = []
    release_mismatch: tuple[str, str] | None = None
    saw_probe_line = False
    saw_status_line = False

    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        ok_match = re.search(r"Live ARM Shared WebApp API\s+([^\s]+)\s+release\s+([^\s]+)", line)
        if ok_match:
            api_version = ok_match.group(1)
            release = ok_match.group(2)

        passed_match = re.match(r"\[(PASSED|FAILED)\]\s+([^:]+):\s*(.*)", line)
        if passed_match:
            saw_status_line = True
            status_text, project_name, detail = passed_match.groups()
            project_statuses[project_name] = ProbeProjectStatus(
                name=project_name,
                status="passed" if status_text == "PASSED" else "failed",
                detail=detail.strip(),
            )
            continue

        probe_match = re.match(r"\[PROBE\]\s+([^:]+):\s*(.*)", line)
        if probe_match:
            saw_probe_line = True
            project_name, detail = probe_match.groups()
            if project_name in project_statuses and project_statuses[project_name].status == "unknown":
                project_statuses[project_name] = ProbeProjectStatus(
                    name=project_name,
                    status="not_run",
                    detail=detail.strip() or "probe started but no final status reported",
                )
            continue

        run_match = re.search(r"\brunId=([A-Za-z0-9-]+)", line)
        if run_match:
            run_id = run_match.group(1)

        log_match = re.search(r"\bLOG row\b[^0-9]*([0-9]+)", line, re.IGNORECASE)
        if log_match:
            audit_log_row = log_match.group(1)

        error_match = re.match(r"\[ERROR\]\s+(.*)", line)
        if error_match:
            error_lines.append(error_match.group(1).strip())

        fail_match = re.match(r"\[FAIL\]\s+(.*)", line)
        if fail_match:
            fail_text = fail_match.group(1).strip()
            fail_lines.append(fail_text)
            release_match = re.search(
                r"health releaseVersion=([^\s;]+);\s+expected\s+([^\s;]+)",
                fail_text,
            )
            if release_match:
                live_release = release_match.group(1).strip("'\"")
                registry_release = release_match.group(2).strip("'\"")
                release = live_release
                release_mismatch = (live_release, registry_release)

    if not audit_log_row:
        json_log_match = re.search(r'"logRow"\s*:\s*([0-9]+)', stdout_text)
        if json_log_match:
            audit_log_row = json_log_match.group(1)

    if not run_id:
        stderr_run_match = re.search(r"\brunId=([A-Za-z0-9-]+)", stderr_text)
        if stderr_run_match:
            run_id = stderr_run_match.group(1)

    if exit_code != 0 and not saw_probe_line and not saw_status_line:
        project_statuses = {
            name: ProbeProjectStatus(
                name=name,
                status="not_run",
                detail="orchestrator stopped before project probes ran",
            )
            for name in EXPECTED_PROJECTS
        }

    if not registry_ok:
        reason = (
            "CONFIG FAIL: arm_webapp_registry.json must be the canonical psr-gas registry "
            "and contain exactly psr-aios-v1, ARM, line_edge_selenium, easyflow"
        )
        summary_status = "red"
    elif release_mismatch:
        live_release, registry_release = release_mismatch
        reason = (
            "CONFIG FAIL: psr-gas canonical registry/deploy mismatch; "
            f"live release {live_release} != registry {registry_release}; "
            "release workflow incomplete"
        )
        summary_status = "red"
    elif exit_code != 0:
        reason = error_lines[0] if error_lines else fail_lines[0] if fail_lines else f"orchestrator exit code {exit_code}"
        summary_status = "red"
    else:
        failed_projects = [status for status in project_statuses.values() if status.status == "failed"]
        if failed_projects:
            reason = f"{failed_projects[0].name}: {failed_projects[0].detail or 'probe failed'}"
            summary_status = "red"
        else:
            reason = ""
            summary_status = "green"

    return ProbeSummary(
        taipei_date=taipei_day,
        registry_ok=registry_ok,
        registry_projects=registry_projects,
        missing_projects=missing_projects,
        unexpected_projects=unexpected_projects,
        orchestrator_exit_code=exit_code,
        api_version=api_version,
        webapp_release=release,
        run_id=run_id,
        audit_log_row=audit_log_row,
        summary_status=summary_status,
        summary_reason=reason,
        projects=tuple(project_statuses[name] for name in EXPECTED_PROJECTS),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def build_line_message(
    probe: ProbeSummary,
    *,
    worker_live: bool,
    worker_status: str,
) -> str:
    overall = "綠燈" if probe.summary_status == "green" else "紅燈"
    lines = [
        f"【每日專案健康報告 {probe.taipei_date}】",
        f"整體：{overall}",
    ]
    for project in probe.projects:
        label = PROJECT_STATUS_LABELS.get(project.status, project.status)
        lines.append(f"{project.name}：{label}")
    lines.append(f"WebApp release：{probe.webapp_release or '未取得'}")
    audit_bits = [
        f"LOG row {probe.audit_log_row}" if probe.audit_log_row else "LOG row 未取得",
        f"runId {probe.run_id}" if probe.run_id else "runId 未取得",
    ]
    lines.append(f"Audit：{' / '.join(audit_bits)}")
    if probe.summary_reason:
        lines.append(f"原因：{probe.summary_reason}")
    lines.append(f"LINE worker：live={str(worker_live).lower()} / {worker_status or 'unknown'}")
    return "\n".join(lines)


def build_gmail_payload(
    probe: ProbeSummary,
    *,
    worker_live: bool,
    worker_status: str,
) -> dict[str, str]:
    return {
        "to": GMAIL_SELF_ADDRESS,
        "subject": f"【每日專案健康報告 {probe.taipei_date}】",
        "body": build_line_message(probe, worker_live=worker_live, worker_status=worker_status),
    }


def build_line_task(
    probe: ProbeSummary,
    *,
    worker_live: bool,
    worker_status: str,
) -> MessageTask:
    return MessageTask(
        action="send_message",
        query=LINE_TARGET_QUERY,
        match_policy=LINE_TARGET_POLICY,
        message=build_line_message(probe, worker_live=worker_live, worker_status=worker_status),
        allow_group=False,
        customer_id=LINE_TARGET_CUSTOMER_ID,
        line_contact=LINE_TARGET_QUERY,
        source={
            "automation_id": AUTOMATION_ID,
            "kind": "nightly_project_health",
            "taipei_date": probe.taipei_date,
            "orchestrator_exit_code": probe.orchestrator_exit_code,
            "webapp_release": probe.webapp_release,
            "audit_log_row": probe.audit_log_row,
            "run_id": probe.run_id,
            "summary_status": probe.summary_status,
            "summary_reason": probe.summary_reason,
            "worker_live": worker_live,
            "worker_status": worker_status,
        },
        reminder_type="nightly_project_health",
        due_date=probe.taipei_date,
        quota_key=f"project_health:all:{probe.taipei_date}",
        manual_required=False,
    )


def project_health_task_mojibake_fields(task: MessageTask) -> tuple[str, ...]:
    fields = {
        "query": task.query,
        "line_contact": task.line_contact,
        "message": task.message,
    }
    if task.source:
        fields["source.summary_reason"] = str(task.source.get("summary_reason") or "")
    return tuple(
        name
        for name, value in fields.items()
        if _looks_mojibake(str(value or ""))
    )


def assert_project_health_task_safe(task: MessageTask) -> None:
    bad_fields = project_health_task_mojibake_fields(task)
    if bad_fields:
        raise ValueError(
            "Refusing to submit nightly project health LINE task because "
            f"mojibake was detected in: {', '.join(bad_fields)}"
        )


def _looks_mojibake(text: str) -> bool:
    return any(marker in text for marker in MOJIBAKE_MARKERS)


def default_project_health_ledger(
    probe: ProbeSummary,
    *,
    registry_path: str,
    project_root: str,
    gmail_payload: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "taipei_date": probe.taipei_date,
        "report_generated": True,
        "final_delivery_state": "report_only",
        "probe": asdict(probe),
        "registry_path": registry_path,
        "project_root": project_root,
        "gmail": {
            "status": "pending_external_send",
            **gmail_payload,
            "message_id": "",
        },
        "line": {
            "status": "not_started",
            "safe_retry_used": False,
            "attempts": [],
        },
    }


def read_project_health_ledger(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_project_health_ledger(path: str | Path, ledger: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def finalize_delivery_state(ledger: dict[str, Any]) -> str:
    gmail_status = str(ledger.get("gmail", {}).get("status") or "")
    line_status = str(ledger.get("line", {}).get("status") or "")
    if gmail_status == "sent" and line_status == "sent":
        return "gmail_sent_line_sent"
    if gmail_status == "sent":
        return "gmail_sent_line_skipped"
    if gmail_status == "failed":
        return "delivery_failed"
    if line_status in {
        "sent",
        "retryable_failure",
        "blocked_uncertain",
        "worker_not_live",
        "blocked_mojibake",
    }:
        return "delivery_failed"
    if ledger.get("report_generated"):
        return "report_only"
    return "delivery_failed"


def mark_gmail_sent(ledger: dict[str, Any], *, message_id: str = "") -> None:
    gmail = ledger.setdefault("gmail", {})
    gmail["status"] = "sent"
    gmail["message_id"] = message_id
    ledger["final_delivery_state"] = finalize_delivery_state(ledger)


def summarize_handoff_result(result: dict[str, Any], audit_path: str = "") -> dict[str, Any]:
    summary = result.get("summary")
    if isinstance(summary, dict) and summary:
        return summary

    sent_count = 0
    final_status = "unknown"
    final_phase = "request"
    last_detail = ""
    if audit_path and Path(audit_path).exists():
        for line in Path(audit_path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            final_status = str(record.get("status") or final_status)
            final_phase = str(record.get("phase") or final_phase)
            last_detail = str(record.get("detail") or last_detail)
            if final_status == "sent":
                sent_count += 1
    error_text = str(result.get("error") or "")
    if error_text and "InvalidSessionIdException" in error_text and sent_count == 0:
        final_status = "invalid_session_before_send"
        final_phase = "open_chat"
        last_detail = error_text

    can_safe_retry = sent_count == 0 and final_status in LINE_SAFE_RETRY_STATUSES | {"invalid_session_before_send"}
    return {
        "final_status": final_status,
        "final_phase": final_phase,
        "sent_count": sent_count,
        "sent": sent_count > 0,
        "can_safe_retry": can_safe_retry,
        "retry_reason": last_detail if can_safe_retry else "",
    }


def append_line_attempt(
    ledger: dict[str, Any],
    *,
    attempt_number: int,
    request_path: str,
    result_path: str,
    audit_path: str,
    summary: dict[str, Any],
) -> None:
    line_state = ledger.setdefault("line", {})
    attempts = line_state.setdefault("attempts", [])
    attempts.append(
        {
            "attempt_number": attempt_number,
            "request_path": request_path,
            "result_path": result_path,
            "audit_path": audit_path,
            "summary": summary,
        }
    )
    if summary.get("sent"):
        line_state["status"] = "sent"
    elif summary.get("can_safe_retry"):
        line_state["status"] = "retryable_failure"
    else:
        line_state["status"] = "blocked_uncertain"
    line_state["safe_retry_used"] = len(attempts) > 1
    ledger["final_delivery_state"] = finalize_delivery_state(ledger)


def should_retry_line_attempt(ledger: dict[str, Any]) -> bool:
    line_state = ledger.get("line", {})
    attempts = line_state.get("attempts", [])
    if len(attempts) != 1:
        return False
    summary = attempts[0].get("summary") or {}
    return bool(summary.get("can_safe_retry")) and not bool(summary.get("sent"))


def task_due_date(task: MessageTask) -> date:
    return date.fromisoformat(task.due_date)
