from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.material_catalog import load_catalog, validate_external_library


EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "edge-profile",
    "logs",
    "snapshots",
    "responses",
    "portable_exports",
    "video_review",
}
EXCLUDED_NAMES = {
    ".env",
    "credentials.json",
    "service-account.json",
    "service_account.json",
}
SECRET_SUFFIXES = (".pem", ".p12", ".key")


def is_exportable_source(relative_path: str | Path) -> bool:
    relative = Path(relative_path)
    lowered_parts = {part.casefold() for part in relative.parts}
    name = relative.name.casefold()
    if lowered_parts & EXCLUDED_PARTS:
        return False
    if name in EXCLUDED_NAMES:
        return False
    if name.endswith(SECRET_SUFFIXES):
        return False
    if name.startswith(".env.") and name != ".env.example":
        return False
    if "credential" in name or "customer_export" in name:
        return False
    return True


def tracked_source_files(root: Path = ROOT) -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    relative_paths = [
        Path(item.decode("utf-8"))
        for item in result.stdout.split(b"\0")
        if item
    ]
    return tuple(
        root / relative
        for relative in relative_paths
        if is_exportable_source(relative)
    )


def build_usb_kit(
    destination: str | Path,
    *,
    material_root: str | Path,
    source_root: Path = ROOT,
) -> Path:
    target = Path(destination).expanduser().resolve()
    if target.exists():
        raise FileExistsError(
            f"Portable kit destination already exists; choose an empty new path: {target}"
        )

    catalog = load_catalog(source_root / "data" / "line_material_catalog.json")
    material_paths = validate_external_library(
        catalog,
        material_root=material_root,
    )
    source_files = tracked_source_files(source_root)

    source_target = target / "source"
    material_target = target / "materials" / "行動力"
    source_target.mkdir(parents=True)
    material_target.mkdir(parents=True)

    for source in source_files:
        relative = source.relative_to(source_root)
        copied = source_target / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, copied)

    for source in material_paths:
        shutil.copy2(source, material_target / source.name)

    shutil.copy2(
        source_root / "portable" / "setup_second_pc.ps1",
        target / "setup_second_pc.ps1",
    )
    shutil.copy2(
        source_root / "portable" / "doctor_second_pc.py",
        target / "doctor_second_pc.py",
    )
    shutil.copy2(
        source_root / "portable" / "README.md",
        target / "README.md",
    )
    shutil.copy2(
        source_root / "portable" / "portable.env.example",
        target / "portable.env.example",
    )

    checksum_path = target / "SHA256SUMS.txt"
    checksum_path.write_text(_checksum_manifest(target), encoding="utf-8")
    manifest = {
        "format_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_file_count": len(source_files),
        "material_file_count": len(material_paths),
        "catalog_record_count": len(catalog.records),
        "checksums": checksum_path.name,
        "credentials_included": False,
        "browser_state_included": False,
    }
    (target / "kit_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def _checksum_manifest(root: Path) -> str:
    lines = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name in {"SHA256SUMS.txt", "kit_manifest.json"}:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        relative = path.relative_to(root).as_posix()
        lines.append(f"{digest}  {relative}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a credential-free portable LINE automation kit."
    )
    parser.add_argument("--destination", required=True)
    parser.add_argument("--material-root", required=True)
    args = parser.parse_args(argv)

    target = build_usb_kit(
        args.destination,
        material_root=args.material_root,
    )
    print(f"portable_kit={target}")
    print("credentials_included=false")
    print("next=Run setup_second_pc.ps1 on the destination PC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
