from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from app.line_profile import LineProfile, apply_line_profile, parse_line_profiles
from app.sheet_source import add_business_days, parse_sheet_date


TRIGGER_TYPES = (
    "logistics",
    "stocking_reorder",
    "promotion",
    "referral_thanks",
    "new_product",
    "usage_reminder",
    "new_customer",
    "lost_recovery",
    "price_adjustment",
    "continue_topic",
    "relationship_temperature",
    "activity_followup",
)

DRAFT_STATUS_PENDING = "pending_review"
DRAFT_STATUS_APPROVED = "approved"
DRAFT_STATUS_REJECTED = "rejected"
DRAFT_STATUS_SENT = "sent"
DRAFT_STATUS_ERROR = "error"
SEND_MODE_REVIEW = "review"
SEND_MODE_LIVE = "live"

DRAFT_HEADERS = (
    "Draft_ID",
    "Created_At",
    "Trigger_Type",
    "Source_Sheets",
    "Source_Refs",
    "Customer_ID",
    "Customer_Name",
    "Line_Query",
    "Product",
    "Signal_Summary",
    "Draft_Message",
    "Risk_Level",
    "Safety_Flags",
    "Status",
    "Send_Mode",
    "Approved_By",
    "Approved_At",
    "Sent_At",
    "Result",
    "Error_Message",
    "Line_Contact",
    "Line_Message_Style",
    "Material_ID",
    "Image_Path",
    "Message_Kind",
    "Material_SHA256",
    "Material_Label",
)

LOG_HEADERS = (
    "Timestamp",
    "Bot_Name",
    "Trigger_Type",
    "Source_Sheets",
    "Customer_ID",
    "Customer_Name",
    "Product",
    "Draft_Status",
    "Message_Risk_Level",
    "Human_Review_Required",
    "Result",
    "Error_Message",
)

BOT_NAME = "LINE_BOT_DRAFT_V1"

TEMPLATES = {
    "logistics": "醫師/藥師您好，提醒您近期物流量較大，{product} 到貨可能需要多一點緩衝。若近期有固定使用，建議先確認庫存，避免臨時需要時缺貨。需要我幫您看備庫建議，也可以跟我說。",
    "stocking_reorder": "醫師您好，最近整理補貨資料時看到 {product} 可能接近備庫週期。我先不急著推銷，只是提醒您可以先確認目前庫存，若需要我也可以幫您整理最簡單的備庫建議。",
    "promotion": "醫師您好，這次配合 {event_name} 有一波專業通路活動。若您這邊剛好有固定使用族群，我可以幫您整理一版最精簡的活動搭配方式，讓櫃檯比較好說明。",
    "referral_thanks": "真的謝謝您願意把信任交給我。轉介這件事不只是介紹產品，也是把您的專業信用一起放進來。我會用更謹慎、認真的態度說明，也會把後續服務做好。",
    "new_product": "醫師您好，近期有一個新品項 {product} 想簡短跟您更新，主要是看起來和您目前診所族群有一定相關性。之後拜訪時我可以用 1 分鐘把重點、適合族群與搭配方式講清楚，您再判斷是否值得試用。",
    "usage_reminder": "小提醒：{product} 建議搭配規律使用與足量開水，讓保養比較有儀式感，也比較容易持續。可以從日常活動感、乾澀感、保水感等狀態去觀察，有需要我再幫您整理簡短說明。",
    "new_customer": "很高興今天有機會認識您。我這邊會先把基本資料整理好，之後若有產品資料、到貨、活動或使用方式需要確認，都可以直接用 LINE 找我。我會盡量用最簡短、最不打擾的方式協助您。",
    "lost_recovery": "醫師您好，最近整理回訪資料時看到 {product} 有一陣子比較少補貨。我先不急著推銷，只是想確認一下，是目前需求變少、庫存還夠，還是使用情境有改變？若需要，我可以幫您重新整理適合族群與說明重點。",
    "price_adjustment": "醫師您好，先跟您主動說明一下，{product} 近期價格有做調整。我會盡量提早告知，讓診所比較好安排庫存與客戶說明。若您需要，我也可以幫您整理一版簡短說法。",
    "continue_topic": "醫師您好，延續上次我們聊到的 {topic}，我後來有再幫您整理一下重點。這件事可以不用急著決定，但可以先把適合族群、使用方式與庫存安排抓出來，之後您比較好判斷。",
    "relationship_temperature": "午安，今天剛好想到您那邊有些熟客可能會喜歡這類小福利。這不是急件，只是先跟您分享一下，有需要我再幫您整理最簡單的說明方式。",
    "activity_followup": "謝謝您上次活動的協助。活動後我建議可以抓 3 類對象追蹤：有主動詢問者、已經拿樣品者、以及原本固定使用但需要提醒回購者。我可以幫您整理一份簡短名單與話術。",
}

SOURCE_CANDIDATES = {
    "logistics": ("DY2", "Y2", "OPSR2"),
    "stocking_reorder": ("LOST_Recovery", "Bridge_Logic", "DY2"),
    "promotion": ("marketing", "discount", "母親節"),
    "referral_thanks": ("推薦", "cases", "V", "List"),
    "new_product": ("DY2",),
    "usage_reminder": ("DY2", "Product_Master", "HA客戶n"),
    "new_customer": ("adr",),
    "lost_recovery": ("LOST_Recovery", "XLOST_Recovery"),
    "price_adjustment": ("Price_Adjustment", "checkVariations", "Y2", "DY2"),
    "continue_topic": ("Line", "今日拜訪", "List", "V"),
    "relationship_temperature": ("Line", "List", "今日拜訪"),
    "activity_followup": ("Acts", "ACT4P12", "大型活動"),
}


@dataclass(frozen=True)
class ScenarioDraft:
    draft_id: str
    created_at: str
    trigger_type: str
    source_sheets: tuple[str, ...]
    source_refs: dict[str, Any]
    customer_id: str
    customer_name: str
    line_query: str
    product: str
    signal_summary: str
    draft_message: str
    line_contact: str = ""
    line_message_style: str = ""
    material_id: str = ""
    image_path: str = ""
    message_kind: str = "text"
    material_sha256: str = ""
    material_label: str = ""
    risk_level: str = "low"
    safety_flags: tuple[str, ...] = ("human_review_required",)
    status: str = DRAFT_STATUS_PENDING
    send_mode: str = SEND_MODE_REVIEW
    approved_by: str = ""
    approved_at: str = ""
    sent_at: str = ""
    result: str = ""
    error_message: str = ""

    def with_message(
        self,
        message: str,
        *,
        risk_level: str | None = None,
        safety_flags: tuple[str, ...] | None = None,
        result: str | None = None,
        error_message: str | None = None,
    ) -> "ScenarioDraft":
        return replace(
            self,
            draft_message=message,
            risk_level=risk_level or self.risk_level,
            safety_flags=safety_flags or self.safety_flags,
            result=self.result if result is None else result,
            error_message=self.error_message if error_message is None else error_message,
        )

    def with_line_profile(self, profiles: dict[str, LineProfile]) -> "ScenarioDraft":
        line_query, line_contact, line_message_style = apply_line_profile(
            customer_id=self.customer_id,
            fallback_query=self.line_query,
            profiles=profiles,
        )
        return replace(
            self,
            line_query=line_query,
            line_contact=line_contact,
            line_message_style=line_message_style,
        )


@dataclass(frozen=True)
class ScenarioEvent:
    timestamp: str
    trigger_type: str
    source_sheets: tuple[str, ...]
    customer_id: str = ""
    customer_name: str = ""
    product: str = ""
    draft_status: str = "skipped"
    message_risk_level: str = "low"
    result: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class ScenarioBuildResult:
    drafts: tuple[ScenarioDraft, ...]
    events: tuple[ScenarioEvent, ...]


def build_scenario_drafts(
    sources: dict[str, list[list[str]]],
    *,
    today: date,
    trigger_types: tuple[str, ...] = TRIGGER_TYPES,
    max_per_type: int = 0,
) -> ScenarioBuildResult:
    drafts: list[ScenarioDraft] = []
    events: list[ScenarioEvent] = []
    created_at = taipei_now_iso()
    line_profiles = parse_line_profiles(sources.get("List") or [])

    detectors: dict[str, Callable[[dict[str, list[list[str]]], date, str], list[ScenarioDraft]]] = {
        "logistics": _detect_logistics,
        "stocking_reorder": _detect_stocking_reorder,
        "promotion": _detect_promotion,
        "referral_thanks": _detect_referral_thanks,
        "new_product": _detect_new_product,
        "usage_reminder": _detect_usage_reminder,
        "new_customer": _detect_new_customer,
        "lost_recovery": _detect_lost_recovery,
        "price_adjustment": _detect_price_adjustment,
        "continue_topic": _detect_continue_topic,
        "relationship_temperature": _detect_relationship_temperature,
        "activity_followup": _detect_activity_followup,
    }

    for trigger_type in trigger_types:
        if trigger_type not in detectors:
            events.append(_event(trigger_type, (), result=f"unsupported trigger type: {trigger_type}"))
            continue
        available = _available_sources(sources, trigger_type)
        if not available:
            events.append(
                _event(
                    trigger_type,
                    SOURCE_CANDIDATES.get(trigger_type, ()),
                    result="skipped: source sheet not available",
                )
            )
            continue
        try:
            detected = detectors[trigger_type](sources, today, created_at)
        except Exception as exc:
            events.append(
                _event(
                    trigger_type,
                    available,
                    draft_status="error",
                    message_risk_level="medium",
                    result="error while detecting scenario",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        if max_per_type > 0:
            detected = detected[:max_per_type]
        if line_profiles:
            detected = [draft.with_line_profile(line_profiles) for draft in detected]
        if detected:
            drafts.extend(detected)
            events.extend(
                _event(
                    draft.trigger_type,
                    draft.source_sheets,
                    customer_id=draft.customer_id,
                    customer_name=draft.customer_name,
                    product=draft.product,
                    draft_status="generated",
                    message_risk_level=draft.risk_level,
                    result=draft.signal_summary,
                )
                for draft in detected
            )
        else:
            events.append(_event(trigger_type, available, result="skipped: no matching signal"))

    return ScenarioBuildResult(tuple(drafts), tuple(events))


def draft_to_row(draft: ScenarioDraft) -> list[str]:
    data = {
        "Draft_ID": draft.draft_id,
        "Created_At": draft.created_at,
        "Trigger_Type": draft.trigger_type,
        "Source_Sheets": ",".join(draft.source_sheets),
        "Source_Refs": json.dumps(draft.source_refs, ensure_ascii=False, sort_keys=True),
        "Customer_ID": draft.customer_id,
        "Customer_Name": draft.customer_name,
        "Line_Query": draft.line_query,
        "Line_Contact": draft.line_contact,
        "Line_Message_Style": draft.line_message_style,
        "Material_ID": draft.material_id,
        "Image_Path": draft.image_path,
        "Message_Kind": draft.message_kind,
        "Material_SHA256": draft.material_sha256,
        "Material_Label": draft.material_label,
        "Product": draft.product,
        "Signal_Summary": draft.signal_summary,
        "Draft_Message": draft.draft_message,
        "Risk_Level": draft.risk_level,
        "Safety_Flags": ",".join(draft.safety_flags),
        "Status": draft.status,
        "Send_Mode": draft.send_mode,
        "Approved_By": draft.approved_by,
        "Approved_At": draft.approved_at,
        "Sent_At": draft.sent_at,
        "Result": draft.result,
        "Error_Message": draft.error_message,
    }
    return [str(data.get(header, "")) for header in DRAFT_HEADERS]


def event_to_log_row(event: ScenarioEvent) -> list[str]:
    data = {
        "Timestamp": event.timestamp,
        "Bot_Name": BOT_NAME,
        "Trigger_Type": event.trigger_type,
        "Source_Sheets": ",".join(event.source_sheets),
        "Customer_ID": event.customer_id,
        "Customer_Name": event.customer_name,
        "Product": event.product,
        "Draft_Status": event.draft_status,
        "Message_Risk_Level": event.message_risk_level,
        "Human_Review_Required": "TRUE",
        "Result": event.result,
        "Error_Message": event.error_message,
    }
    return [str(data.get(header, "")) for header in LOG_HEADERS]


def draft_to_log_event(draft: ScenarioDraft, *, draft_status: str = "generated") -> ScenarioEvent:
    return ScenarioEvent(
        timestamp=taipei_now_iso(),
        trigger_type=draft.trigger_type,
        source_sheets=draft.source_sheets,
        customer_id=draft.customer_id,
        customer_name=draft.customer_name,
        product=draft.product,
        draft_status=draft_status,
        message_risk_level=draft.risk_level,
        result=draft.result or draft.signal_summary,
        error_message=draft.error_message,
    )


def draft_from_row(row: dict[str, str]) -> ScenarioDraft:
    source_refs_text = row.get("Source_Refs", "").strip()
    try:
        source_refs = json.loads(source_refs_text) if source_refs_text else {}
    except json.JSONDecodeError:
        source_refs = {"raw": source_refs_text}
    flags = tuple(item.strip() for item in row.get("Safety_Flags", "").split(",") if item.strip())
    return ScenarioDraft(
        draft_id=row.get("Draft_ID", ""),
        created_at=row.get("Created_At", ""),
        trigger_type=row.get("Trigger_Type", ""),
        source_sheets=tuple(item.strip() for item in row.get("Source_Sheets", "").split(",") if item.strip()),
        source_refs=source_refs,
        customer_id=row.get("Customer_ID", ""),
        customer_name=row.get("Customer_Name", ""),
        line_query=row.get("Line_Query", ""),
        line_contact=row.get("Line_Contact", ""),
        line_message_style=row.get("Line_Message_Style", ""),
        material_id=row.get("Material_ID", ""),
        image_path=row.get("Image_Path", ""),
        message_kind=row.get("Message_Kind", "text") or "text",
        material_sha256=row.get("Material_SHA256", ""),
        material_label=row.get("Material_Label", ""),
        product=row.get("Product", ""),
        signal_summary=row.get("Signal_Summary", ""),
        draft_message=row.get("Draft_Message", ""),
        risk_level=row.get("Risk_Level", "low") or "low",
        safety_flags=flags or ("human_review_required",),
        status=row.get("Status", DRAFT_STATUS_PENDING) or DRAFT_STATUS_PENDING,
        send_mode=row.get("Send_Mode", SEND_MODE_REVIEW) or SEND_MODE_REVIEW,
        approved_by=row.get("Approved_By", ""),
        approved_at=row.get("Approved_At", ""),
        sent_at=row.get("Sent_At", ""),
        result=row.get("Result", ""),
        error_message=row.get("Error_Message", ""),
    )


def taipei_now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).replace(microsecond=0).isoformat()


def _detect_logistics(sources: dict[str, list[list[str]]], today: date, created_at: str) -> list[ScenarioDraft]:
    drafts = []
    for tab in ("DY2", "Y2", "OPSR2"):
        for row in _row_dicts(sources, tab):
            sales_date = _date_value(row, "sales_date", "sale_date", "date", "出貨日", "銷售日期")
            if sales_date is None or not (today <= sales_date <= today + timedelta(days=1)):
                continue
            product = _value(row, "product", "品項", "產品")
            line_query = _line_query(row)
            if not product or not line_query:
                continue
            arrival = add_business_days(sales_date, 3)
            drafts.append(
                _draft(
                    created_at,
                    "logistics",
                    tab,
                    row,
                    product=product,
                    line_query=line_query,
                    signal_summary=f"{product} sale date {sales_date.isoformat()}, estimated arrival {arrival.isoformat()}",
                    message=TEMPLATES["logistics"].format(product=product),
                )
            )
    return drafts


def _detect_stocking_reorder(sources: dict[str, list[list[str]]], today: date, created_at: str) -> list[ScenarioDraft]:
    drafts = []
    for tab in ("LOST_Recovery", "Bridge_Logic", "DY2"):
        for row in _row_dicts(sources, tab):
            product = _value(row, "product", "品項", "產品")
            line_query = _line_query(row)
            if not product or not line_query:
                continue
            interval = _optional_int_value(row, "interval_days", "days_since_sale", "days_after_sale")
            qty = _optional_int_value(row, "qty", "quantity", "數量")
            status = _value(row, "status", "flag").casefold()
            reorder_flag = _value(row, "reorder_risk", "reorder_flag", "stocking_reorder", "stocking_reorder_flag")
            if ((interval is not None and interval >= 21) or (qty is not None and qty <= 1) or "reorder" in status or "stock" in status or _truthy(reorder_flag)):
                drafts.append(
                    _draft(
                        created_at,
                        "stocking_reorder",
                        tab,
                        row,
                        product=product,
                        line_query=line_query,
                        signal_summary=f"{product} reorder/stocking signal from {tab}",
                        message=TEMPLATES["stocking_reorder"].format(product=product),
                    )
                )
    return drafts


def _detect_promotion(sources: dict[str, list[list[str]]], today: date, created_at: str) -> list[ScenarioDraft]:
    drafts = []
    for tab in ("marketing", "discount", "母親節"):
        for row in _row_dicts(sources, tab):
            status = _value(row, "status", "approved", "approval").casefold()
            if status and "approved" not in status and "yes" not in status and status not in {"y", "true"}:
                continue
            event_name = _value(row, "event_name", "campaign", "活動") or "節慶活動"
            product = _value(row, "product", "品項", "產品")
            line_query = _line_query(row)
            if not line_query:
                continue
            drafts.append(
                _draft(
                    created_at,
                    "promotion",
                    tab,
                    row,
                    product=product,
                    line_query=line_query,
                    signal_summary=f"{event_name} promotion signal",
                    message=TEMPLATES["promotion"].format(event_name=event_name),
                    risk_level="medium",
                )
            )
    return drafts


def _detect_referral_thanks(sources: dict[str, list[list[str]]], today: date, created_at: str) -> list[ScenarioDraft]:
    drafts = []
    for tab in ("推薦", "cases", "V", "List"):
        for row in _row_dicts(sources, tab):
            referral = _value(row, "referral_event", "referral", "referred", "推薦")
            line_query = _line_query(row)
            if referral and line_query:
                drafts.append(
                    _draft(
                        created_at,
                        "referral_thanks",
                        tab,
                        row,
                        product=_value(row, "product", "品項"),
                        line_query=line_query,
                        signal_summary="privacy-safe referral thanks signal",
                        message=TEMPLATES["referral_thanks"],
                    )
                )
    return drafts


def _detect_new_product(sources: dict[str, list[list[str]]], today: date, created_at: str) -> list[ScenarioDraft]:
    drafts = []
    for row in _row_dicts(sources, "DY2"):
        flag = _value(row, "new_product_flag", "new_item", "新品 flag", "新品").casefold()
        if flag not in {"y", "yes", "true", "1", "新品"}:
            continue
        product = _value(row, "product", "品項", "產品")
        sales_date = _date_value(row, "sales_date", "sale_date", "date")
        if sales_date is None or sales_date < today - timedelta(days=30) or sales_date > today:
            continue
        line_query = _line_query(row)
        if product and line_query:
            drafts.append(
                _draft(
                    created_at,
                    "new_product",
                    "DY2",
                    row,
                    product=product,
                    line_query=line_query,
                    signal_summary=f"{product} marked as new product",
                    message=TEMPLATES["new_product"].format(product=product),
                    risk_level="medium",
                )
            )
    return drafts


def _detect_usage_reminder(sources: dict[str, list[list[str]]], today: date, created_at: str) -> list[ScenarioDraft]:
    drafts = []
    for tab in ("DY2", "Product_Master", "HA客戶n"):
        for row in _row_dicts(sources, tab):
            product = _value(row, "product", "品項", "產品")
            line_query = _line_query(row)
            needs_education = _truthy(_value(row, "usage_education_needed", "usage_reminder", "needs_usage"))
            if line_query and product and needs_education:
                drafts.append(
                    _draft(
                        created_at,
                        "usage_reminder",
                        tab,
                        row,
                        product=product,
                        line_query=line_query,
                        signal_summary=f"{product} usage reminder signal",
                        message=TEMPLATES["usage_reminder"].format(product=product),
                    )
                )
    return drafts


def _detect_new_customer(sources: dict[str, list[list[str]]], today: date, created_at: str) -> list[ScenarioDraft]:
    drafts = []
    for row in _row_dicts(sources, "adr"):
        created = _date_value(row, "created_date", "append_date", "date", "建立日期")
        line_query = _line_query(row)
        if line_query and created == today:
            drafts.append(
                _draft(
                    created_at,
                    "new_customer",
                    "adr",
                    row,
                    product="",
                    line_query=line_query,
                    signal_summary="new customer added to adr",
                    message=TEMPLATES["new_customer"],
                )
            )
    return drafts


def _detect_lost_recovery(sources: dict[str, list[list[str]]], today: date, created_at: str) -> list[ScenarioDraft]:
    drafts = []
    for tab in ("LOST_Recovery", "XLOST_Recovery"):
        for row in _row_dicts(sources, tab):
            product = _value(row, "product", "品項", "產品") or "這個品項"
            line_query = _line_query(row)
            interval = _int_value(row, "interval_days", "lost_days", "days_since_sale")
            status = _value(row, "status", "lost_flag", "flag").casefold()
            if line_query and (interval >= 45 or "lost" in status):
                drafts.append(
                    _draft(
                        created_at,
                        "lost_recovery",
                        tab,
                        row,
                        product=product,
                        line_query=line_query,
                        signal_summary=f"{product} slow/lost usage signal",
                        message=TEMPLATES["lost_recovery"].format(product=product),
                    )
                )
    return drafts


def _detect_price_adjustment(sources: dict[str, list[list[str]]], today: date, created_at: str) -> list[ScenarioDraft]:
    drafts = []
    for tab in ("Price_Adjustment", "checkVariations", "Y2", "DY2"):
        for row in _row_dicts(sources, tab):
            flag = _value(row, "price_change", "price_variation", "variation", "調價").casefold()
            if flag not in {"y", "yes", "true", "1"} and "change" not in flag and "adjust" not in flag:
                continue
            product = _value(row, "product", "品項", "產品") or "這個品項"
            line_query = _line_query(row)
            if line_query:
                drafts.append(
                    _draft(
                        created_at,
                        "price_adjustment",
                        tab,
                        row,
                        product=product,
                        line_query=line_query,
                        signal_summary=f"{product} price adjustment signal",
                        message=TEMPLATES["price_adjustment"].format(product=product),
                        risk_level="medium",
                    )
                )
    return drafts


def _detect_continue_topic(sources: dict[str, list[list[str]]], today: date, created_at: str) -> list[ScenarioDraft]:
    drafts = []
    for tab in ("Line", "今日拜訪", "List", "V"):
        for row in _row_dicts(sources, tab):
            topic = _value(row, "last_topic", "open_loop", "next_action", "topic")
            line_query = _line_query(row)
            if topic and line_query:
                drafts.append(
                    _draft(
                        created_at,
                        "continue_topic",
                        tab,
                        row,
                        product=_value(row, "product", "品項"),
                        line_query=line_query,
                        signal_summary=f"continue previous topic: {topic}",
                        message=TEMPLATES["continue_topic"].format(topic=topic),
                    )
                )
    return drafts


def _detect_relationship_temperature(sources: dict[str, list[list[str]]], today: date, created_at: str) -> list[ScenarioDraft]:
    drafts = []
    for tab in ("Line", "List", "今日拜訪"):
        for row in _row_dicts(sources, tab):
            line_query = _line_query(row)
            last_contact = _date_value(row, "last_contact_date", "last_line_date", "last_contact")
            temperature = _value(row, "temperature", "relationship_temperature", "response_quality").casefold()
            low_contact = last_contact is not None and last_contact <= today - timedelta(days=21)
            if line_query and (low_contact or "low" in temperature or "cold" in temperature):
                drafts.append(
                    _draft(
                        created_at,
                        "relationship_temperature",
                        tab,
                        row,
                        product=_value(row, "product", "品項"),
                        line_query=line_query,
                        signal_summary="low contact frequency relationship signal",
                        message=TEMPLATES["relationship_temperature"],
                    )
                )
    return drafts


def _detect_activity_followup(sources: dict[str, list[list[str]]], today: date, created_at: str) -> list[ScenarioDraft]:
    drafts = []
    for tab in ("Acts", "ACT4P12", "大型活動"):
        for row in _row_dicts(sources, tab):
            activity_date = _date_value(row, "activity_date", "date", "活動日期")
            if activity_date is None or activity_date < today - timedelta(days=14) or activity_date > today:
                continue
            line_query = _line_query(row) or _value(row, "medical_unit", "customer_name", "診所")
            if not line_query:
                continue
            product = _value(row, "products", "product", "品項", "產品")
            drafts.append(
                _draft(
                    created_at,
                    "activity_followup",
                    tab,
                    row,
                    product=product,
                    line_query=line_query,
                    signal_summary=f"activity follow-up for {activity_date.isoformat()}",
                    message=TEMPLATES["activity_followup"],
                )
            )
    return drafts


def _draft(
    created_at: str,
    trigger_type: str,
    tab: str,
    row: dict[str, str],
    *,
    product: str,
    line_query: str,
    signal_summary: str,
    message: str,
    risk_level: str = "low",
) -> ScenarioDraft:
    source_row = row.get("__row_number", "")
    customer_id = _value(row, "customer_id", "code", "customer_code", "客戶代號") or line_query
    customer_name = _value(row, "customer_name", "customer", "medical_unit", "診所", "客戶")
    key = "|".join([trigger_type, tab, source_row, customer_id, line_query, product, signal_summary])
    draft_id = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return ScenarioDraft(
        draft_id=draft_id,
        created_at=created_at,
        trigger_type=trigger_type,
        source_sheets=(tab,),
        source_refs={"tab": tab, "row": source_row},
        customer_id=customer_id,
        customer_name=customer_name,
        line_query=line_query,
        product=product,
        signal_summary=signal_summary,
        draft_message=message,
        risk_level=risk_level,
    )


def _event(
    trigger_type: str,
    source_sheets: tuple[str, ...],
    *,
    customer_id: str = "",
    customer_name: str = "",
    product: str = "",
    draft_status: str = "skipped",
    message_risk_level: str = "low",
    result: str = "",
    error_message: str = "",
) -> ScenarioEvent:
    return ScenarioEvent(
        timestamp=taipei_now_iso(),
        trigger_type=trigger_type,
        source_sheets=source_sheets,
        customer_id=customer_id,
        customer_name=customer_name,
        product=product,
        draft_status=draft_status,
        message_risk_level=message_risk_level,
        result=result,
        error_message=error_message,
    )


def _available_sources(sources: dict[str, list[list[str]]], trigger_type: str) -> tuple[str, ...]:
    return tuple(tab for tab in SOURCE_CANDIDATES.get(trigger_type, ()) if tab in sources)


def _row_dicts(sources: dict[str, list[list[str]]], tab: str) -> list[dict[str, str]]:
    values = sources.get(tab) or []
    if len(values) < 2:
        return []
    headers = [_normalize_header(cell) for cell in values[0]]
    rows = []
    for row_number, raw in enumerate(values[1:], start=2):
        mapped = {"__tab": tab, "__row_number": str(row_number)}
        for index, value in enumerate(raw):
            header = headers[index] if index < len(headers) and headers[index] else f"col_{index + 1}"
            mapped[header] = str(value).strip()
        _apply_positional_fallbacks(tab, raw, mapped)
        rows.append(mapped)
    return rows


def _apply_positional_fallbacks(tab: str, raw: list[str], mapped: dict[str, str]) -> None:
    if tab in {"DY2", "Y2", "OPSR2"}:
        _set_if_present(mapped, "product", raw, 0)
        _set_if_present(mapped, "customer_name", raw, 3)
        _set_if_present(mapped, "qty", raw, 7)
        _set_if_present(mapped, "sales_date", raw, 8)
        _set_if_present(mapped, "new_product_flag", raw, 11)
        _set_if_present(mapped, "customer_id", raw, 29)
        _set_if_present(mapped, "code", raw, 29)
    if tab in {"Acts", "ACT4P12", "大型活動"}:
        _set_if_present(mapped, "activity_date", raw, 2)
        _set_if_present(mapped, "medical_unit", raw, 4)
        products = [raw[index].strip() for index in (6, 7, 8) if index < len(raw) and raw[index].strip()]
        if products:
            mapped.setdefault("products", " / ".join(products))


def _set_if_present(mapped: dict[str, str], key: str, raw: list[str], index: int) -> None:
    if index < len(raw) and str(raw[index]).strip():
        mapped.setdefault(key, str(raw[index]).strip())


def _normalize_header(value: str) -> str:
    text = str(value or "").strip().casefold()
    for old, new in (
        (" ", "_"),
        ("-", "_"),
        ("/", "_"),
        ("customer_code", "customer_id"),
        ("line_query", "line_query"),
        ("sale_date", "sales_date"),
    ):
        text = text.replace(old, new)
    return text


def _line_query(row: dict[str, str]) -> str:
    return _value(row, "line_query", "customer_id", "code", "customer_code", "aka", "customer_name", "medical_unit")


def _value(row: dict[str, str], *names: str) -> str:
    for name in names:
        normalized = _normalize_header(name)
        value = row.get(normalized, "")
        if value:
            return value
    return ""


def _date_value(row: dict[str, str], *names: str) -> date | None:
    text = _value(row, *names)
    if not text:
        return None
    return parse_sheet_date(text)


def _int_value(row: dict[str, str], *names: str) -> int:
    parsed = _optional_int_value(row, *names)
    return parsed if parsed is not None else 0


def _optional_int_value(row: dict[str, str], *names: str) -> int | None:
    text = _value(row, *names).replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _truthy(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "y", "on", "needed"}
