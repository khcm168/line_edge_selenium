from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import Settings

try:
    import gspread
except (ImportError, ModuleNotFoundError):
    gspread = None

try:
    from google.oauth2.service_account import Credentials
except (ImportError, ModuleNotFoundError):
    Credentials = None


SHEETS_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)
DY2_COLUMNS = {
    "product": 0,
    "sales_date": 8,
    "code": 29,
}
ACTS_COLUMNS = {
    "date": 2,
    "psr": 3,
    "medical_unit": 4,
    "activity_type": 5,
    "product_one": 6,
    "product_two": 7,
    "product_three": 8,
    "lecturer": 9,
    "dining_cost": 10,
    "sample_fee": 11,
    "speaker_fee": 12,
    "two_season_sales": 13,
}
SHIPPING_NOTICE_TEMPLATE = "{product}產品預計三個工作天({arrival_date})到貨，請留意"


@dataclass(frozen=True)
class ShipmentRow:
    source_tab: str
    source_row: int
    product: str
    sales_date: date
    code: str


@dataclass(frozen=True)
class ActivityRow:
    source_tab: str
    source_row: int
    activity_date: date
    psr: str
    medical_unit: str
    activity_type: str
    products: tuple[str, ...]
    lecturer: str
    dining_cost: str
    sample_fee: str
    speaker_fee: str
    two_season_sales: str


def fetch_dy2_values(settings: Settings) -> list[list[str]]:
    return fetch_tab_values(settings, settings.dy2_tab_name)


def fetch_acts_values(settings: Settings) -> list[list[str]]:
    return fetch_tab_values(settings, settings.acts_tab_name)


def fetch_list_values(settings: Settings) -> list[list[str]]:
    return fetch_tab_values(settings, settings.list_tab_name)


def fetch_tab_values(settings: Settings, tab_name: str) -> list[list[str]]:
    if gspread is None or Credentials is None:
        raise RuntimeError(
            "Google Sheets dependencies are missing. Run `pip install -r requirements.txt`."
        )
    credentials = Credentials.from_service_account_file(
        settings.google_credentials_path,
        scopes=list(SHEETS_SCOPES),
    )
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(settings.source_spreadsheet_id)
    worksheet = spreadsheet.worksheet(tab_name)
    return worksheet.get_all_values()


def parse_dy2_rows(
    values: list[list[str]],
    *,
    tab_name: str = "DY2",
) -> list[ShipmentRow]:
    rows: list[ShipmentRow] = []
    for index, row in enumerate(values[1:], start=2):
        product = _cell(row, DY2_COLUMNS["product"])
        raw_date = _cell(row, DY2_COLUMNS["sales_date"])
        code = _cell(row, DY2_COLUMNS["code"])
        if not product or not raw_date or not code:
            continue
        parsed_date = parse_sheet_date(raw_date)
        if parsed_date is None:
            continue
        rows.append(
            ShipmentRow(
                source_tab=tab_name,
                source_row=index,
                product=product,
                sales_date=parsed_date,
                code=code,
            )
        )
    return rows


def filter_shipping_window(
    rows: list[ShipmentRow],
    *,
    today: date,
    days: int = 1,
) -> list[ShipmentRow]:
    end_date = today + timedelta(days=days)
    return [row for row in rows if today <= row.sales_date <= end_date]


def parse_acts_rows(
    values: list[list[str]],
    *,
    tab_name: str = "Acts",
) -> list[ActivityRow]:
    rows: list[ActivityRow] = []
    for index, row in enumerate(values[1:], start=2):
        raw_date = _cell(row, ACTS_COLUMNS["date"])
        parsed_date = parse_sheet_date(raw_date)
        medical_unit = _cell(row, ACTS_COLUMNS["medical_unit"])
        if parsed_date is None or not medical_unit:
            continue
        products = tuple(
            product
            for product in (
                _cell(row, ACTS_COLUMNS["product_one"]),
                _cell(row, ACTS_COLUMNS["product_two"]),
                _cell(row, ACTS_COLUMNS["product_three"]),
            )
            if product
        )
        rows.append(
            ActivityRow(
                source_tab=tab_name,
                source_row=index,
                activity_date=parsed_date,
                psr=_cell(row, ACTS_COLUMNS["psr"]),
                medical_unit=medical_unit,
                activity_type=_cell(row, ACTS_COLUMNS["activity_type"]),
                products=products,
                lecturer=_cell(row, ACTS_COLUMNS["lecturer"]),
                dining_cost=_cell(row, ACTS_COLUMNS["dining_cost"]),
                sample_fee=_cell(row, ACTS_COLUMNS["sample_fee"]),
                speaker_fee=_cell(row, ACTS_COLUMNS["speaker_fee"]),
                two_season_sales=_cell(row, ACTS_COLUMNS["two_season_sales"]),
            )
        )
    return rows


def filter_activity_window(
    rows: list[ActivityRow],
    *,
    today: date,
    lookback_days: int = 14,
    lookahead_days: int = 0,
) -> list[ActivityRow]:
    start_date = today - timedelta(days=lookback_days)
    end_date = today + timedelta(days=lookahead_days)
    return [row for row in rows if start_date <= row.activity_date <= end_date]


def add_business_days(start: date, days: int) -> date:
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def build_shipping_message(row: ShipmentRow) -> str:
    arrival = add_business_days(row.sales_date, 3)
    return SHIPPING_NOTICE_TEMPLATE.format(
        product=row.product,
        arrival_date=arrival.isoformat(),
        sales_date=row.sales_date.isoformat(),
    )


def row_source(row: ShipmentRow) -> dict[str, Any]:
    return {
        "tab": row.source_tab,
        "row": row.source_row,
        "product": row.product,
        "date": row.sales_date.isoformat(),
        "code": row.code,
    }


def activity_source(row: ActivityRow) -> dict[str, Any]:
    return {
        "tab": row.source_tab,
        "row": row.source_row,
        "date": row.activity_date.isoformat(),
        "psr": row.psr,
        "medical_unit": row.medical_unit,
        "activity_type": row.activity_type,
        "products": list(row.products),
        "lecturer": row.lecturer,
    }


def parse_sheet_date(value: str) -> date | None:
    text = value.strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _cell(row: list[str], index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index]).strip()


def load_values_from_json(path: str | Path) -> list[list[str]]:
    import json

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of rows.")
    return data
