from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from app.config import Settings
from app.bmp_safety import sanitize_bmp_text
from app.material_catalog import MaterialRecord, material_label
from app.scenario_engine import (
    DRAFT_HEADERS,
    LOG_HEADERS,
    ScenarioDraft,
    ScenarioEvent,
    draft_from_row,
    draft_to_row,
    event_to_log_row,
)
from app.sheet_source import SHEETS_SCOPES

try:
    import gspread
except (ImportError, ModuleNotFoundError):
    gspread = None

try:
    from google.oauth2.service_account import Credentials
except (ImportError, ModuleNotFoundError):
    Credentials = None


@dataclass(frozen=True)
class DraftSheetRow:
    row_number: int
    draft: ScenarioDraft
    raw: dict[str, str]


class SheetGateway:
    PRESENCE_PROFILE_HEADERS = (
        "Enabled",
        "Customer_ID",
        "Clinic_Name",
        "Line_Query",
        "Line_Contact",
        "Line_Message_Style",
        "Interest_Tags",
        "Cadence_Days",
        "Preferred_Send_Time",
        "Last_Category",
        "Last_Generated_Date",
        "Remark",
    )

    MATERIAL_HEADERS = (
        "Material_ID",
        "Filename",
        "SHA256",
        "Duplicate_Of",
        "Product",
        "Topic",
        "Audience",
        "Visual_Summary",
        "Internal_Comment",
        "Customer_Caption",
        "Risk_Level",
        "Safety_Flags",
        "Sendability",
        "Review_Status",
        "Test_Result",
        "Campaigns",
        "Trigger_Types",
        "Tags",
        "Material_Label",
    )

    def __init__(
        self,
        spreadsheet: Any,
        *,
        draft_sheet_name: str,
        log_sheet_name: str,
        material_sheet_name: str = "LINE_Material",
        presence_profile_sheet_name: str = "LINE_Presence_Profiles",
    ) -> None:
        self.spreadsheet = spreadsheet
        self.draft_sheet_name = draft_sheet_name
        self.log_sheet_name = log_sheet_name
        self.material_sheet_name = material_sheet_name
        self.presence_profile_sheet_name = presence_profile_sheet_name

    @classmethod
    def from_settings(cls, settings: Settings) -> "SheetGateway":
        if gspread is None or Credentials is None:
            raise RuntimeError("Google Sheets dependencies are missing. Run `pip install -r requirements.txt`.")
        if not settings.google_credentials_path:
            raise RuntimeError("Missing GOOGLE_APPLICATION_CREDENTIALS or SERVICE_ACCOUNT_FILE.")
        credentials = Credentials.from_service_account_file(
            settings.google_credentials_path,
            scopes=list(SHEETS_SCOPES),
        )
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(settings.source_spreadsheet_id)
        return cls(
            spreadsheet,
            draft_sheet_name=settings.draft_sheet_name,
            log_sheet_name=settings.sheet_log_name,
            material_sheet_name=settings.material_sheet_name,
            presence_profile_sheet_name=settings.presence_profile_sheet_name,
        )

    def fetch_sources(self, tab_names: tuple[str, ...]) -> dict[str, list[list[str]]]:
        sources: dict[str, list[list[str]]] = {}
        for tab_name in tab_names:
            worksheet = self._maybe_worksheet(tab_name)
            if worksheet is not None:
                sources[tab_name] = worksheet.get_all_values()
        return sources

    def append_drafts(self, drafts: list[ScenarioDraft] | tuple[ScenarioDraft, ...]) -> int:
        if not drafts:
            return 0
        worksheet = self.ensure_draft_sheet()
        existing_ids = {
            row.draft.draft_id
            for row in self.read_draft_rows()
            if row.draft.draft_id
        }
        pending_rows = []
        batch_ids = set()
        for draft in drafts:
            if draft.draft_id and (draft.draft_id in existing_ids or draft.draft_id in batch_ids):
                continue
            pending_rows.append(draft_to_row(_sanitize_draft(draft)))
            if draft.draft_id:
                batch_ids.add(draft.draft_id)
        if pending_rows:
            append_managed_rows(worksheet, pending_rows, width=len(DRAFT_HEADERS))
        return len(pending_rows)

    def append_log_events(self, events: list[ScenarioEvent] | tuple[ScenarioEvent, ...]) -> int:
        if not events:
            return 0
        worksheet = self.ensure_log_sheet()
        append_managed_rows(
            worksheet,
            [event_to_log_row(event) for event in events],
            width=len(LOG_HEADERS),
        )
        return len(events)

    def replace_material_catalog(
        self,
        records: list[MaterialRecord] | tuple[MaterialRecord, ...],
    ) -> int:
        worksheet = self.ensure_material_sheet()
        rows = [_material_to_row(record) for record in records]
        update_values(worksheet, "A1", [list(self.MATERIAL_HEADERS)] + rows)
        return len(rows)

    def read_draft_rows(self) -> list[DraftSheetRow]:
        worksheet = self.ensure_draft_sheet()
        values = worksheet.get_all_values()
        if len(values) < 2:
            return []
        headers = [str(cell).strip() for cell in values[0]]
        rows = []
        for row_number, raw in enumerate(values[1:], start=2):
            mapped = {
                headers[index]: str(value).strip()
                for index, value in enumerate(raw)
                if index < len(headers) and headers[index]
            }
            rows.append(DraftSheetRow(row_number=row_number, draft=draft_from_row(mapped), raw=mapped))
        return rows

    def read_presence_profile_rows(self) -> list[dict[str, str]]:
        worksheet = self.ensure_presence_profile_sheet()
        return _worksheet_dict_rows(worksheet)

    def update_draft_result(
        self,
        row_number: int,
        *,
        status: str,
        sent_at: str = "",
        result: str = "",
        error_message: str = "",
    ) -> None:
        worksheet = self.ensure_draft_sheet()
        updates = {
            "Status": status,
            "Sent_At": sent_at,
            "Result": result,
            "Error_Message": error_message,
        }
        header_positions = _header_positions(worksheet.row_values(1))
        cells = []
        for header, value in updates.items():
            column = header_positions.get(header)
            if column:
                cells.append({"range": _a1(row_number, column), "values": [[value]]})
        if cells:
            worksheet.batch_update(cells, value_input_option="USER_ENTERED")

    def ensure_draft_sheet(self) -> Any:
        return self._ensure_sheet(self.draft_sheet_name, DRAFT_HEADERS)

    def ensure_log_sheet(self) -> Any:
        return self._ensure_sheet(self.log_sheet_name, LOG_HEADERS)

    def ensure_material_sheet(self) -> Any:
        return self._ensure_sheet(self.material_sheet_name, self.MATERIAL_HEADERS)

    def ensure_presence_profile_sheet(self) -> Any:
        return self._ensure_sheet(self.presence_profile_sheet_name, self.PRESENCE_PROFILE_HEADERS)

    def _ensure_sheet(self, title: str, headers: tuple[str, ...]) -> Any:
        worksheet = self._maybe_worksheet(title)
        if worksheet is None:
            worksheet = self.spreadsheet.add_worksheet(title=title, rows=1000, cols=max(len(headers), 20))
        existing = [str(value).strip() for value in worksheet.row_values(1)]
        if not any(existing):
            update_values(worksheet, "A1", [list(headers)])
        elif list(headers[: len(existing)]) == existing and len(existing) < len(headers):
            update_values(worksheet, "A1", [list(headers)])
        elif existing[: len(headers)] != list(headers):
            raise RuntimeError(
                f"Sheet {title!r} header mismatch. Expected first columns: {', '.join(headers)}"
            )
        return worksheet

    def _maybe_worksheet(self, title: str) -> Any | None:
        try:
            return self.spreadsheet.worksheet(title)
        except Exception:
            return None


def _header_positions(headers: list[str]) -> dict[str, int]:
    return {str(header).strip(): index for index, header in enumerate(headers, start=1) if str(header).strip()}


def _worksheet_dict_rows(worksheet: Any) -> list[dict[str, str]]:
    values = worksheet.get_all_values()
    if len(values) < 2:
        return []
    headers = [str(cell).strip() for cell in values[0]]
    rows = []
    for raw in values[1:]:
        rows.append(
            {
                headers[index]: str(value).strip()
                for index, value in enumerate(raw)
                if index < len(headers) and headers[index]
            }
        )
    return rows


def _a1(row: int, column: int) -> str:
    letters = ""
    current = column
    while current:
        current, remainder = divmod(current - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def update_values(worksheet: Any, range_name: str, values: list[list[str]]) -> None:
    try:
        worksheet.update(range_name, values, value_input_option="USER_ENTERED")
    except TypeError:
        worksheet.update(values, range_name=range_name, value_input_option="USER_ENTERED")


def append_managed_rows(worksheet: Any, rows: list[list[str]], *, width: int) -> None:
    if not rows:
        return
    values = [_fit_row(row, width) for row in rows]
    existing_values = worksheet.get_all_values()
    _shrink_blank_trailing_columns(worksheet, min_cols=width, existing_values=existing_values)
    next_row = len(existing_values) + 1
    last_row = next_row + len(values) - 1
    row_count = int(getattr(worksheet, "row_count", 0) or 0)
    if row_count and last_row > row_count:
        worksheet.resize(rows=last_row)
    update_values(worksheet, f"{_a1(next_row, 1)}:{_a1(last_row, width)}", values)


def _fit_row(row: list[str], width: int) -> list[str]:
    return (list(row) + [""] * width)[:width]


def _shrink_blank_trailing_columns(
    worksheet: Any,
    *,
    min_cols: int,
    existing_values: list[list[str]],
) -> None:
    col_count = int(getattr(worksheet, "col_count", 0) or 0)
    if not col_count or col_count <= min_cols:
        return
    content_width = max((len(row) for row in existing_values), default=0)
    target_cols = max(min_cols, content_width)
    if target_cols < col_count:
        worksheet.resize(cols=target_cols)


def _sanitize_draft(draft: ScenarioDraft) -> ScenarioDraft:
    message = sanitize_bmp_text(draft.draft_message)
    if message == draft.draft_message:
        return draft
    return replace(draft, draft_message=message)


def _material_to_row(record: MaterialRecord) -> list[str]:
    values = {
        "Material_ID": record.material_id,
        "Filename": record.filename,
        "SHA256": record.sha256,
        "Duplicate_Of": record.duplicate_of,
        "Product": record.product,
        "Topic": record.topic,
        "Audience": record.audience,
        "Visual_Summary": record.visual_summary,
        "Internal_Comment": record.internal_comment,
        "Customer_Caption": record.customer_caption,
        "Risk_Level": record.risk_level,
        "Safety_Flags": ",".join(record.safety_flags),
        "Sendability": record.sendability,
        "Review_Status": record.review_status,
        "Test_Result": record.test_result,
        "Campaigns": ",".join(record.campaigns),
        "Trigger_Types": ",".join(record.trigger_types),
        "Tags": ",".join(record.tags),
        "Material_Label": material_label(record),
    }
    return [values[header] for header in SheetGateway.MATERIAL_HEADERS]
