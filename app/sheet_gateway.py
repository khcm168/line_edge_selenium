from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings
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
    def __init__(self, spreadsheet: Any, *, draft_sheet_name: str, log_sheet_name: str) -> None:
        self.spreadsheet = spreadsheet
        self.draft_sheet_name = draft_sheet_name
        self.log_sheet_name = log_sheet_name

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
        worksheet.append_rows([draft_to_row(draft) for draft in drafts], value_input_option="USER_ENTERED")
        return len(drafts)

    def append_log_events(self, events: list[ScenarioEvent] | tuple[ScenarioEvent, ...]) -> int:
        if not events:
            return 0
        worksheet = self.ensure_log_sheet()
        worksheet.append_rows([event_to_log_row(event) for event in events], value_input_option="USER_ENTERED")
        return len(events)

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
