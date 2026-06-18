from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings


def fetch_health(url: str, timeout: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"ARM WebApp health returned HTTP {response.status}.")
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict) or body.get("ok") is not True:
        raise RuntimeError(f"ARM WebApp health returned an error: {body}")
    return body


def check_compatibility(
    *,
    settings: Settings | None = None,
    health_fetcher: Callable[[str], dict[str, Any]] = fetch_health,
) -> dict[str, Any]:
    current = settings or Settings.from_env(require_google=False)
    url = os.getenv("ARM_WEBAPP_CANDIDATE_URL", "").strip()
    expected_spreadsheet = os.getenv("ARM_WEBAPP_EXPECTED_SPREADSHEET_ID", "").strip()
    expected_contract = os.getenv("ARM_WEBAPP_EXPECTED_CONTRACT", "").strip()
    expected_contract_version = os.getenv("ARM_WEBAPP_EXPECTED_CONTRACT_VERSION", "").strip()
    expected_release = int(os.getenv("ARM_WEBAPP_EXPECTED_RELEASE_VERSION", "0") or 0)
    if not url:
        raise RuntimeError("Missing ARM_WEBAPP_CANDIDATE_URL from orchestrator.")
    if not expected_spreadsheet:
        raise RuntimeError("Missing ARM_WEBAPP_EXPECTED_SPREADSHEET_ID from orchestrator.")
    if current.source_spreadsheet_id != expected_spreadsheet:
        raise RuntimeError(
            "line_edge_selenium targets another spreadsheet: "
            f"{current.source_spreadsheet_id!r} != {expected_spreadsheet!r}"
        )
    health = health_fetcher(url)
    if health.get("contract") != expected_contract:
        raise RuntimeError(f"Unexpected ARM WebApp contract: {health.get('contract')!r}")
    if health.get("contractVersion") != expected_contract_version:
        raise RuntimeError(
            f"Unexpected ARM WebApp contract version: {health.get('contractVersion')!r}"
        )
    if int(health.get("releaseVersion") or 0) != expected_release:
        raise RuntimeError(f"Unexpected ARM WebApp release: {health.get('releaseVersion')!r}")
    return {
        "ok": True,
        "project": current.project_name,
        "spreadsheetId": current.source_spreadsheet_id,
        "contract": health.get("contract"),
        "contractVersion": health.get("contractVersion"),
        "releaseVersion": health.get("releaseVersion"),
        "role": "shared-spreadsheet observer",
    }


def main() -> int:
    print(json.dumps(check_compatibility(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1) from exc
