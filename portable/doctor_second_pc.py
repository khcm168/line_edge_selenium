from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path


KIT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = KIT_ROOT / "source"
MATERIAL_ROOT = KIT_ROOT / "materials" / "行動力"
CATALOG_PATH = SOURCE_ROOT / "data" / "line_material_catalog.json"


def run_doctor() -> tuple[list[str], list[str]]:
    passed: list[str] = []
    failed: list[str] = []

    _check(
        sys.version_info >= (3, 10),
        f"Python {platform.python_version()}",
        "Python 3.10 or newer is required",
        passed,
        failed,
    )
    _check(SOURCE_ROOT.is_dir(), "source directory", "source directory missing", passed, failed)
    _check(
        (SOURCE_ROOT / "requirements.txt").is_file(),
        "requirements.txt",
        "requirements.txt missing",
        passed,
        failed,
    )
    _check(MATERIAL_ROOT.is_dir(), "material directory", "material directory missing", passed, failed)
    _check(CATALOG_PATH.is_file(), "material catalog", "material catalog missing", passed, failed)

    if CATALOG_PATH.is_file() and MATERIAL_ROOT.is_dir():
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        records = payload.get("records") or []
        errors = []
        for record in records:
            path = MATERIAL_ROOT / str(record.get("filename") or "")
            if not path.is_file():
                errors.append(f"missing:{path.name}")
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != record.get("sha256"):
                errors.append(f"hash:{path.name}")
        _check(
            len(records) == 195 and not errors,
            f"195 material files and hashes ({len(records)} catalog rows)",
            f"material validation failed: rows={len(records)} errors={errors[:5]}",
            passed,
            failed,
        )

    forbidden = [
        path
        for path in KIT_ROOT.rglob("*")
        if path.name.casefold()
        in {
            "credentials.json",
            "service-account.json",
            "service_account.json",
            "devtoolsactiveport",
        }
        or "edge-profile" in {part.casefold() for part in path.parts}
    ]
    _check(
        not forbidden,
        "no credentials or Edge profile present",
        f"forbidden portable files found: {[str(path) for path in forbidden[:5]]}",
        passed,
        failed,
    )
    return passed, failed


def _check(
    condition: bool,
    success: str,
    failure: str,
    passed: list[str],
    failed: list[str],
) -> None:
    (passed if condition else failed).append(success if condition else failure)


def main() -> int:
    passed, failed = run_doctor()
    for item in passed:
        print(f"PASS {item}")
    for item in failed:
        print(f"FAIL {item}")
    print(f"doctor_ok={str(not failed).lower()}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
