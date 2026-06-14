from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


CATALOG_VERSION = 1
SENDABILITY_VALUES = {"sendable", "internal_only", "blocked"}
REVIEW_STATUS_VALUES = {"pending_review", "approved", "rejected", "blocked"}


@dataclass(frozen=True)
class MaterialRecord:
    material_id: str
    filename: str
    sha256: str
    duplicate_of: str
    product: str
    topic: str
    audience: str
    visual_summary: str
    internal_comment: str
    customer_caption: str
    risk_level: str
    safety_flags: tuple[str, ...]
    sendability: str
    review_status: str
    test_result: str
    campaigns: tuple[str, ...] = ()
    trigger_types: tuple[str, ...] = ()

    @property
    def is_live_eligible(self) -> bool:
        return (
            self.sendability == "sendable"
            and self.review_status == "approved"
            and self.risk_level != "high"
            and "medical_overclaim_risk" not in self.safety_flags
            and "patient_privacy_risk" not in self.safety_flags
        )


@dataclass(frozen=True)
class MaterialCatalog:
    version: int
    records: tuple[MaterialRecord, ...]

    def by_id(self) -> dict[str, MaterialRecord]:
        return {record.material_id: record for record in self.records}


def material_hashtags(record: MaterialRecord) -> tuple[str, ...]:
    values = (
        record.product,
        record.topic,
        record.audience,
        *record.campaigns,
        *record.trigger_types,
        record.sendability,
        record.review_status,
        record.risk_level,
    )
    tags = []
    for value in values:
        normalized = "".join(
            character if character.isalnum() else "_"
            for character in value.strip()
        ).strip("_")
        if normalized:
            tags.append(f"#{normalized}")
    return tuple(dict.fromkeys(tags))


def load_catalog(path: str | Path) -> MaterialCatalog:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"LINE material catalog not found: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    records = tuple(_record_from_dict(item) for item in payload.get("records", []))
    catalog = MaterialCatalog(version=int(payload.get("version", 0)), records=records)
    validate_catalog_shape(catalog)
    return catalog


def write_catalog(path: str | Path, records: Iterable[MaterialRecord]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CATALOG_VERSION,
        "records": [asdict(record) for record in records],
    }
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def validate_catalog_shape(catalog: MaterialCatalog) -> None:
    if catalog.version != CATALOG_VERSION:
        raise ValueError(
            f"Unsupported LINE material catalog version {catalog.version}; "
            f"expected {CATALOG_VERSION}."
        )
    ids = [record.material_id for record in catalog.records]
    filenames = [record.filename.casefold() for record in catalog.records]
    if len(ids) != len(set(ids)):
        raise ValueError("LINE material catalog contains duplicate Material_ID values.")
    if len(filenames) != len(set(filenames)):
        raise ValueError("LINE material catalog contains duplicate filenames.")
    known_ids = set(ids)
    for record in catalog.records:
        if not record.material_id or not record.filename or not record.sha256:
            raise ValueError(f"Incomplete LINE material catalog row: {record}")
        if record.sendability not in SENDABILITY_VALUES:
            raise ValueError(
                f"Unsupported sendability {record.sendability!r} for {record.material_id}."
            )
        if record.review_status not in REVIEW_STATUS_VALUES:
            raise ValueError(
                f"Unsupported review status {record.review_status!r} "
                f"for {record.material_id}."
            )
        if record.duplicate_of and record.duplicate_of not in known_ids:
            raise ValueError(
                f"Unknown duplicate_of {record.duplicate_of!r} "
                f"for {record.material_id}."
            )


def resolve_material_path(
    record: MaterialRecord,
    *,
    material_root: str | Path,
    verify_hash: bool = True,
) -> Path:
    root = Path(material_root)
    if str(material_root).strip() in {"", "."}:
        raise RuntimeError(
            "LINE_MATERIAL_ROOT is not configured. Point it at the external "
            "directory containing the catalog JPG files."
        )
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"LINE material root is unavailable: {root}")
    candidate = (root / record.filename).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(
            f"Material filename escapes LINE_MATERIAL_ROOT: {record.filename}"
        ) from exc
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(
            f"LINE material file is missing for {record.material_id}: {candidate}"
        )
    if verify_hash:
        actual = sha256_file(candidate)
        if actual != record.sha256:
            raise ValueError(
                f"LINE material hash mismatch for {record.material_id}: "
                f"expected {record.sha256}, got {actual}"
            )
    return candidate


def validate_external_library(
    catalog: MaterialCatalog,
    *,
    material_root: str | Path,
) -> tuple[Path, ...]:
    return tuple(
        resolve_material_path(record, material_root=material_root)
        for record in catalog.records
    )


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_materials(
    catalog: MaterialCatalog,
    *,
    product: str = "",
    audience: str = "",
    campaign: str = "",
    trigger_type: str = "",
    approved_only: bool = True,
) -> tuple[MaterialRecord, ...]:
    product_norm = product.casefold().strip()
    audience_norm = audience.casefold().strip()
    campaign_norm = campaign.casefold().strip()
    trigger_norm = trigger_type.casefold().strip()
    selected = []
    for record in catalog.records:
        if approved_only and not record.is_live_eligible:
            continue
        if product_norm and product_norm not in record.product.casefold():
            continue
        if audience_norm and audience_norm not in record.audience.casefold():
            continue
        if campaign_norm and campaign_norm not in {
            item.casefold() for item in record.campaigns
        }:
            continue
        if trigger_norm and trigger_norm not in {
            item.casefold() for item in record.trigger_types
        }:
            continue
        selected.append(record)
    return tuple(selected)


def _record_from_dict(item: dict[str, Any]) -> MaterialRecord:
    return MaterialRecord(
        material_id=str(item.get("material_id") or ""),
        filename=str(item.get("filename") or ""),
        sha256=str(item.get("sha256") or ""),
        duplicate_of=str(item.get("duplicate_of") or ""),
        product=str(item.get("product") or ""),
        topic=str(item.get("topic") or ""),
        audience=str(item.get("audience") or ""),
        visual_summary=str(item.get("visual_summary") or ""),
        internal_comment=str(item.get("internal_comment") or ""),
        customer_caption=str(item.get("customer_caption") or ""),
        risk_level=str(item.get("risk_level") or "medium"),
        safety_flags=tuple(item.get("safety_flags") or ()),
        sendability=str(item.get("sendability") or "internal_only"),
        review_status=str(item.get("review_status") or "pending_review"),
        test_result=str(item.get("test_result") or "not_tested"),
        campaigns=tuple(item.get("campaigns") or ()),
        trigger_types=tuple(item.get("trigger_types") or ()),
    )
