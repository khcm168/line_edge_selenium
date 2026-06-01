from __future__ import annotations

import argparse
from datetime import date

from app.audit import append_jsonl, build_audit_record, utc_stamp
from app.config import Settings
from app.reminder_rules import ReminderRules, normalize_types, write_default_rules
from app.sheet_source import (
    fetch_acts_values,
    fetch_dy2_values,
    load_values_from_json,
    parse_acts_rows,
    parse_dy2_rows,
)
from app.task_builder import build_reminder_tasks, write_tasks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build LINE reminder task files.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Taipei local YYYY-MM-DD date.")
    parser.add_argument("--types", default="all", help="Comma-separated reminder types, or all.")
    parser.add_argument("--max-rows", type=int, default=0, help="Limit generated task count.")
    parser.add_argument("--dy2-json", help="Read DY2 values from local JSON instead of Google Sheets.")
    parser.add_argument("--acts-json", help="Read Acts values from local JSON instead of Google Sheets.")
    parser.add_argument("--write-default-rules", action="store_true", help="Create data/reminder_rules.json if absent.")
    args = parser.parse_args(argv)

    settings = Settings.from_env(require_google=not (args.dy2_json and args.acts_json))
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.task_dir.mkdir(parents=True, exist_ok=True)
    if args.write_default_rules:
        print(f"rules={write_default_rules(settings.reminder_rules_path)}")

    run_date = date.fromisoformat(args.date)
    reminder_types = normalize_types(args.types)
    rules = ReminderRules.load(settings.reminder_rules_path)

    dy2_values = load_values_from_json(args.dy2_json) if args.dy2_json else fetch_dy2_values(settings)
    acts_values = load_values_from_json(args.acts_json) if args.acts_json else fetch_acts_values(settings)
    dy2_rows = parse_dy2_rows(dy2_values, tab_name=settings.dy2_tab_name)
    acts_rows = parse_acts_rows(acts_values, tab_name=settings.acts_tab_name)
    tasks = build_reminder_tasks(
        dy2_rows=dy2_rows,
        acts_rows=acts_rows,
        today=run_date,
        reminder_types=reminder_types,
        rules=rules,
        max_rows=args.max_rows,
    )

    type_label = "all" if args.types == "all" else "_".join(reminder_types)
    task_path = settings.task_dir / f"reminders_{run_date.isoformat()}_{type_label}.json"
    write_tasks(task_path, tasks)
    audit_path = settings.log_dir / f"reminder_preview_{utc_stamp()}.jsonl"
    append_jsonl(
        audit_path,
        build_audit_record(
            action="build_reminder_tasks",
            status="preview",
            detail=f"generated {len(tasks)} tasks",
            source={
                "spreadsheet_id": settings.source_spreadsheet_id,
                "dy2_tab": settings.dy2_tab_name,
                "acts_tab": settings.acts_tab_name,
                "date": run_date.isoformat(),
                "types": list(reminder_types),
                "task_file": str(task_path),
            },
        ),
    )
    print(f"tasks={task_path}")
    print(f"task_count={len(tasks)}")
    print(f"audit={audit_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
