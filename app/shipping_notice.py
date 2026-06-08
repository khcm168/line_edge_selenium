from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date

from app.audit import append_jsonl, build_audit_record, utc_stamp
from app.config import Settings
from app.line_profile import parse_line_profiles
from app.scenario_engine import draft_to_log_event, taipei_now_iso
from app.sheet_source import fetch_dy2_values, fetch_list_values, load_values_from_json, parse_dy2_rows
from app.sheet_gateway import SheetGateway
from app.task_builder import build_shipping_notice_tasks, tasks_to_drafts, write_tasks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build DY2 shipping notice LINE tasks.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Taipei local YYYY-MM-DD date.")
    parser.add_argument("--days", type=int, default=1, help="Window after date; default today+tomorrow.")
    parser.add_argument("--max-rows", type=int, default=0, help="Limit generated task count.")
    parser.add_argument("--source-json", help="Read DY2 values from local JSON instead of Google Sheets.")
    parser.add_argument("--list-json", help="Read List values from local JSON instead of Google Sheets.")
    parser.add_argument("--no-ai", action="store_true", help="Use fixed templates without Ollama personalization.")
    parser.add_argument("--write-drafts", action="store_true", help="Append generated messages to LINE_Drafts and log.")
    args = parser.parse_args(argv)

    settings = Settings.from_env(require_google=args.write_drafts or not bool(args.source_json and args.list_json))
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.task_dir.mkdir(parents=True, exist_ok=True)

    run_date = date.fromisoformat(args.date)
    values = load_values_from_json(args.source_json) if args.source_json else fetch_dy2_values(settings)
    list_values = load_values_from_json(args.list_json) if args.list_json else fetch_list_values(settings)
    line_profiles = parse_line_profiles(list_values)
    rows = parse_dy2_rows(values, tab_name=settings.dy2_tab_name)
    tasks = build_shipping_notice_tasks(
        rows,
        today=run_date,
        days=args.days,
        max_rows=args.max_rows,
        line_profiles=line_profiles,
        ai_settings=replace(settings, ai_enabled=False) if args.no_ai else settings,
    )
    task_path = settings.task_dir / f"shipping_notice_{run_date.isoformat()}.json"
    write_tasks(task_path, tasks)
    draft_count = 0
    log_count = 0
    if args.write_drafts:
        gateway = SheetGateway.from_settings(settings)
        drafts = tasks_to_drafts(tasks, created_at=taipei_now_iso())
        draft_count = gateway.append_drafts(drafts)
        log_count = gateway.append_log_events(tuple(draft_to_log_event(draft) for draft in drafts))

    audit_path = settings.log_dir / f"shipping_notice_preview_{utc_stamp()}.jsonl"
    append_jsonl(
        audit_path,
        build_audit_record(
            action="build_shipping_notice_tasks",
            status="preview",
            detail=f"generated {len(tasks)} tasks",
            source={
                "spreadsheet_id": settings.source_spreadsheet_id,
                "tab": settings.dy2_tab_name,
                "date": run_date.isoformat(),
                "days": args.days,
                "ai_enabled": not args.no_ai and settings.ai_enabled,
                "ai_provider": settings.ai_provider,
                "ollama_model": settings.ollama_model,
                "write_drafts": args.write_drafts,
                "draft_count": draft_count,
                "log_count": log_count,
                "task_file": str(task_path),
            },
        ),
    )
    print(f"tasks={task_path}")
    print(f"task_count={len(tasks)}")
    if args.write_drafts:
        print(f"draft_count={draft_count}")
        print(f"log_count={log_count}")
        print(f"draft_sheet={settings.draft_sheet_name}")
    print(f"audit={audit_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

