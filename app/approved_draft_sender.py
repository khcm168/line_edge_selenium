from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.ai_drafter import has_unresolved_placeholder
from app.audit import SnapshotWriter, append_jsonl, build_audit_record, utc_stamp
from app.config import Settings
from app.line_profile import is_line_contact_eligible
from app.line_batch import _run_task
from app.line_client import LineClient
from app.rate_limiter import MessageQuota, RandomDelay, RateLimitSettings
from app.reminder_rules import ReminderRules
from app.response_loop import append_follow_ups, schedule_follow_ups
from app.scenario_engine import (
    DRAFT_STATUS_APPROVED,
    DRAFT_STATUS_ERROR,
    DRAFT_STATUS_SENT,
    SEND_MODE_LIVE,
    ScenarioEvent,
    ScenarioDraft,
    taipei_now_iso,
)
from app.sheet_gateway import DraftSheetRow, SheetGateway
from app.task_builder import MessageTask, write_tasks


@dataclass(frozen=True)
class ApprovedDraftTask:
    row_number: int
    draft: ScenarioDraft
    task: MessageTask


@dataclass(frozen=True)
class ApprovalSelection:
    approved: tuple[ApprovedDraftTask, ...]
    skipped: tuple[ScenarioEvent, ...]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview or send approved LINE_Drafts rows.")
    parser.add_argument("--send-approved", action="store_true", help="Live-send approved rows.")
    parser.add_argument("--max-rows", type=int, default=0, help="Limit approved rows processed.")
    parser.add_argument("--draft-id", default="", help="Process one exact Draft_ID only.")
    parser.add_argument("--write-tasks", help="Write approved rows to a local task JSON file and exit.")
    parser.add_argument("--keep-open", action="store_true", help="Leave Edge open after live send.")
    args = parser.parse_args(argv)

    settings = Settings.from_env(require_google=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    gateway = SheetGateway.from_settings(settings)
    selection = select_approved_drafts(
        gateway.read_draft_rows(),
        allowed_group_targets=settings.allowed_group_targets,
        max_rows=args.max_rows,
        draft_ids=(args.draft_id,) if args.draft_id else (),
    )
    gateway.append_log_events(selection.skipped)

    tasks = [item.task for item in selection.approved]
    if args.write_tasks:
        path = write_tasks(Path(args.write_tasks), tasks)
        print(f"tasks={path}")
        print(f"task_count={len(tasks)}")
        return 0

    if not args.send_approved:
        print(f"approved_count={len(tasks)}")
        print(f"skipped_count={len(selection.skipped)}")
        print("send_approved=false")
        return 0

    if not tasks:
        print("approved_count=0")
        print("nothing_to_send=true")
        return 0

    audit_path = settings.log_dir / f"approved_draft_sender_{utc_stamp()}.jsonl"
    rules = ReminderRules.load(settings.reminder_rules_path)
    rate_settings = RateLimitSettings(
        delay_min_seconds=rules.default_int("delay_min_seconds", 45),
        delay_max_seconds=rules.default_int("delay_max_seconds", 120),
        daily_message_quota=rules.default_int("daily_message_quota", 20),
        per_recipient_daily_quota=rules.default_int("per_recipient_daily_quota", 1),
    )
    quota = MessageQuota(settings.task_dir.parent / "handoff" / "quota.json", rate_settings)
    delay = RandomDelay(rate_settings)
    snapshot_writer = SnapshotWriter(settings.snapshot_dir)
    client = LineClient.open()
    sent_events: list[ScenarioEvent] = []
    try:
        client.driver.maximize_window()
        client.ensure_friends()
        for index, item in enumerate(selection.approved):
            allowed, detail = quota.check(item.task, day=date.today())
            if not allowed:
                gateway.update_draft_result(
                    item.row_number,
                    status=DRAFT_STATUS_ERROR,
                    result="quota blocked",
                    error_message=detail,
                )
                sent_events.append(_send_event(item.draft, "error", "medium", "quota blocked", detail))
                raise RuntimeError(detail)
            if index > 0:
                waited = delay.wait()
                append_jsonl(
                    audit_path,
                    build_audit_record(
                        action="rate_limit_delay",
                        status="waited",
                        query=item.task.query,
                        detail=f"waited {waited:.1f} seconds",
                        source={"draft_id": item.draft.draft_id},
                    ),
                )
            try:
                status = _run_task(
                    client=client,
                    task=item.task,
                    send=True,
                    manual_approve=False,
                    settings=settings,
                    audit_path=audit_path,
                    snapshot_writer=snapshot_writer,
                )
                sent_at = taipei_now_iso()
                gateway.update_draft_result(
                    item.row_number,
                    status=DRAFT_STATUS_SENT,
                    sent_at=sent_at,
                    result=status,
                    error_message="",
                )
                quota.record(item.task, day=date.today(), status=status)
                message_id = f"line-send:{item.draft.draft_id}:{sent_at}"
                append_follow_ups(
                    settings.response_dir / "followups.jsonl",
                    schedule_follow_ups(
                        draft_id=item.draft.draft_id,
                        message_id=message_id,
                        recipient=item.task.query,
                        sent_at=sent_at,
                    ),
                )
                sent_events.append(_send_event(item.draft, "sent", item.draft.risk_level, status, ""))
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                gateway.update_draft_result(
                    item.row_number,
                    status=DRAFT_STATUS_ERROR,
                    result="send failed",
                    error_message=error,
                )
                sent_events.append(_send_event(item.draft, "error", "medium", "send failed", error))
                raise
    finally:
        gateway.append_log_events(sent_events)
        if not args.keep_open:
            client.close()
    print(f"sent_count={len(sent_events)}")
    print(f"audit={audit_path}")
    return 0


def select_approved_drafts(
    rows: list[DraftSheetRow],
    *,
    allowed_group_targets: tuple[str, ...] = (),
    max_rows: int = 0,
    draft_ids: tuple[str, ...] = (),
) -> ApprovalSelection:
    approved: list[ApprovedDraftTask] = []
    skipped: list[ScenarioEvent] = []
    requested_ids = {item.strip() for item in draft_ids if item.strip()}
    for row in rows:
        if requested_ids and row.draft.draft_id not in requested_ids:
            continue
        reason = skip_reason(row.draft, allowed_group_targets=allowed_group_targets)
        if reason:
            skipped.append(_send_event(row.draft, "skipped", row.draft.risk_level, reason, ""))
            continue
        task = MessageTask(
            action="send_message",
            query=row.draft.line_query,
            match_policy=_match_policy(row.draft, allowed_group_targets),
            message=row.draft.draft_message,
            allow_group=row.draft.line_query in allowed_group_targets,
            customer_id=row.draft.customer_id,
            line_contact=row.draft.line_contact,
            line_message_style=row.draft.line_message_style,
            material_id=row.draft.material_id,
            image_path=row.draft.image_path,
            message_kind=row.draft.message_kind,
            material_sha256=row.draft.material_sha256,
            source={
                "draft_id": row.draft.draft_id,
                "trigger_type": row.draft.trigger_type,
                "source_refs": row.draft.source_refs,
                "customer_id": row.draft.customer_id,
                "line_contact": row.draft.line_contact,
                "line_message_style": row.draft.line_message_style,
            },
            reminder_type=row.draft.trigger_type,
            due_date="",
            quota_key=f"draft:{row.draft.draft_id}",
            manual_required=False,
        )
        approved.append(ApprovedDraftTask(row.row_number, row.draft, task))
        if max_rows > 0 and len(approved) >= max_rows:
            break
    return ApprovalSelection(tuple(approved), tuple(skipped))


def skip_reason(draft: ScenarioDraft, *, allowed_group_targets: tuple[str, ...] = ()) -> str:
    if draft.status.casefold() != DRAFT_STATUS_APPROVED:
        return "not approved"
    if draft.send_mode.casefold() != SEND_MODE_LIVE:
        return "send mode is not live"
    if draft.sent_at.strip() or draft.status.casefold() == DRAFT_STATUS_SENT:
        return "already sent"
    if not draft.line_query.strip():
        return "missing line query"
    if not is_line_contact_eligible(draft.customer_id, draft.line_contact):
        return "missing eligible line contact"
    if draft.message_kind not in {"text", "image", "image_text"}:
        return "unsupported message kind"
    if draft.message_kind in {"text", "image_text"} and not draft.draft_message.strip():
        return "blank message"
    if draft.message_kind in {"text", "image_text"} and has_unresolved_placeholder(
        draft.draft_message
    ):
        return "unresolved message placeholder"
    if draft.message_kind in {"image", "image_text"}:
        if not draft.material_id.strip():
            return "missing material id"
        if not draft.image_path.strip():
            return "missing image path"
        if not draft.material_sha256.strip():
            return "missing material hash"
    flags = {flag.casefold() for flag in draft.safety_flags}
    if draft.risk_level.casefold() == "high" or "medical_overclaim_risk" in flags or "patient_privacy_risk" in flags:
        return "high risk blocked"
    if _looks_like_group(draft.line_query) and draft.line_query not in allowed_group_targets:
        return "group target blocked"
    return ""


def _match_policy(draft: ScenarioDraft, allowed_group_targets: tuple[str, ...]) -> str:
    if draft.line_query in allowed_group_targets:
        return "unique_contains_group"
    return "unique_contains_friend"


def _looks_like_group(query: str) -> bool:
    normalized = query.casefold()
    return "group:" in normalized or "備份區" in normalized or "群" in normalized


def _send_event(
    draft: ScenarioDraft,
    status: str,
    risk_level: str,
    result: str,
    error_message: str,
) -> ScenarioEvent:
    return ScenarioEvent(
        timestamp=taipei_now_iso(),
        trigger_type=draft.trigger_type,
        source_sheets=draft.source_sheets,
        customer_id=draft.customer_id,
        customer_name=draft.customer_name,
        product=draft.product,
        draft_status=status,
        message_risk_level=risk_level,
        result=result,
        error_message=error_message,
    )


if __name__ == "__main__":
    raise SystemExit(main())
