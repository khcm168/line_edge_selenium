from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from app.audit import SnapshotWriter, append_jsonl, build_audit_record, utc_stamp
from app.config import Settings
from app.line_client import LineClient
from app.line_messaging import open_chat, resolve_match, send_message
from app.task_builder import MessageTask, build_test_tasks, read_tasks, write_tasks
from app.ui_health import check_composer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview or send LINE message tasks.")
    parser.add_argument("--tasks", help="JSON task file to run.")
    parser.add_argument("--test-targets", action="store_true", help="Use the three smoke-test LINE targets.")
    parser.add_argument("--send", action="store_true", help="Actually send messages. Preview is default.")
    parser.add_argument(
        "--manual-approve",
        action="store_true",
        help="Open the matched chat and stop before typing or sending.",
    )
    parser.add_argument("--keep-open", action="store_true", help="Leave Edge open after the run.")
    parser.add_argument(
        "--handoff-start",
        action="store_true",
        help="Start/login LINE, leave Edge open, and exit without running tasks.",
    )
    parser.add_argument(
        "--attach-existing",
        action="store_true",
        help="Attach to the existing handoff Edge session instead of launching a new one.",
    )
    parser.add_argument("--write-test-tasks", action="store_true", help="Write the smoke-test task JSON and exit.")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    settings.task_dir.mkdir(parents=True, exist_ok=True)
    audit_path = settings.log_dir / f"line_batch_{utc_stamp()}.jsonl"
    snapshot_writer = SnapshotWriter(settings.snapshot_dir)

    tasks = _load_tasks(args, settings)
    if args.write_test_tasks:
        path = write_tasks(settings.task_dir / "line_test_targets.json", tasks)
        print(f"tasks_written={path}")
        return 0

    _validate_live_scope(tasks, send=args.send, settings=settings)
    if args.attach_existing:
        client = LineClient.attach_existing()
    elif args.handoff_start:
        client = LineClient.open_handoff()
    else:
        client = LineClient.open()
    try:
        client.driver.maximize_window()
        client.ensure_friends()
        if args.handoff_start:
            print("handoff_ready=true")
            print("next_command_hint=python -m app.line_batch --attach-existing --tasks <task-file>")
            return 0
        for task in tasks:
            _run_task(
                client=client,
                task=task,
                send=args.send,
                manual_approve=args.manual_approve,
                settings=settings,
                audit_path=audit_path,
                snapshot_writer=snapshot_writer,
            )
            if args.manual_approve:
                print("manual_approval_waiting=true")
                break
    finally:
        if not args.keep_open and not args.manual_approve and not args.handoff_start:
            client.close()
    print(f"audit={audit_path}")
    return 0


def _load_tasks(args: argparse.Namespace, settings: Settings) -> list[MessageTask]:
    if args.test_targets:
        return build_test_tasks()
    if args.tasks:
        return read_tasks(args.tasks)
    default_task_path = settings.task_dir / "line_test_targets.json"
    if default_task_path.exists():
        return read_tasks(default_task_path)
    return build_test_tasks()


def _run_task(
    *,
    client: LineClient,
    task: MessageTask,
    send: bool,
    manual_approve: bool,
    settings: Settings,
    audit_path: Path,
    snapshot_writer: SnapshotWriter,
) -> str:
    decision = resolve_match(
        client.driver,
        query=task.query,
        policy=task.match_policy,
        allow_group=task.allow_group,
        allowed_group_targets=settings.allowed_group_targets,
    )
    snapshot = snapshot_writer.write(
        label=f"match_{task.query}",
        payload={
            "task": asdict(task),
            "decision": decision,
            "visible_text": client.visible_text()[:3000],
        },
        driver=client.driver,
    )
    if not decision.ok:
        append_jsonl(
            audit_path,
            build_audit_record(
                action=task.action,
                status=decision.status,
                query=task.query,
                policy=task.match_policy,
                message=task.message,
                detail=decision.detail,
                source=task.source,
                candidates=list(decision.candidates),
                snapshot=snapshot,
            ),
        )
        print(f"skipped={task.query} status={decision.status}")
        return decision.status

    if manual_approve:
        open_chat(client.driver, decision)
        health = check_composer(client.driver)
        approval_snapshot = snapshot_writer.write(
            label=f"manual_approval_{task.query}",
            payload={
                "task": asdict(task),
                "decision": decision,
                "visible_text": client.visible_text()[:3000],
                "note": "Manual approval mode opened the matched chat and stopped before typing or sending.",
                "composer_health": health,
            },
            driver=client.driver,
        )
        append_jsonl(
            audit_path,
            build_audit_record(
                action=task.action,
                status="manual_approval_opened",
                query=task.query,
                policy=task.match_policy,
                message=task.message,
                detail=f"opened matched chat; no text typed and no message sent; {health.status}",
                source=task.source,
                candidates=list(decision.candidates),
                selected=decision.selected,
                snapshot=approval_snapshot,
            ),
        )
        print(f"manual_approval_opened={task.query}")
        return "manual_approval_opened"

    if not send:
        append_jsonl(
            audit_path,
            build_audit_record(
                action=task.action,
                status="preview_matched",
                query=task.query,
                policy=task.match_policy,
                message=task.message,
                detail=decision.detail,
                source=task.source,
                candidates=list(decision.candidates),
                selected=decision.selected,
                snapshot=snapshot,
            ),
        )
        print(f"preview_matched={task.query}")
        return "preview_matched"

    open_chat(client.driver, decision)
    health = check_composer(client.driver)
    if not health.ok:
        failure_snapshot = snapshot_writer.write(
            label=f"composer_missing_{task.query}",
            payload={
                "task": asdict(task),
                "decision": decision,
                "visible_text": client.visible_text()[:3000],
                "composer_health": health,
            },
            driver=client.driver,
        )
        append_jsonl(
            audit_path,
            build_audit_record(
                action=task.action,
                status=health.status,
                query=task.query,
                policy=task.match_policy,
                message=task.message,
                detail=health.detail,
                source=task.source,
                selected=decision.selected,
                snapshot=failure_snapshot,
            ),
        )
        raise RuntimeError(health.detail)
    method = send_message(client.driver, task.message)
    send_snapshot = snapshot_writer.write(
        label=f"sent_{task.query}",
        payload={"task": asdict(task), "method": method},
        driver=client.driver,
    )
    append_jsonl(
        audit_path,
        build_audit_record(
            action=task.action,
            status="sent",
            query=task.query,
            policy=task.match_policy,
            message=task.message,
            detail=f"sent via {method}",
            source=task.source,
            selected=decision.selected,
            snapshot=send_snapshot,
        ),
    )
    print(f"sent={task.query} method={method}")
    return "sent"


def _validate_live_scope(
    tasks: list[MessageTask],
    *,
    send: bool,
    settings: Settings,
) -> None:
    if not send:
        return
    allowed = set(settings.allowed_live_targets)
    for task in tasks:
        if not task.message.strip():
            raise ValueError(f"Refusing live send with blank message: {task.query}")
        if task.manual_required:
            raise ValueError(
                f"Live send target {task.query!r} requires manual approval workflow."
            )
        if task.query not in allowed:
            raise ValueError(
                f"Live send target {task.query!r} is not in LINE_ALLOWED_LIVE_TARGETS."
            )


if __name__ == "__main__":
    raise SystemExit(main())
