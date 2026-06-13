from __future__ import annotations

import argparse

from app.config import Settings
from app.material_catalog import load_catalog
from app.material_drafting import build_material_draft
from app.sheet_gateway import SheetGateway


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a reviewed picture-message draft in LINE_Drafts."
    )
    parser.add_argument("--line-query", required=True)
    parser.add_argument("--customer-id", default="")
    parser.add_argument("--customer-name", default="")
    parser.add_argument("--line-contact", default="")
    parser.add_argument("--line-message-style", default="")
    parser.add_argument("--material-id", default="")
    parser.add_argument("--product", default="")
    parser.add_argument("--audience", default="")
    parser.add_argument("--campaign", default="")
    parser.add_argument("--trigger-type", default="material_followup")
    args = parser.parse_args(argv)

    settings = Settings.from_env(require_google=True)
    catalog = load_catalog(settings.material_catalog_path)
    draft = build_material_draft(
        catalog,
        settings=settings,
        line_query=args.line_query,
        customer_id=args.customer_id,
        customer_name=args.customer_name,
        line_contact=args.line_contact,
        line_message_style=args.line_message_style,
        material_id=args.material_id,
        product=args.product,
        audience=args.audience,
        campaign=args.campaign,
        trigger_type=args.trigger_type,
    )
    gateway = SheetGateway.from_settings(settings)
    written = gateway.append_drafts([draft])
    print(f"draft_id={draft.draft_id}")
    print(f"material_id={draft.material_id}")
    print(f"drafts_written={written}")
    print(f"draft_result={draft.result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
