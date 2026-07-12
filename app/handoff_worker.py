from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.audit import SnapshotWriter, append_jsonl, build_audit_record, utc_stamp
from app.config import Settings
from app.line_batch import _run_task, _validate_live_scope
from app.line_client import LineClient
from app.project_health import summarize_handoff_result
from app.rate_limiter import MessageQuota, RandomDelay, RateLimitSettings
from app.reminder_rules import ReminderRules
from app.task_builder import MessageTask, build_test_tasks, read_tasks
from app.ui_health import check_login_state, check_search_box
from login_probe import edge_profile_dir, prepare_edge_profile_dir


POLL_SECONDS = 1.0
HEARTBEAT_STALE_SECONDS = 180.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persistent LINE handoff worker.")
    parser.add_argument("--submit", action="store_true", help="Submit a request to the running worker.")
    parser.add_argument("--stop", action="store_true", help="Ask the running worker to stop.")
    parser.add_argument("--status", action="store_true", help="Show persistent worker status.")
    parser.add_argument(
        "--observe",
        action="store_true",
        help="Submit a passive screenshot/state observation without sending.",
    )
    parser.add_argument("--tasks", help="Task JSON file to submit.")
    parser.add_argument("--test-targets", action="store_true", help="Submit smoke-test targets.")
    parser.add_argument("--manual-approve", action="store_true", help="Open matched chat and stop before sending.")
    parser.add_argument("--send", action="store_true", help="Ask worker to live-send.")
    parser.add_argument("--delay-min-seconds", type=int)
    parser.add_argument("--delay-max-seconds", type=int)
    parser.add_argument("--per-recipient-quota", type=int)
    parser.add_argument("--daily-message-quota", type=int)
    parser.add_argument(
        "--reclaim-stale-owner",
        action="store_true",
        help="Clear only a dead handoff worker's ownership metadata and stale profile markers.",
    )
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    handoff_dir = settings.task_dir.parent / "handoff"
    inbox = handoff_dir / "inbox"
    done = handoff_dir / "done"
    errors = handoff_dir / "error"
    state_path = handoff_dir / "worker_state.json"
    owner_path = handoff_dir / "worker_owner.json"
    inbox.mkdir(parents=True, exist_ok=True)
    done.mkdir(parents=True, exist_ok=True)
    errors.mkdir(parents=True, exist_ok=True)

    if args.status:
        return print_worker_status(state_path)

    if args.reclaim_stale_owner:
        return print_reclaim_result(
            reclaim_stale_owner(
                owner_path=owner_path,
                state_path=state_path,
                profile_dir=edge_profile_dir(),
            )
        )

    if args.submit or args.stop or args.observe:
        request_path = submit_request(args=args, inbox=inbox)
        print(f"handoff_request={request_path}")
        print("handoff_worker_must_be_running=true")
        return 0

    return run_worker(
        settings=settings,
        inbox=inbox,
        done=done,
        errors=errors,
        state_path=state_path,
        owner_path=owner_path,
    )


def submit_request(*, args: argparse.Namespace, inbox: Path) -> Path:
    request = {
        "id": uuid4().hex,
        "created_at": utc_stamp(),
        "stop": args.stop,
        "observe": args.observe,
        "tasks": str(Path(args.tasks)) if args.tasks else "",
        "test_targets": args.test_targets,
        "manual_approve": args.manual_approve,
        "send": args.send,
        "delay_min_seconds": args.delay_min_seconds,
        "delay_max_seconds": args.delay_max_seconds,
        "per_recipient_quota": args.per_recipient_quota,
        "daily_message_quota": args.daily_message_quota,
    }
    path = inbox / f"{request['created_at']}_{request['id']}.json"
    path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_worker(
    *,
    settings: Settings,
    inbox: Path,
    done: Path,
    errors: Path,
    state_path: Path,
    owner_path: Path,
) -> int:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    write_worker_state(state_path, status="starting")
    write_worker_owner(owner_path)
    client = None
    try:
        client = LineClient.open()
        client.driver.maximize_window()
        health = check_login_state(client)
        if not health.ok:
            snapshot_writer = SnapshotWriter(settings.snapshot_dir)
            snapshot = snapshot_writer.write(
                label="handoff_login_state_failed",
                payload={"health": health, "visible_text": client.visible_text()[:3000]},
                driver=client.driver,
            )
            append_jsonl(
                settings.log_dir / f"line_handoff_health_{utc_stamp()}.jsonl",
                build_audit_record(
                    action="ui_health",
                    status=health.status,
                    detail=health.detail,
                    snapshot=snapshot,
                ),
            )
            raise RuntimeError(health.detail)
        search_health = check_search_box(client.driver)
        if not search_health.ok:
            snapshot_writer = SnapshotWriter(settings.snapshot_dir)
            snapshot = snapshot_writer.write(
                label="handoff_search_box_missing",
                payload={"health": search_health, "visible_text": client.visible_text()[:3000]},
                driver=client.driver,
            )
            append_jsonl(
                settings.log_dir / f"line_handoff_health_{utc_stamp()}.jsonl",
                build_audit_record(
                    action="ui_health",
                    status=search_health.status,
                    detail=search_health.detail,
                    snapshot=snapshot,
                ),
            )
            raise RuntimeError(search_health.detail)
        write_worker_state(state_path, status="idle")
        print("handoff_worker_ready=true", flush=True)
        print(f"handoff_inbox={inbox}", flush=True)
        while True:
            write_worker_state(state_path, status="idle")
            request_path = next_request(inbox)
            if request_path is None:
                time.sleep(POLL_SECONDS)
                continue
            write_worker_state(
                state_path,
                status="processing",
                request=request_path.name,
            )
            should_stop = handle_request(
                request_path=request_path,
                done=done,
                errors=errors,
                settings=settings,
                client=client,
                state_path=state_path,
            )
            if should_stop:
                print("handoff_worker_stopping=true", flush=True)
                return 0
    except Exception as exc:
        write_worker_state(
            state_path,
            status="error",
            detail=f"{type(exc).__name__}: {exc}",
        )
        raise
    finally:
        try:
            if client is not None:
                client.close()
        finally:
            current = read_worker_state(state_path)
            if current.get("status") != "error":
                write_worker_state(state_path, status="stopped")
            clear_worker_owner(owner_path)


def next_request(inbox: Path) -> Path | None:
    requests = sorted(inbox.glob("*.json"), key=lambda path: path.name)
    return requests[0] if requests else None


def handle_request(
    *,
    request_path: Path,
    done: Path,
    errors: Path,
    settings: Settings,
    client: LineClient,
    state_path: Path,
) -> bool:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    result = {
        "request": request,
        "started_at": utc_stamp(),
        "status": "started",
        "audit": "",
        "error": "",
        "summary": {},
    }
    try:
        if request.get("stop"):
            result["status"] = "stopped"
            result["summary"] = {
                "final_status": "stopped",
                "final_phase": "worker_precheck",
                "sent_count": 0,
                "sent": False,
                "can_safe_retry": False,
                "retry_reason": "",
            }
            return True

        if request.get("observe"):
            audit_path = settings.log_dir / (
                f"line_handoff_observe_{utc_stamp()}_{request['id']}.jsonl"
            )
            snapshot_writer = SnapshotWriter(settings.snapshot_dir)
            snapshot = snapshot_writer.write(
                label="handoff_observation",
                payload={
                    "request": request,
                    "visible_text": client.visible_text()[:5000],
                    "search_health": check_search_box(client.driver),
                },
                driver=client.driver,
            )
            append_jsonl(
                audit_path,
                build_audit_record(
                    action="observe",
                    status="captured",
                    detail="Passive LINE state captured; no message action attempted.",
                    source={"request_id": request["id"]},
                    snapshot=snapshot,
                ),
            )
            result["status"] = "ok"
            result["audit"] = str(audit_path)
            result["summary"] = {
                "final_status": "observe_captured",
                "final_phase": "worker_precheck",
                "sent_count": 0,
                "sent": False,
                "can_safe_retry": False,
                "retry_reason": "",
            }
            return False

        tasks = load_request_tasks(request)
        _validate_live_scope(tasks, send=bool(request.get("send")), settings=settings)
        rules = ReminderRules.load(settings.reminder_rules_path)
        rate_settings = request_rate_settings(
            request,
            defaults=RateLimitSettings(
            delay_min_seconds=rules.default_int("delay_min_seconds", 45),
            delay_max_seconds=rules.default_int("delay_max_seconds", 120),
            daily_message_quota=rules.default_int("daily_message_quota", 20),
            per_recipient_daily_quota=rules.default_int("per_recipient_daily_quota", 1),
            ),
        )
        quota = MessageQuota(settings.task_dir.parent / "handoff" / "quota.json", rate_settings)
        delay = RandomDelay(rate_settings)
        audit_path = settings.log_dir / f"line_handoff_{utc_stamp()}_{request['id']}.jsonl"
        snapshot_writer = SnapshotWriter(settings.snapshot_dir)
        for index, task in enumerate(tasks):
            if request.get("send"):
                allowed, detail = quota.check(task, day=date.today())
                if not allowed:
                    append_jsonl(
                        audit_path,
                        build_audit_record(
                            action=task.action,
                            status="quota_blocked",
                            query=task.query,
                            policy=task.match_policy,
                            message=task.message,
                            detail=detail,
                            source=task.source,
                        ),
                    )
                    raise RuntimeError(detail)
                if index > 0:
                    waited = delay.wait(
                        heartbeat=lambda: write_worker_state(
                            state_path,
                            status="processing",
                            request=request_path.name,
                        )
                    )
                    append_jsonl(
                        audit_path,
                        build_audit_record(
                            action="rate_limit_delay",
                            status="waited",
                            query=task.query,
                            detail=f"waited {waited:.1f} seconds",
                            source={"request_id": request["id"]},
                        ),
                    )
            status = _run_task(
                client=client,
                task=task,
                send=bool(request.get("send")),
                manual_approve=bool(request.get("manual_approve")),
                settings=settings,
                audit_path=audit_path,
                snapshot_writer=snapshot_writer,
            )
            quota.record(task, day=date.today(), status=status)
            if request.get("manual_approve"):
                break
        result["status"] = "ok"
        result["audit"] = str(audit_path)
        result["summary"] = summarize_handoff_result(result, str(audit_path))
        return False
    except Exception as exc:
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
        append_jsonl(
            settings.log_dir / f"line_handoff_error_{utc_stamp()}.jsonl",
                build_audit_record(
                    action="handoff_request",
                    status="error",
                    phase="request",
                    detail=result["error"],
                    source={"request": request},
                ),
            )
        result["summary"] = summarize_handoff_result(result, str(result.get("audit") or ""))
        return False
    finally:
        result["finished_at"] = utc_stamp()
        result_dir = errors if result.get("status") == "error" else done
        result_path = result_dir / request_path.name
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            request_path.unlink()
        except OSError:
            pass
        print(f"handoff_result={result_path}", flush=True)


def load_request_tasks(request: dict[str, object]) -> list[MessageTask]:
    if request.get("test_targets"):
        return build_test_tasks()
    task_path = str(request.get("tasks") or "")
    if not task_path:
        raise ValueError("Handoff request requires --tasks or --test-targets.")
    return read_tasks(task_path)


def write_worker_state(
    path: Path,
    *,
    status: str,
    request: str = "",
    detail: str = "",
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    previous = read_worker_state(path)
    payload = {
        "pid": os.getpid(),
        "started_at": previous.get("started_at") or now,
        "heartbeat_at": now,
        "status": status,
        "request": request,
        "detail": detail,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp"
    )
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                break
            time.sleep(0.05)
    try:
        temporary.unlink()
    except OSError:
        pass
    print(
        f"handoff_state_warning=unable_to_replace:{path}",
        file=sys.stderr,
        flush=True,
    )


def read_worker_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def worker_state_is_live(
    state: dict[str, object],
    *,
    now: datetime | None = None,
) -> bool:
    if state.get("status") not in {"starting", "idle", "processing"}:
        return False
    heartbeat = str(state.get("heartbeat_at") or "")
    if not heartbeat:
        return False
    try:
        heartbeat_at = datetime.fromisoformat(heartbeat)
    except ValueError:
        return False
    current = now or datetime.now(timezone.utc)
    return (current - heartbeat_at).total_seconds() <= HEARTBEAT_STALE_SECONDS


def print_worker_status(path: Path) -> int:
    state = read_worker_state(path)
    owner = read_worker_owner(path.with_name("worker_owner.json"))
    live = worker_state_is_live(state)
    print(f"handoff_worker_live={str(live).lower()}")
    for field in ("status", "pid", "started_at", "heartbeat_at", "request", "detail"):
        print(f"{field}={state.get(field, '')}")
    for field in ("launch_source", "cwd", "parent_pid", "command_line"):
        print(f"owner_{field}={owner.get(field, '')}")
    print(f"owner_pid={owner.get('pid', '')}")
    print(f"owner_profile_dir={owner.get('profile_dir', '')}")
    return 0 if live else 1


def write_worker_owner(path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "created_by": "app.handoff_worker",
        "pid": os.getpid(),
        "created_at": now,
        "command_line": _current_process_command_line(),
        "argv": sys.argv,
        "cwd": os.getcwd(),
        "profile_dir": str(edge_profile_dir()),
        "launch_source": os.getenv("LINE_WORKER_LAUNCH_SOURCE", "").strip(),
        "parent_pid": os.getppid(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_worker_owner(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def clear_worker_owner(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def reclaim_stale_owner(*, owner_path: Path, state_path: Path, profile_dir: Path) -> dict[str, str]:
    owner = read_worker_owner(owner_path)
    if not owner:
        state = read_worker_state(state_path)
        if worker_state_is_live(state):
            return {"status": "blocked", "detail": "worker heartbeat is still live"}
        try:
            state_path.unlink()
        except FileNotFoundError:
            return {"status": "noop", "detail": "no owner file"}
        except OSError:
            return {"status": "blocked", "detail": f"unable to clear stale state: {state_path}"}
        return {"status": "reclaimed", "detail": "stale worker state cleared; no owner file existed"}
    if str(owner.get("created_by") or "") != "app.handoff_worker":
        return {"status": "blocked", "detail": "owner file was not created by app.handoff_worker"}
    owner_pid = _parse_pid(owner.get("pid"))
    if owner_pid and pid_is_running(owner_pid):
        return {"status": "blocked", "detail": f"owner pid is still running: {owner_pid}"}
    state = read_worker_state(state_path)
    if worker_state_is_live(state):
        return {"status": "blocked", "detail": "worker heartbeat is still live"}
    try:
        prepare_edge_profile_dir(profile_dir)
    except RuntimeError as exc:
        return {"status": "blocked", "detail": str(exc)}
    clear_worker_owner(owner_path)
    try:
        state_path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        return {"status": "blocked", "detail": f"unable to clear stale state: {state_path}"}
    return {"status": "reclaimed", "detail": f"stale worker owner cleared for {profile_dir}"}


def print_reclaim_result(result: dict[str, str]) -> int:
    print(f"handoff_reclaim_status={result.get('status', '')}")
    print(f"detail={result.get('detail', '')}")
    return 0 if result.get("status") in {"reclaimed", "noop"} else 1


def pid_is_running(pid: int) -> bool:
    if os.name == "nt":
        return _windows_pid_is_running(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _parse_pid(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _windows_pid_is_running(pid: int) -> bool:
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return False

    process_query_limited_information = 0x1000
    synchronize = 0x00100000
    still_active = 259

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(
        process_query_limited_information | synchronize,
        False,
        pid,
    )
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _current_process_command_line() -> str:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.GetCommandLineW.restype = ctypes.c_wchar_p
            return str(ctypes.windll.kernel32.GetCommandLineW() or "")
        except Exception:
            pass
    return " ".join([sys.executable, *sys.argv])


def request_rate_settings(
    request: dict[str, object],
    *,
    defaults: RateLimitSettings,
) -> RateLimitSettings:
    minimum = _positive_override(
        request.get("delay_min_seconds"),
        defaults.delay_min_seconds,
        allow_zero=True,
    )
    maximum = _positive_override(
        request.get("delay_max_seconds"),
        defaults.delay_max_seconds,
        allow_zero=True,
    )
    if maximum < minimum:
        raise ValueError("delay_max_seconds must be >= delay_min_seconds")
    return RateLimitSettings(
        delay_min_seconds=minimum,
        delay_max_seconds=maximum,
        daily_message_quota=_positive_override(
            request.get("daily_message_quota"),
            defaults.daily_message_quota,
        ),
        per_recipient_daily_quota=_positive_override(
            request.get("per_recipient_quota"),
            defaults.per_recipient_daily_quota,
        ),
    )


def _positive_override(
    value: object,
    default: int,
    *,
    allow_zero: bool = False,
) -> int:
    if value is None:
        return default
    parsed = int(value)
    lower_bound = 0 if allow_zero else 1
    if parsed < lower_bound:
        raise ValueError(f"Rate-limit override must be >= {lower_bound}")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
