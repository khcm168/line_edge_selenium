from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from app.ai_drafter import draft_with_ai
from app.audit import append_jsonl, build_audit_record, utc_stamp
from app.config import Settings
from app.scenario_engine import SOURCE_CANDIDATES, TRIGGER_TYPES, build_scenario_drafts, draft_to_log_event
from app.sheet_gateway import SheetGateway


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build LINE_Drafts rows from scenario signals.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Taipei local YYYY-MM-DD date.")
    parser.add_argument("--types", default="all", help="Comma-separated trigger types, or all.")
    parser.add_argument("--max-per-type", type=int, default=0, help="Limit generated draft count per trigger type.")
    parser.add_argument("--source-json", help="Read source tabs from local JSON mapping instead of Google Sheets.")
    parser.add_argument("--no-ai", action="store_true", help="Use deterministic templates without AI rewrite.")
    parser.add_argument("--no-write", action="store_true", help="Build and audit locally without writing Sheets.")
    args = parser.parse_args(argv)

    settings = Settings.from_env(require_google=not bool(args.source_json) and not args.no_write)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    run_date = date.fromisoformat(args.date)
    trigger_types = normalize_trigger_types(args.types)
    source_tabs = source_tabs_for(trigger_types, list_tab_name=settings.list_tab_name)

    gateway = None if args.source_json else SheetGateway.from_settings(settings)
    sources = load_sources_from_json(args.source_json) if args.source_json else gateway.fetch_sources(source_tabs)
    result = build_scenario_drafts(
        sources,
        today=run_date,
        trigger_types=trigger_types,
        max_per_type=args.max_per_type,
    )

    ai_settings = settings
    if args.no_ai:
        ai_settings = settings.__class__(**{**settings.__dict__, "ai_enabled": False})
    drafts = tuple(draft_with_ai(draft, settings=ai_settings) for draft in result.drafts)
    log_events = tuple(draft_to_log_event(draft) for draft in drafts) + tuple(
        event for event in result.events if event.draft_status != "generated"
    )

    draft_count = 0
    log_count = 0
    if gateway is not None and not args.no_write:
        draft_count = gateway.append_drafts(drafts)
        log_count = gateway.append_log_events(log_events)

    audit_path = settings.log_dir / f"line_draft_builder_{utc_stamp()}.jsonl"
    append_jsonl(
        audit_path,
        build_audit_record(
            action="build_line_drafts",
            status="preview" if args.no_write else "written",
            detail=f"generated {len(drafts)} drafts; wrote {draft_count} new drafts; logged {log_count} events",
            source={
                "spreadsheet_id": settings.source_spreadsheet_id,
                "draft_sheet": settings.draft_sheet_name,
                "log_sheet": settings.sheet_log_name,
                "types": list(trigger_types),
                "source_tabs": list(source_tabs),
                "source_json": args.source_json or "",
                "generated_draft_count": len(drafts),
                "draft_count": draft_count,
                "log_count": log_count,
            },
        ),
    )
    print(f"generated_draft_count={len(drafts)}")
    print(f"event_count={len(log_events)}")
    print(f"audit={audit_path}")
    if args.no_write:
        print("sheets_written=false")
    else:
        print(f"draft_count={draft_count}")
        print(f"log_count={log_count}")
        print(f"draft_sheet={settings.draft_sheet_name}")
        print(f"log_sheet={settings.sheet_log_name}")
    return 0


def normalize_trigger_types(value: str) -> tuple[str, ...]:
    if not value or value == "all":
        return TRIGGER_TYPES
    selected = tuple(item.strip() for item in value.split(",") if item.strip())
    unknown = [item for item in selected if item not in TRIGGER_TYPES]
    if unknown:
        raise ValueError(f"Unsupported trigger type(s): {', '.join(unknown)}")
    return selected


def source_tabs_for(trigger_types: tuple[str, ...], *, list_tab_name: str = "List") -> tuple[str, ...]:
    tabs: list[str] = []
    for trigger_type in trigger_types:
        for tab in SOURCE_CANDIDATES.get(trigger_type, ()):
            if tab not in tabs:
                tabs.append(tab)
    if list_tab_name and list_tab_name not in tabs:
        tabs.append(list_tab_name)
    return tuple(tabs)


def load_sources_from_json(path: str | None) -> dict[str, list[list[str]]]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("--source-json must contain an object mapping tab names to rows.")
    return {
        str(tab): rows
        for tab, rows in data.items()
        if isinstance(rows, list)
    }


if __name__ == "__main__":
    raise SystemExit(main())
