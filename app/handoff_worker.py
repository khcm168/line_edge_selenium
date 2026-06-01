from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from datetime import date

from app.audit import SnapshotWriter, append_jsonl, build_audit_record, utc_stamp
from app.config import Settings
from app.line_batch import _run_task, _validate_live_scope
from app.line_client import LineClient
from app.rate_limiter import MessageQuota, RandomDelay, RateLimitSettings
from app.reminder_rules import ReminderRules
from app.task_builder import MessageTask, build_test_tasks, read_tasks
from app.ui_health import check_login_state, check_search_box


POLL_SECONDS = 1.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persistent LINE handoff worker.")
    parser.add_argument("--submit", action="store_true", help="Submit a request to the running worker.")
    parser.add_argument("--stop", action="store_true", help="Ask the running worker to stop.")
    parser.add_argument("--tasks", help="Task JSON file to submit.")
    parser.add_argument("--test-targets", action="store_true", help="Submit smoke-test targets.")
    parser.add_argument("--manual-approve", action="store_true", help="Open matched chat and stop before sending.")
    parser.add_argument("--send", action="store_true", help="Ask worker to live-send.")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    handoff_dir = settings.task_dir.parent / "handoff"
    inbox = handoff_dir / "inbox"
    done = handoff_dir / "done"
    errors = handoff_dir / "error"
    inbox.mkdir(parents=True, exist_ok=True)
    done.mkdir(parents=True, exist_ok=True)
    errors.mkdir(parents=True, exist_ok=True)

    if args.submit or args.stop:
        request_path = submit_request(args=args, inbox=inbox)
        print(f"handoff_request={request_path}")
        print("handoff_worker_must_be_running=true")
        return 0

    return run_worker(settings=settings, inbox=inbox, done=done, errors=errors)


def submit_request(*, args: argparse.Namespace, inbox: Path) -> Path:
    request = {
        "id": uuid4().hex,
        "created_at": utc_stamp(),
        "stop": args.stop,
        "tasks": str(Path(args.tasks)) if args.tasks else "",
        "test_targets": args.test_targets,
        "manual_approve": args.manual_approve,
        "send": args.send,
    }
    path = inbox / f"{request['created_at']}_{request['id']}.json"
    path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_worker(*, settings: Settings, inbox: Path, done: Path, errors: Path) -> int:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    client = LineClient.open()
    try:
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
        print("handoff_worker_ready=true", flush=True)
        print(f"handoff_inbox={inbox}", flush=True)
        while True:
            request_path = next_request(inbox)
            if request_path is None:
                time.sleep(POLL_SECONDS)
                continue
            should_stop = handle_request(
                request_path=request_path,
                done=done,
                errors=errors,
                settings=settings,
                client=client,
            )
            if should_stop:
                print("handoff_worker_stopping=true", flush=True)
                return 0
    finally:
        client.close()


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
) -> bool:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    result = {
        "request": request,
        "started_at": utc_stamp(),
        "status": "started",
        "audit": "",
        "error": "",
    }
    try:
        if request.get("stop"):
            result["status"] = "stopped"
            return True

        tasks = load_request_tasks(request)
        _validate_live_scope(tasks, send=bool(request.get("send")), settings=settings)
        rules = ReminderRules.load(settings.reminder_rules_path)
        rate_settings = RateLimitSettings(
            delay_min_seconds=rules.default_int("delay_min_seconds", 45),
            delay_max_seconds=rules.default_int("delay_max_seconds", 120),
            daily_message_quota=rules.default_int("daily_message_quota", 20),
            per_recipient_daily_quota=rules.default_int("per_recipient_daily_quota", 1),
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
                    waited = delay.wait()
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
        return False
    except Exception as exc:
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
        append_jsonl(
            settings.log_dir / f"line_handoff_error_{utc_stamp()}.jsonl",
            build_audit_record(
                action="handoff_request",
                status="error",
                detail=result["error"],
                source={"request": request},
            ),
        )
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


if __name__ == "__main__":
    raise SystemExit(main())
