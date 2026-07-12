from __future__ import annotations

import argparse
import json
import locale
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.project_health import (
    AUTOMATION_ID,
    PROJECT_HEALTH_TMP_DIR,
    append_line_attempt,
    build_gmail_payload,
    build_line_task,
    default_project_health_ledger,
    finalize_delivery_state,
    assert_project_health_task_safe,
    load_registry_validation,
    mark_gmail_sent,
    parse_orchestrator_output,
    project_health_paths,
    read_project_health_ledger,
    should_retry_line_attempt,
    summarize_handoff_result,
    write_project_health_ledger,
)
from app.task_builder import write_tasks

DEFAULT_PROJECT_ROOT = Path(r"C:\Dev\psr-gas")
DEFAULT_REGISTRY_PATH = DEFAULT_PROJECT_ROOT / "arm_webapp_registry.json"
DEFAULT_WORKER_START = ROOT / "automations" / "10_LINE_Message_Test" / "start_worker_hidden.ps1"
DEFAULT_WORKER_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PROXY_ENV_VARS = (
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "NO_PROXY",
    "no_proxy",
    "GIT_HTTP_PROXY",
    "GIT_HTTPS_PROXY",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate nightly ARM shared WebApp health report artifacts.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Taipei date in YYYY-MM-DD format.")
    parser.add_argument("--project-root", default=str(DEFAULT_PROJECT_ROOT))
    parser.add_argument("--registry-path", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--worker-python", default=str(DEFAULT_WORKER_PYTHON))
    parser.add_argument("--worker-start-script", default=str(DEFAULT_WORKER_START))
    parser.add_argument("--ledger-path", default="")
    parser.add_argument("--line-timeout-seconds", type=int, default=600)
    parser.add_argument("--skip-line", action="store_true")
    parser.add_argument("--mark-gmail-sent", action="store_true")
    parser.add_argument("--gmail-message-id", default="")
    return parser.parse_args(argv)


def run_command(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for name in PROXY_ENV_VARS:
        env.pop(name, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=False,
        check=False,
    )
    stdout = _decode_process_stream(completed.stdout)
    stderr = _decode_process_stream(completed.stderr)
    return subprocess.CompletedProcess(
        args=completed.args,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _decode_process_stream(data: bytes) -> str:
    encodings = [
        "utf-8",
        locale.getpreferredencoding(False) or "",
        "cp950",
    ]
    seen: set[str] = set()
    for encoding in encodings:
        if not encoding or encoding in seen:
            continue
        seen.add(encoding)
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_key_value_output(stdout_text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in stdout_text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def run_worker_status(worker_python: Path) -> dict[str, str]:
    completed = run_command([str(worker_python), "-m", "app.handoff_worker", "--status"], cwd=ROOT)
    output = parse_key_value_output(completed.stdout)
    output["_returncode"] = str(completed.returncode)
    output["_stderr"] = completed.stderr.strip()
    return output


def ensure_worker_live(worker_python: Path, start_script: Path) -> tuple[dict[str, str], dict[str, Any]]:
    first = run_worker_status(worker_python)
    precheck = {
        "initial_status": first,
        "startup_attempted": False,
        "startup_stdout": "",
        "startup_stderr": "",
    }
    if first.get("handoff_worker_live") == "true":
        return first, precheck

    precheck["startup_attempted"] = True
    started = run_command(
        [
            "powershell.exe",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(start_script),
        ],
        cwd=ROOT,
    )
    precheck["startup_stdout"] = started.stdout.strip()
    precheck["startup_stderr"] = started.stderr.strip()
    second = run_worker_status(worker_python)
    precheck["final_status"] = second
    return second, precheck


def run_probe(taipei_day: str, *, project_root: Path, registry_path: Path) -> tuple[Any, dict[str, Path]]:
    paths = project_health_paths(taipei_day)
    PROJECT_HEALTH_TMP_DIR.mkdir(parents=True, exist_ok=True)
    completed = run_command(["python", "tools\\arm_webapp_orchestrator.py", "--dry-run"], cwd=project_root)
    paths["stdout"].write_text(completed.stdout, encoding="utf-8")
    paths["stderr"].write_text(completed.stderr, encoding="utf-8")
    registry_ok, registry_projects, missing_projects, unexpected_projects = load_registry_validation(registry_path)
    summary = parse_orchestrator_output(
        taipei_day=taipei_day,
        stdout_text=completed.stdout,
        stderr_text=completed.stderr,
        exit_code=completed.returncode,
        registry_ok=registry_ok,
        registry_projects=registry_projects,
        missing_projects=missing_projects,
        unexpected_projects=unexpected_projects,
        stdout_path=str(paths["stdout"]),
        stderr_path=str(paths["stderr"]),
    )
    return summary, paths


def submit_line_request(worker_python: Path, task_path: Path) -> tuple[str, subprocess.CompletedProcess[str]]:
    completed = run_command(
        [
            str(worker_python),
            "-m",
            "app.handoff_worker",
            "--submit",
            "--send",
            "--tasks",
            str(task_path),
            "--per-recipient-quota",
            "2",
        ],
        cwd=ROOT,
    )
    fields = parse_key_value_output(completed.stdout)
    return fields.get("handoff_request", ""), completed


def wait_for_result(request_path: str, timeout_seconds: int) -> tuple[str, dict[str, Any]]:
    request = Path(request_path)
    deadline = time.monotonic() + timeout_seconds
    done_path = request.parent.parent / "done" / request.name
    error_path = request.parent.parent / "error" / request.name
    while time.monotonic() < deadline:
        if done_path.exists():
            return str(done_path), json.loads(done_path.read_text(encoding="utf-8"))
        if error_path.exists():
            return str(error_path), json.loads(error_path.read_text(encoding="utf-8"))
        time.sleep(1)
    return "", {}


def perform_line_delivery(
    *,
    ledger: dict[str, Any],
    worker_python: Path,
    start_script: Path,
    task_path: Path,
    timeout_seconds: int,
) -> None:
    line_state = ledger.setdefault("line", {})
    worker_status, precheck = ensure_worker_live(worker_python, start_script)
    line_state["worker_precheck"] = precheck

    if worker_status.get("handoff_worker_live") != "true":
        line_state["status"] = "worker_not_live"
        line_state["attempts"] = []
        ledger["final_delivery_state"] = finalize_delivery_state(ledger)
        return

    attempt_number = 0
    while attempt_number < 2:
        attempt_number += 1
        request_path, submit_completed = submit_line_request(worker_python, task_path)
        if not request_path:
            summary = {
                "final_status": "request_submit_failed",
                "final_phase": "worker_precheck",
                "sent_count": 0,
                "sent": False,
                "can_safe_retry": attempt_number == 1,
                "retry_reason": submit_completed.stderr.strip() or submit_completed.stdout.strip(),
            }
            append_line_attempt(
                ledger,
                attempt_number=attempt_number,
                request_path="",
                result_path="",
                audit_path="",
                summary=summary,
            )
        else:
            result_path, result = wait_for_result(request_path, timeout_seconds)
            if not result_path:
                summary = {
                    "final_status": "result_timeout",
                    "final_phase": "verify",
                    "sent_count": 0,
                    "sent": False,
                    "can_safe_retry": False,
                    "retry_reason": f"no result within {timeout_seconds} seconds",
                }
                append_line_attempt(
                    ledger,
                    attempt_number=attempt_number,
                    request_path=request_path,
                    result_path="",
                    audit_path="",
                    summary=summary,
                )
            else:
                audit_path = str(result.get("audit") or "")
                summary = summarize_handoff_result(result, audit_path)
                append_line_attempt(
                    ledger,
                    attempt_number=attempt_number,
                    request_path=request_path,
                    result_path=result_path,
                    audit_path=audit_path,
                    summary=summary,
                )
        if not should_retry_line_attempt(ledger):
            break
    ledger["final_delivery_state"] = finalize_delivery_state(ledger)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    taipei_day = str(args.date)
    worker_python = Path(args.worker_python)
    project_root = Path(args.project_root)
    registry_path = Path(args.registry_path)
    start_script = Path(args.worker_start_script)
    ledger_path_arg = Path(args.ledger_path) if args.ledger_path else None

    if ledger_path_arg and args.mark_gmail_sent:
        ledger = read_project_health_ledger(ledger_path_arg)
        mark_gmail_sent(ledger, message_id=args.gmail_message_id)
        write_project_health_ledger(ledger_path_arg, ledger)
        print(
            json.dumps(
                {
                    "automation_id": AUTOMATION_ID,
                    "ledger_path": str(ledger_path_arg),
                    "gmail": ledger["gmail"],
                    "line": ledger["line"],
                    "final_delivery_state": ledger["final_delivery_state"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    probe, paths = run_probe(taipei_day, project_root=project_root, registry_path=registry_path)
    worker_status = run_worker_status(worker_python)
    gmail_payload = build_gmail_payload(
        probe,
        worker_live=worker_status.get("handoff_worker_live") == "true",
        worker_status=worker_status.get("status", ""),
    )
    ledger = default_project_health_ledger(
        probe,
        registry_path=str(registry_path),
        project_root=str(project_root),
        gmail_payload=gmail_payload,
    )
    if args.mark_gmail_sent:
        mark_gmail_sent(ledger, message_id=args.gmail_message_id)

    task = build_line_task(
        probe,
        worker_live=worker_status.get("handoff_worker_live") == "true",
        worker_status=worker_status.get("status", ""),
    )
    try:
        assert_project_health_task_safe(task)
    except ValueError as exc:
        ledger["line"]["status"] = "blocked_mojibake"
        ledger["line"]["task_validation_error"] = str(exc)
        ledger["final_delivery_state"] = finalize_delivery_state(ledger)
        ledger_path = write_project_health_ledger(paths["ledger"], ledger)
        print(
            json.dumps(
                {
                    "automation_id": AUTOMATION_ID,
                    "ledger_path": str(ledger_path),
                    "task_path": "",
                    "gmail": ledger["gmail"],
                    "line": ledger["line"],
                    "final_delivery_state": ledger["final_delivery_state"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    task_path = write_tasks(paths["task"], [task])
    ledger["line"]["task_path"] = str(task_path)

    if not args.skip_line:
        perform_line_delivery(
            ledger=ledger,
            worker_python=worker_python,
            start_script=start_script,
            task_path=task_path,
            timeout_seconds=int(args.line_timeout_seconds),
        )
    else:
        ledger["line"]["status"] = "skipped"
        ledger["final_delivery_state"] = finalize_delivery_state(ledger)

    ledger_path = write_project_health_ledger(paths["ledger"], ledger)
    print(
        json.dumps(
            {
                "automation_id": AUTOMATION_ID,
                "ledger_path": str(ledger_path),
                "task_path": str(task_path),
                "gmail": ledger["gmail"],
                "line": ledger["line"],
                "final_delivery_state": ledger["final_delivery_state"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
