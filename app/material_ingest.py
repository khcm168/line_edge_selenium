from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.config import Settings
from app.material_catalog import (
    MaterialCatalog,
    MaterialRecord,
    load_catalog,
    sha256_file,
    write_catalog,
)
from app.material_vision import DEFAULT_VISION_MODEL, VisionAnalysis, analyze_material_image


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
POLL_SECONDS = 30
MEDICAL_CLAIM_TERMS = (
    "治癒",
    "根治",
    "保證",
    "立即見效",
    "療效",
    "降低死亡",
    "改善疾病",
    "預防疾病",
)
PRIVACY_TERMS = ("姓名", "病歷號", "身分證", "電話", "地址", "出生日期")


def discover_new_images(
    material_root: str | Path,
    catalog: MaterialCatalog,
    *,
    folder: str = "",
    min_age_seconds: float = 10,
    now: float | None = None,
) -> tuple[tuple[Path, str, str], ...]:
    root = Path(material_root).resolve()
    scan_root = (root / folder).resolve() if folder else root
    scan_root.relative_to(root)
    if not scan_root.exists():
        raise FileNotFoundError(f"Material scan folder does not exist: {scan_root}")
    known_hashes = {record.sha256 for record in catalog.records}
    current = now if now is not None else time.time()
    found = []
    for path in sorted(scan_root.rglob("*"), key=lambda item: str(item).casefold()):
        if not path.is_file() or path.suffix.casefold() not in IMAGE_SUFFIXES:
            continue
        if current - path.stat().st_mtime < min_age_seconds:
            continue
        digest = sha256_file(path)
        if digest in known_hashes:
            continue
        known_hashes.add(digest)
        relative = path.resolve().relative_to(root).as_posix()
        found.append((path, relative, digest))
    return tuple(found)


def build_pending_record(
    *,
    relative_path: str,
    digest: str,
    analysis: VisionAnalysis,
    model: str,
) -> MaterialRecord:
    folder = Path(relative_path).parts[0] if len(Path(relative_path).parts) > 1 else "未分類"
    flags = [
        "human_review_required",
        "ai_vision_generated",
        *analysis.safety_flags,
    ]
    reasons = list(analysis.risk_reasons)
    text = " ".join(
        (
            analysis.visible_text,
            analysis.visual_summary,
            analysis.neutral_caption,
        )
    )
    if "處方藥" in folder or "prescription" in folder.casefold():
        flags.append("prescription_drug_content")
        reasons.append("資料夾標示為處方藥，需由合格人員審核用途與對象")
    if any(term in text for term in MEDICAL_CLAIM_TERMS):
        flags.append("medical_overclaim_risk")
        reasons.append("可見內容含需人工確認的醫療或療效用語")
    if any(term in text for term in PRIVACY_TERMS):
        flags.append("patient_privacy_risk")
        reasons.append("可見內容可能包含個人識別欄位")
    flags = tuple(dict.fromkeys(flags))
    risk_level = analysis.risk_level
    if any(
        flag in flags
        for flag in (
            "medical_overclaim_risk",
            "patient_privacy_risk",
            "prescription_drug_content",
        )
    ):
        risk_level = "high"
    reason_text = "；".join(dict.fromkeys(reasons)) or "未指出特定風險，仍需人工審核"
    visible = analysis.visible_text[:1000] or "未可靠辨識"
    return MaterialRecord(
        material_id=f"MAT-AUTO-{digest[:12].upper()}",
        filename=relative_path,
        sha256=digest,
        duplicate_of="",
        product=folder,
        topic=analysis.topic,
        audience=analysis.audience,
        visual_summary=analysis.visual_summary,
        internal_comment=(
            f"Ollama {model} 視覺草稿；風險理由：{reason_text}；"
            f"可見文字：{visible}"
        ),
        customer_caption=analysis.neutral_caption,
        risk_level=risk_level,
        safety_flags=flags,
        sendability="internal_only",
        review_status="pending_review",
        test_result=f"ollama_vision_pending_review:{model}",
        campaigns=("material_library",),
        trigger_types=("material_followup",),
        tags=analysis.tags,
    )


def ingest_once(
    *,
    material_root: Path,
    catalog_path: Path,
    pending_catalog_path: Path,
    folder: str,
    model: str,
    base_url: str,
    timeout_seconds: int,
    num_gpu: int,
    max_files: int,
    min_age_seconds: float,
    analyzer: Callable[..., VisionAnalysis] = analyze_material_image,
    audit_path: Path | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[int, int]:
    catalog = load_catalog(catalog_path)
    pending_records = (
        list(load_catalog(pending_catalog_path, include_pending=False).records)
        if pending_catalog_path.exists()
        else []
    )
    candidates = discover_new_images(
        material_root,
        catalog,
        folder=folder,
        min_age_seconds=min_age_seconds,
    )
    if max_files > 0:
        candidates = candidates[:max_files]
    imported = 0
    failed = 0
    for path, relative, digest in candidates:
        if should_stop is not None and should_stop():
            break
        try:
            analysis = analyzer(
                path,
                folder_name=path.parent.name,
                model=model,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                num_gpu=num_gpu,
            )
            record = build_pending_record(
                relative_path=relative,
                digest=digest,
                analysis=analysis,
                model=model,
            )
            pending_records.append(record)
            write_catalog(pending_catalog_path, pending_records)
            imported += 1
            _audit(
                audit_path,
                status="imported_pending_review",
                material_path=relative,
                material_id=record.material_id,
                detail=asdict(record),
            )
            print(
                f"imported={record.material_id} path={relative} "
                f"tags={' '.join(record.tags)}",
                flush=True,
            )
        except Exception as exc:
            failed += 1
            _audit(
                audit_path,
                status="error",
                material_path=relative,
                detail=f"{type(exc).__name__}: {exc}",
            )
            print(
                f"material_ingest_error={relative}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
    return imported, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect new material images and create Ollama vision metadata."
    )
    parser.add_argument("--root", default="")
    parser.add_argument("--catalog", default="")
    parser.add_argument("--pending-catalog", default="")
    parser.add_argument("--folder", default="")
    parser.add_argument("--model", default=os.getenv("OLLAMA_VISION_MODEL", DEFAULT_VISION_MODEL))
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--min-age-seconds", type=float, default=10)
    parser.add_argument("--poll-seconds", type=float, default=POLL_SECONDS)
    parser.add_argument(
        "--num-gpu",
        type=int,
        default=int(os.getenv("OLLAMA_VISION_NUM_GPU", "0")),
    )
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--list-new", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    project_root = Path(__file__).resolve().parents[1]
    root = Path(
        args.root
        or os.getenv("LINE_MATERIAL_SCAN_ROOT", "")
        or project_root / "Material"
    ).resolve()
    catalog_path = Path(args.catalog or settings.material_catalog_path).resolve()
    state_dir = project_root / "data" / "material_ingest"
    state_path = state_dir / "worker_state.json"
    pending_catalog_path = Path(
        args.pending_catalog or state_dir / "pending_catalog.json"
    ).resolve()
    stop_path = state_dir / "stop.flag"
    audit_path = settings.log_dir / "material_ingest.jsonl"

    if args.status:
        if not state_path.exists():
            print("material_watcher_state=not_started")
            return 1
        print(state_path.read_text(encoding="utf-8"))
        return 0
    if args.stop:
        state_dir.mkdir(parents=True, exist_ok=True)
        stop_path.write_text("stop\n", encoding="ascii")
        print(f"material_watcher_stop_requested={stop_path}")
        return 0
    if args.list_new:
        catalog = load_catalog(catalog_path)
        candidates = discover_new_images(
            root,
            catalog,
            folder=args.folder,
            min_age_seconds=args.min_age_seconds,
        )
        for _, relative, digest in candidates:
            print(f"{digest[:12]} {relative}")
        print(f"new_material_count={len(candidates)}")
        return 0

    state_dir.mkdir(parents=True, exist_ok=True)
    if stop_path.exists():
        stop_path.unlink()
    while True:
        _write_state(state_path, status="scanning", root=str(root), model=args.model)
        imported, failed = ingest_once(
            material_root=root,
            catalog_path=catalog_path,
            pending_catalog_path=pending_catalog_path,
            folder=args.folder,
            model=args.model,
            base_url=settings.ollama_base_url,
            timeout_seconds=max(settings.ollama_timeout_seconds, 300),
            num_gpu=args.num_gpu,
            max_files=args.max_files,
            min_age_seconds=args.min_age_seconds,
            audit_path=audit_path,
            should_stop=stop_path.exists,
        )
        if stop_path.exists():
            _write_state(state_path, status="stopped", root=str(root), model=args.model)
            stop_path.unlink()
            return 0
        _write_state(
            state_path,
            status="idle" if args.watch else "complete",
            root=str(root),
            model=args.model,
            imported=imported,
            failed=failed,
        )
        print(f"imported_count={imported}")
        print(f"failed_count={failed}")
        if not args.watch or args.max_files > 0:
            return 1 if failed else 0
        deadline = time.monotonic() + max(1, args.poll_seconds)
        while time.monotonic() < deadline:
            if stop_path.exists():
                _write_state(state_path, status="stopped", root=str(root), model=args.model)
                stop_path.unlink()
                return 0
            time.sleep(min(1, deadline - time.monotonic()))


def _audit(
    audit_path: Path | None,
    *,
    status: str,
    material_path: str,
    detail: object,
    material_id: str = "",
) -> None:
    if audit_path is None:
        return
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "path": material_path,
        "material_id": material_id,
        "detail": detail,
    }
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_state(path: Path, **values: object) -> None:
    payload = {
        "pid": os.getpid(),
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        **values,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                break
            time.sleep(0.05)
    try:
        temporary.unlink()
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
