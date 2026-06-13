from __future__ import annotations

import argparse

from app.config import Settings
from app.material_catalog import load_catalog, validate_external_library
from app.sheet_gateway import SheetGateway


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the external LINE material library and optionally write LINE_Material."
    )
    parser.add_argument("--write-sheet", action="store_true")
    parser.add_argument("--skip-hash-check", action="store_true")
    args = parser.parse_args(argv)

    settings = Settings.from_env(require_google=args.write_sheet)
    catalog = load_catalog(settings.material_catalog_path)
    if args.skip_hash_check:
        if not settings.material_root.exists():
            raise FileNotFoundError(
                f"LINE material root is unavailable: {settings.material_root}"
            )
    else:
        validate_external_library(catalog, material_root=settings.material_root)

    print(f"catalog={settings.material_catalog_path}")
    print(f"material_root={settings.material_root}")
    print(f"records={len(catalog.records)}")
    print("external_library_valid=true")
    if args.write_sheet:
        gateway = SheetGateway.from_settings(settings)
        written = gateway.replace_material_catalog(catalog.records)
        print(f"material_sheet={settings.material_sheet_name}")
        print(f"sheet_rows={written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
