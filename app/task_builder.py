from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.ai_drafter import DraftProvider, constrained_rewrite
from app.config import Settings
from app.line_profile import LineProfile, apply_line_profile
from app.reminder_rules import ReminderRules
from app.scenario_engine import ScenarioDraft
from app.sheet_source import (
    ActivityRow,
    ShipmentRow,
    activity_source,
    add_business_days,
    build_shipping_message,
    filter_activity_window,
    filter_shipping_window,
    row_source,
)


TEST_TARGETS = (
    ("洪啓明", "unique_contains_friend", False),
    ("P103003", "unique_contains_friend", False),
    ("001N1備份區", "unique_contains_group", True),
    ("Ya.ping", "exact_friend", False),
)
TEST_MESSAGE = "LINE automation preview test. No live send unless --send is used."


@dataclass(frozen=True)
class MessageTask:
    action: str
    query: str
    match_policy: str
    message: str
    allow_group: bool = False
    customer_id: str = ""
    line_contact: str = ""
    line_message_style: str = ""
    source: dict[str, Any] | None = None
    reminder_type: str = ""
    due_date: str = ""
    quota_key: str = ""
    manual_required: bool = False


def build_test_tasks() -> list[MessageTask]:
    return [
        MessageTask(
            action="send_message",
            query=query,
            match_policy=policy,
            message=TEST_MESSAGE,
            allow_group=allow_group,
            source={"kind": "smoke_test_target"},
            reminder_type="smoke_test",
            quota_key=f"smoke_test:{query}",
        )
        for query, policy, allow_group in TEST_TARGETS
    ]


def build_shipping_notice_tasks(
    rows: list[ShipmentRow],
    *,
    today: date,
    days: int = 1,
    max_rows: int = 0,
    line_profiles: dict[str, LineProfile] | None = None,
    ai_settings: Settings | None = None,
    draft_provider: DraftProvider | None = None,
) -> list[MessageTask]:
    selected = filter_shipping_window(rows, today=today, days=days)
    if max_rows > 0:
        selected = selected[:max_rows]
    profiles = line_profiles or {}
    tasks = []
    for row in selected:
        query, line_contact, line_message_style = apply_line_profile(
            customer_id=row.code,
            fallback_query=row.code,
            profiles=profiles,
        )
        source = row_source(row)
        message, source = _personalize_message(
            base_message=build_shipping_message(row),
            trigger_type="shipping",
            source_sheets=(row.source_tab,),
            source_refs=source,
            customer_id=row.code,
            customer_name=line_contact,
            line_query=query,
            product=row.product,
            signal_summary=(
                f"{row.product} shipping notice; sale date {row.sales_date.isoformat()}; "
                f"arrival estimate {add_business_days(row.sales_date, 3).isoformat()}."
            ),
            line_contact=line_contact,
            line_message_style=line_message_style,
            settings=ai_settings,
            provider=draft_provider,
        )
        tasks.append(
            MessageTask(
                action="send_message",
                query=query,
                match_policy="unique_contains_friend",
                message=message,
                allow_group=False,
                customer_id=row.code,
                line_contact=line_contact,
                line_message_style=line_message_style,
                source=source,
                reminder_type="shipping",
                due_date=row.sales_date.isoformat(),
                quota_key=f"shipping:{row.code}:{row.sales_date.isoformat()}",
                manual_required=True,
            )
        )
    return tasks


def build_reminder_tasks(
    *,
    dy2_rows: list[ShipmentRow],
    acts_rows: list[ActivityRow],
    today: date,
    reminder_types: tuple[str, ...],
    rules: ReminderRules,
    max_rows: int = 0,
    line_profiles: dict[str, LineProfile] | None = None,
    ai_settings: Settings | None = None,
    draft_provider: DraftProvider | None = None,
) -> list[MessageTask]:
    tasks: list[MessageTask] = []
    profiles = line_profiles or {}
    if "shipping" in reminder_types:
        tasks.extend(
            _build_shipping(
                dy2_rows,
                today=today,
                rules=rules,
                line_profiles=profiles,
                ai_settings=ai_settings,
                draft_provider=draft_provider,
            )
        )
    if "feedback" in reminder_types:
        tasks.extend(
            _build_dy2_offset_reminders(
                dy2_rows,
                today=today,
                rules=rules,
                reminder_type="feedback",
                line_profiles=profiles,
                ai_settings=ai_settings,
                draft_provider=draft_provider,
            )
        )
    if "free_goods" in reminder_types:
        tasks.extend(
            _build_dy2_same_day_reminders(
                dy2_rows,
                today=today,
                rules=rules,
                reminder_type="free_goods",
                line_profiles=profiles,
                ai_settings=ai_settings,
                draft_provider=draft_provider,
            )
        )
    if "usage" in reminder_types:
        tasks.extend(
            _build_dy2_same_day_reminders(
                dy2_rows,
                today=today,
                rules=rules,
                reminder_type="usage",
                line_profiles=profiles,
                ai_settings=ai_settings,
                draft_provider=draft_provider,
            )
        )
    if "activity_followup" in reminder_types:
        tasks.extend(
            _build_activity_followups(
                acts_rows,
                today=today,
                rules=rules,
                line_profiles=profiles,
                ai_settings=ai_settings,
                draft_provider=draft_provider,
            )
        )
    if "repurchase" in reminder_types:
        tasks.extend(
            _build_dy2_offset_reminders(
                dy2_rows,
                today=today,
                rules=rules,
                reminder_type="repurchase",
                line_profiles=profiles,
                ai_settings=ai_settings,
                draft_provider=draft_provider,
            )
        )
    if "app" in reminder_types:
        tasks.extend(
            _build_dy2_same_day_reminders(
                dy2_rows,
                today=today,
                rules=rules,
                reminder_type="app",
                line_profiles=profiles,
                ai_settings=ai_settings,
                draft_provider=draft_provider,
            )
        )
    if max_rows > 0:
        return tasks[:max_rows]
    return tasks


def _build_shipping(
    rows: list[ShipmentRow],
    *,
    today: date,
    rules: ReminderRules,
    line_profiles: dict[str, LineProfile],
    ai_settings: Settings | None,
    draft_provider: DraftProvider | None,
) -> list[MessageTask]:
    if not rules.enabled("shipping"):
        return []
    days = int(rules.reminder("shipping").get("days", 1))
    return build_shipping_notice_tasks(
        rows,
        today=today,
        days=days,
        line_profiles=line_profiles,
        ai_settings=ai_settings,
        draft_provider=draft_provider,
    )


def _build_dy2_same_day_reminders(
    rows: list[ShipmentRow],
    *,
    today: date,
    rules: ReminderRules,
    reminder_type: str,
    line_profiles: dict[str, LineProfile],
    ai_settings: Settings | None,
    draft_provider: DraftProvider | None,
) -> list[MessageTask]:
    if not rules.enabled(reminder_type):
        return []
    template = rules.template(reminder_type)
    if not template:
        return []
    selected = filter_shipping_window(rows, today=today, days=0)
    return [
        _shipment_task(
            row,
            reminder_type,
            template,
            today,
            line_profiles,
            ai_settings,
            draft_provider,
        )
        for row in selected
    ]


def _build_dy2_offset_reminders(
    rows: list[ShipmentRow],
    *,
    today: date,
    rules: ReminderRules,
    reminder_type: str,
    line_profiles: dict[str, LineProfile],
    ai_settings: Settings | None,
    draft_provider: DraftProvider | None,
) -> list[MessageTask]:
    if not rules.enabled(reminder_type):
        return []
    rule = rules.reminder(reminder_type)
    template = rules.template(reminder_type)
    if not template:
        return []
    if reminder_type == "feedback":
        offset = int(rule.get("days_after_delivery", 2))
        selected = [
            row
            for row in rows
            if add_business_days(row.sales_date, 3).toordinal() + offset
            == today.toordinal()
        ]
    else:
        offset = int(rule.get("days_after_sale", 30))
        selected = [
            row for row in rows if row.sales_date.toordinal() + offset == today.toordinal()
        ]
    return [
        _shipment_task(
            row,
            reminder_type,
            template,
            today,
            line_profiles,
            ai_settings,
            draft_provider,
        )
        for row in selected
    ]


def _build_activity_followups(
    rows: list[ActivityRow],
    *,
    today: date,
    rules: ReminderRules,
    line_profiles: dict[str, LineProfile],
    ai_settings: Settings | None,
    draft_provider: DraftProvider | None,
) -> list[MessageTask]:
    reminder_type = "activity_followup"
    if not rules.enabled(reminder_type):
        return []
    rule = rules.reminder(reminder_type)
    template = rules.template(reminder_type)
    if not template:
        return []
    selected = filter_activity_window(
        rows,
        today=today,
        lookback_days=int(rule.get("lookback_days", 14)),
    )
    tasks = []
    for row in selected:
        query, line_contact, line_message_style = apply_line_profile(
            customer_id=row.medical_unit,
            fallback_query=row.medical_unit,
            profiles=line_profiles,
        )
        products = ", ".join(row.products)
        message = template.format(
            medical_unit=row.medical_unit,
            activity_type=row.activity_type,
            products=products,
            activity_date=row.activity_date.isoformat(),
            lecturer=row.lecturer,
        )
        source = activity_source(row)
        message, source = _personalize_message(
            base_message=message,
            trigger_type=reminder_type,
            source_sheets=(row.source_tab,),
            source_refs=source,
            customer_id=row.medical_unit,
            customer_name=line_contact or row.medical_unit,
            line_query=query,
            product=products,
            signal_summary=(
                f"{row.medical_unit} {row.activity_type}; activity date "
                f"{row.activity_date.isoformat()}; products {products}."
            ),
            line_contact=line_contact,
            line_message_style=line_message_style,
            settings=ai_settings,
            provider=draft_provider,
        )
        tasks.append(
            MessageTask(
                action="send_message",
                query=query,
                match_policy="unique_contains_friend",
                message=message,
                allow_group=False,
                customer_id=row.medical_unit,
                line_contact=line_contact,
                line_message_style=line_message_style,
                source=source,
                reminder_type=reminder_type,
                due_date=today.isoformat(),
                quota_key=f"{reminder_type}:{row.medical_unit}:{row.activity_date.isoformat()}",
                manual_required=True,
            )
        )
    return tasks


def _shipment_task(
    row: ShipmentRow,
    reminder_type: str,
    template: str,
    today: date,
    line_profiles: dict[str, LineProfile],
    ai_settings: Settings | None,
    draft_provider: DraftProvider | None,
) -> MessageTask:
    arrival = add_business_days(row.sales_date, 3)
    query, line_contact, line_message_style = apply_line_profile(
        customer_id=row.code,
        fallback_query=row.code,
        profiles=line_profiles,
    )
    base_message = template.format(
        product=row.product,
        sales_date=row.sales_date.isoformat(),
        arrival_date=arrival.isoformat(),
        code=row.code,
    )
    source = row_source(row)
    message, source = _personalize_message(
        base_message=base_message,
        trigger_type=reminder_type,
        source_sheets=(row.source_tab,),
        source_refs=source,
        customer_id=row.code,
        customer_name=line_contact,
        line_query=query,
        product=row.product,
        signal_summary=(
            f"{row.product} {reminder_type}; sale date {row.sales_date.isoformat()}; "
            f"arrival estimate {arrival.isoformat()}."
        ),
        line_contact=line_contact,
        line_message_style=line_message_style,
        settings=ai_settings,
        provider=draft_provider,
    )
    return MessageTask(
        action="send_message",
        query=query,
        match_policy="unique_contains_friend",
        message=message,
        allow_group=False,
        customer_id=row.code,
        line_contact=line_contact,
        line_message_style=line_message_style,
        source=source,
        reminder_type=reminder_type,
        due_date=today.isoformat(),
        quota_key=f"{reminder_type}:{row.code}:{today.isoformat()}",
        manual_required=True,
    )


def _personalize_message(
    *,
    base_message: str,
    trigger_type: str,
    source_sheets: tuple[str, ...],
    source_refs: dict[str, Any],
    customer_id: str,
    customer_name: str,
    line_query: str,
    product: str,
    signal_summary: str,
    line_contact: str,
    line_message_style: str,
    settings: Settings | None,
    provider: DraftProvider | None,
) -> tuple[str, dict[str, Any]]:
    source = dict(source_refs)
    draft_message = _addressed_fallback_message(base_message, line_contact)
    if settings is None:
        return draft_message, source

    draft = ScenarioDraft(
        draft_id=f"task:{trigger_type}:{customer_id}:{datetime.now(timezone.utc).isoformat()}",
        created_at=datetime.now(timezone.utc).isoformat(),
        trigger_type=trigger_type,
        source_sheets=source_sheets,
        source_refs=source_refs,
        customer_id=customer_id,
        customer_name=customer_name,
        line_query=line_query,
        product=product,
        signal_summary=signal_summary,
        draft_message=draft_message,
        line_contact=line_contact,
        line_message_style=line_message_style,
    )
    review = constrained_rewrite(
        draft,
        model=settings.openai_model,
        enabled=settings.ai_enabled,
        provider=provider,
        ai_provider=settings.ai_provider,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        ollama_timeout_seconds=settings.ollama_timeout_seconds,
    )
    source["message_draft"] = {
        "result": "ai_rewrite" if review.used_ai else "template_fallback",
        "risk_level": review.risk_level,
        "safety_flags": list(review.safety_flags),
        "rationale": review.rationale,
        "error_message": review.error_message,
        "model": settings.ollama_model if settings.ai_provider == "ollama" else settings.openai_model,
        "provider": settings.ai_provider,
        "line_nickname": line_contact,
        "line_style": line_message_style,
    }
    return review.message, source


def _addressed_fallback_message(message: str, line_contact: str) -> str:
    contact = line_contact.strip()
    if not contact:
        return message
    if message.startswith(contact):
        return message
    return f"{contact}您好，{message}"


def tasks_to_drafts(
    tasks: list[MessageTask],
    *,
    created_at: str | None = None,
) -> tuple[ScenarioDraft, ...]:
    timestamp = created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    drafts: list[ScenarioDraft] = []
    for index, task in enumerate(tasks, start=1):
        source = task.source or {}
        message_draft = source.get("message_draft") if isinstance(source.get("message_draft"), dict) else {}
        source_tab = str(source.get("tab") or "")
        source_row = str(source.get("row") or index)
        product = str(source.get("product") or "")
        result = str(message_draft.get("result") or "template")
        rationale = str(message_draft.get("rationale") or "")
        drafts.append(
            ScenarioDraft(
                draft_id=f"{task.reminder_type}:{task.customer_id}:{task.due_date}:{source_row}",
                created_at=timestamp,
                trigger_type=task.reminder_type or "shipping",
                source_sheets=(source_tab,) if source_tab else (),
                source_refs=source,
                customer_id=task.customer_id,
                customer_name=task.line_contact or task.query,
                line_query=task.query,
                product=product,
                signal_summary=(
                    f"{task.reminder_type or 'shipping'} task from {source_tab or 'task'} "
                    f"row {source_row}; due {task.due_date}."
                ),
                draft_message=task.message,
                line_contact=task.line_contact,
                line_message_style=task.line_message_style,
                risk_level=str(message_draft.get("risk_level") or "low"),
                safety_flags=tuple(message_draft.get("safety_flags") or ("human_review_required",)),
                result=f"{result}: {rationale}" if rationale else result,
                error_message=str(message_draft.get("error_message") or ""),
            )
        )
    return tuple(drafts)


def write_tasks(path: str | Path, tasks: list[MessageTask]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps([asdict(task) for task in tasks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def read_tasks(path: str | Path) -> list[MessageTask]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        MessageTask(
            action=item["action"],
            query=item["query"],
            match_policy=item["match_policy"],
            message=item["message"],
            allow_group=bool(item.get("allow_group", False)),
            customer_id=str(item.get("customer_id") or ""),
            line_contact=str(item.get("line_contact") or ""),
            line_message_style=str(item.get("line_message_style") or ""),
            source=item.get("source") or {},
            reminder_type=str(item.get("reminder_type") or ""),
            due_date=str(item.get("due_date") or ""),
            quota_key=str(item.get("quota_key") or ""),
            manual_required=bool(item.get("manual_required", False)),
        )
        for item in data
    ]
