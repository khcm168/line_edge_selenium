from __future__ import annotations

import hashlib
from dataclasses import replace

from app.ai_drafter import DraftProvider, draft_with_ai
from app.config import Settings
from app.material_catalog import MaterialCatalog, MaterialRecord, select_materials
from app.scenario_engine import ScenarioDraft, taipei_now_iso


def choose_material(
    catalog: MaterialCatalog,
    *,
    material_id: str = "",
    product: str = "",
    audience: str = "",
    campaign: str = "",
    trigger_type: str = "",
) -> MaterialRecord:
    if material_id:
        record = catalog.by_id().get(material_id)
        if record is None:
            raise ValueError(f"Unknown LINE material_id: {material_id}")
        if not record.is_live_eligible:
            raise ValueError(f"LINE material {material_id} is not approved and sendable")
        return record

    matches = select_materials(
        catalog,
        product=product,
        audience=audience,
        campaign=campaign,
        trigger_type=trigger_type,
        approved_only=True,
    )
    if not matches:
        raise ValueError("No approved LINE material matched the requested facts")
    return sorted(matches, key=lambda item: (item.risk_level, item.material_id))[0]


def build_material_draft(
    catalog: MaterialCatalog,
    *,
    settings: Settings,
    line_query: str,
    customer_id: str = "",
    customer_name: str = "",
    line_contact: str = "",
    line_message_style: str = "",
    material_id: str = "",
    product: str = "",
    audience: str = "",
    campaign: str = "",
    trigger_type: str = "material_followup",
    provider: DraftProvider | None = None,
) -> ScenarioDraft:
    record = choose_material(
        catalog,
        material_id=material_id,
        product=product,
        audience=audience,
        campaign=campaign,
        trigger_type=trigger_type,
    )
    created_at = taipei_now_iso()
    key = "|".join(
        (
            "material",
            line_query,
            customer_id,
            record.material_id,
            campaign,
            trigger_type,
        )
    )
    base = ScenarioDraft(
        draft_id=hashlib.sha1(key.encode("utf-8")).hexdigest()[:16],
        created_at=created_at,
        trigger_type=trigger_type,
        source_sheets=("LINE_Material",),
        source_refs={
            "material_id": record.material_id,
            "product": record.product,
            "topic": record.topic,
            "audience": record.audience,
            "visual_summary": record.visual_summary,
            "campaign": campaign,
            "approved_base_caption": record.customer_caption,
        },
        customer_id=customer_id or line_query,
        customer_name=customer_name,
        line_query=line_query,
        line_contact=line_contact or line_query,
        line_message_style=line_message_style,
        product=product or record.product,
        signal_summary=(
            f"Approved material {record.material_id}; topic={record.topic}; "
            f"audience={record.audience}; visual={record.visual_summary}"
        ),
        draft_message=record.customer_caption,
        material_id=record.material_id,
        image_path=record.filename,
        message_kind="image_text",
        material_sha256=record.sha256,
        risk_level=record.risk_level,
        safety_flags=tuple(
            dict.fromkeys(record.safety_flags + ("human_review_required",))
        ),
        result="approved material base caption",
    )
    drafted = draft_with_ai(base, settings=settings, provider=provider)
    return replace(
        drafted,
        material_id=record.material_id,
        image_path=record.filename,
        message_kind="image_text",
        material_sha256=record.sha256,
    )
