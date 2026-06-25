from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from app.config import Settings
from app.material_catalog import (
    MaterialRecord,
    load_catalog,
    material_hashtags,
    material_label,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


def find_materials(
    records: tuple[MaterialRecord, ...],
    *,
    search: str = "",
    product: str = "",
    live_only: bool = False,
) -> tuple[MaterialRecord, ...]:
    search_norm = search.casefold().strip()
    product_norm = product.casefold().strip()
    selected = []
    for record in records:
        if live_only and not record.is_live_eligible:
            continue
        if product_norm and product_norm not in record.product.casefold():
            continue
        searchable = " ".join(
            (
                record.material_id,
                record.filename,
                record.product,
                record.topic,
                record.audience,
                record.visual_summary,
                " ".join(record.campaigns),
                " ".join(record.trigger_types),
                " ".join(material_hashtags(record)),
            )
        ).casefold()
        if search_norm and search_norm not in searchable:
            continue
        selected.append(record)
    return tuple(selected)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search LINE picture materials by topic, product, or hashtag."
    )
    parser.add_argument("--search", default="")
    parser.add_argument("--product", default="")
    parser.add_argument("--material-id", default="")
    parser.add_argument("--live-only", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    catalog = load_catalog(settings.material_catalog_path)
    query = args.material_id or args.search
    matches = find_materials(
        catalog.records,
        search=query,
        product=args.product,
        live_only=args.live_only,
    )
    if args.limit > 0:
        matches = matches[: args.limit]

    if args.json:
        print(
            json.dumps(
                [
                    {
                        **asdict(record),
                        "hashtags": material_hashtags(record),
                        "material_label": material_label(record),
                        "live_eligible": record.is_live_eligible,
                    }
                    for record in matches
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not matches:
        print("No material matched.")
        return 1

    for record in matches:
        status = "LIVE-READY" if record.is_live_eligible else "REVIEW/BLOCKED"
        print(
            f"{material_label(record)} | {status}\n"
            f"  technical ID: {record.material_id}\n"
            f"  product: {record.product}\n"
            f"  topic: {record.topic}\n"
            f"  audience: {record.audience}\n"
            f"  safety: {record.sendability}/{record.review_status}/"
            f"{record.risk_level}\n"
            f"  tags: {' '.join(material_hashtags(record))}\n"
            f"  caption: {record.customer_caption}\n"
        )
    print(f"matches_shown={len(matches)}")
    print(
        "Create a review draft with: python -m app.line_picture_drafts "
        '--line-query "<LINE name>" --material-id "<technical ID shown above>"'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
