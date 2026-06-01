from __future__ import annotations

import argparse
from datetime import date

from app.audit import append_jsonl, build_audit_record, utc_stamp
from app.config import Settings
from app.sheet_source import fetch_dy2_values, load_values_from_json, parse_dy2_rows
from app.task_builder import build_shipping_notice_tasks, write_tasks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build DY2 shipping notice LINE tasks.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Taipei local YYYY-MM-DD date.")
    parser.add_argument("--days", type=int, default=1, help="Window after date; default today+tomorrow.")
    parser.add_argument("--max-rows", type=int, default=0, help="Limit generated task count.")
    parser.add_argument("--source-json", help="Read DY2 values from local JSON instead of Google Sheets.")
    args = parser.parse_args(argv)

    settings = Settings.from_env(require_google=not bool(args.source_json))
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.task_dir.mkdir(parents=True, exist_ok=True)

    run_date = date.fromisoformat(args.date)
    values = load_values_from_json(args.source_json) if args.source_json else fetch_dy2_values(settings)
    rows = parse_dy2_rows(values, tab_name=settings.dy2_tab_name)
    tasks = build_shipping_notice_tasks(
        rows,
        today=run_date,
        days=args.days,
        max_rows=args.max_rows,
    )
    task_path = settings.task_dir / f"shipping_notice_{run_date.isoformat()}.json"
    write_tasks(task_path, tasks)

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

