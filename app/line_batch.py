from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from pathlib import Path

from app.audit import SnapshotWriter, append_jsonl, build_audit_record, utc_stamp
from app.bmp_safety import sanitize_bmp_text
from app.config import Settings
from app.line_profile import is_line_contact_eligible
from app.line_client import LineClient
from app.line_messaging import (
    current_chat_header,
    open_chat,
    resolve_match,
    send_message,
    submit_image_attachment,
    upload_image,
)
from app.material_catalog import load_catalog, resolve_material_path
from app.task_builder import MessageTask, build_test_tasks, read_tasks, write_tasks
from app.ui_health import check_composer


IMAGE_MESSAGE_KINDS = {"image", "image_text"}
TEXT_MESSAGE_KINDS = {"text", "image_text"}
MESSAGE_KINDS = IMAGE_MESSAGE_KINDS | TEXT_MESSAGE_KINDS
CURRENT_CHAT_EXACT_FRIEND = "current_chat_exact_friend"
CURRENT_CHAT_CONFIRMED = "current_chat_confirmed"


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
    task = _sanitize_task_message(task)
    material = _resolve_task_material(task, settings)
    if task.match_policy == CURRENT_CHAT_EXACT_FRIEND:
        header = current_chat_header(client.driver)
        if not header:
            decision = None
            status = "current_chat_missing"
            detail = "no current chat header was visible"
        elif header != task.query:
            decision = None
            status = "current_chat_mismatch"
            detail = f"current chat header was {header!r}"
        else:
            decision = None
            status = "matched"
            detail = "current chat header matched exactly"
    elif task.match_policy == CURRENT_CHAT_CONFIRMED:
        header = current_chat_header(client.driver)
        if not header:
            decision = None
            status = "current_chat_missing"
            detail = "no current chat header was visible"
        else:
            decision = None
            status = "matched"
            detail = f"current chat header visible: {header!r}"
    else:
        decision = resolve_match(
            client.driver,
            query=task.query,
            policy=task.match_policy,
            allow_group=task.allow_group,
            allowed_group_targets=settings.allowed_group_targets,
        )
        status = decision.status
        detail = decision.detail
    snapshot = snapshot_writer.write(
        label=f"match_{task.query}",
        payload={
            "task": asdict(task),
            "material": material,
            "decision": decision,
            "current_chat_header": current_chat_header(client.driver),
            "visible_text": client.visible_text()[:3000],
        },
        driver=client.driver,
    )
    if (
        task.match_policy not in {CURRENT_CHAT_EXACT_FRIEND, CURRENT_CHAT_CONFIRMED}
        and not decision.ok
    ):
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
    if task.match_policy in {CURRENT_CHAT_EXACT_FRIEND, CURRENT_CHAT_CONFIRMED} and status != "matched":
        append_jsonl(
            audit_path,
            build_audit_record(
                action=task.action,
                status=status,
                query=task.query,
                policy=task.match_policy,
                message=task.message,
                detail=detail,
                source=task.source,
                snapshot=snapshot,
            ),
        )
        print(f"skipped={task.query} status={status}")
        return status

    if manual_approve:
        if decision is not None:
            open_chat(client.driver, decision)
        health = (
            check_composer(client.driver)
            if task.message_kind in TEXT_MESSAGE_KINDS
            else None
        )
        approval_snapshot = snapshot_writer.write(
            label=f"manual_approval_{task.query}",
            payload={
                "task": asdict(task),
                "material": material,
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
                detail=(
                    "opened matched chat; no text typed and no message sent"
                    + (f"; {health.status}" if health else "")
                ),
                source=task.source,
                candidates=list(decision.candidates) if decision is not None else [],
                selected=decision.selected if decision is not None else None,
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
                detail=detail,
                source=task.source,
                candidates=list(decision.candidates) if decision is not None else [],
                selected=decision.selected if decision is not None else None,
                snapshot=snapshot,
            ),
        )
        print(f"preview_matched={task.query}")
        return "preview_matched"

    if decision is not None:
        open_chat(client.driver, decision)
    health = (
        check_composer(client.driver)
        if task.message_kind in TEXT_MESSAGE_KINDS
        else None
    )
    if health is not None and not health.ok:
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
                selected=decision.selected if decision is not None else None,
                snapshot=failure_snapshot,
            ),
        )
        raise RuntimeError(health.detail)
    methods: list[str] = []
    evidence = {"pre_send": str(snapshot)}
    if task.message_kind in IMAGE_MESSAGE_KINDS:
        upload = upload_image(client.driver, material["resolved_path"])
        upload_snapshot = snapshot_writer.write(
            label=f"image_uploaded_{task.query}",
            payload={
                "task": asdict(task),
                "material": material,
                "upload": upload,
                "selected": decision.selected,
            },
            driver=client.driver,
        )
        evidence["post_upload"] = str(upload_snapshot)
        append_jsonl(
            audit_path,
            build_audit_record(
                action="upload_image",
                status="attachment_ready",
                query=task.query,
                policy=task.match_policy,
                message=task.message,
                detail=(
                    f"preview_detected={upload.preview_detected}; "
                    f"explicit_submit_required={upload.explicit_submit_required}"
                ),
                source={
                    **(task.source or {}),
                    "material": material,
                    "evidence": dict(evidence),
                },
                selected=decision.selected if decision is not None else None,
                snapshot=upload_snapshot,
            ),
        )
        methods.append(
            f"image:{submit_image_attachment(client.driver, upload)}"
        )
    if task.message_kind in TEXT_MESSAGE_KINDS:
        methods.append(f"text:{send_message(client.driver, task.message)}")
    method = ",".join(methods)
    send_snapshot = snapshot_writer.write(
        label=f"sent_{task.query}",
        payload={
            "task": asdict(task),
            "material": material,
            "method": method,
            "selected": decision.selected if decision is not None else None,
        },
        driver=client.driver,
    )
    evidence["post_send"] = str(send_snapshot)
    append_jsonl(
        audit_path,
        build_audit_record(
            action=task.action,
            status="sent",
            query=task.query,
            policy=task.match_policy,
            message=task.message,
            detail=f"sent via {method}",
            source={
                **(task.source or {}),
                "material": material,
                "evidence": evidence,
            },
            selected=decision.selected if decision is not None else None,
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
    for task in tasks:
        if task.message_kind not in MESSAGE_KINDS:
            raise ValueError(
                f"Unsupported LINE message_kind {task.message_kind!r}: {task.query}"
            )
        if task.match_policy in {CURRENT_CHAT_EXACT_FRIEND, CURRENT_CHAT_CONFIRMED} and task.allow_group:
            raise ValueError(
                f"Current-chat send cannot allow groups: {task.query}"
            )
        if task.message_kind in TEXT_MESSAGE_KINDS and not sanitize_bmp_text(task.message).strip():
            raise ValueError(f"Refusing live send with blank message: {task.query}")
        if task.message_kind in IMAGE_MESSAGE_KINDS:
            _resolve_task_material(task, settings)
        if task.manual_required:
            raise ValueError(
                f"Live send target {task.query!r} requires manual approval workflow."
            )
        if not is_line_contact_eligible(task.customer_id, task.line_contact):
            raise ValueError(
                f"Live send target {task.query!r} is missing eligible Line contact for Customer_ID {task.customer_id!r}."
            )


def _sanitize_task_message(task: MessageTask) -> MessageTask:
    if task.message_kind not in TEXT_MESSAGE_KINDS:
        return task
    message = sanitize_bmp_text(task.message)
    if message == task.message:
        return task
    return replace(task, message=message)


def _resolve_task_material(task: MessageTask, settings: Settings) -> dict[str, str]:
    if task.message_kind not in IMAGE_MESSAGE_KINDS:
        return {}
    if not task.material_id.strip():
        raise ValueError(f"Picture task is missing material_id: {task.query}")

    catalog = load_catalog(settings.material_catalog_path)
    record = catalog.by_id().get(task.material_id)
    if record is None:
        raise ValueError(f"Unknown LINE material_id: {task.material_id}")
    if not record.is_live_eligible:
        raise ValueError(
            f"LINE material {record.material_id} is not approved and sendable"
        )
    if task.material_sha256 and task.material_sha256 != record.sha256:
        raise ValueError(
            f"Task hash does not match catalog for {record.material_id}"
        )
    if task.image_path:
        requested_name = Path(task.image_path).name.casefold()
        catalog_name = Path(record.filename).name.casefold()
        if requested_name != catalog_name:
            raise ValueError(
                f"Task image_path does not match catalog for {record.material_id}"
            )

    resolved = resolve_material_path(
        record,
        material_root=settings.material_root,
        verify_hash=True,
    )
    return {
        "material_id": record.material_id,
        "filename": record.filename,
        "sha256": record.sha256,
        "duplicate_of": record.duplicate_of,
        "resolved_path": str(resolved),
    }


if __name__ == "__main__":
    raise SystemExit(main())
