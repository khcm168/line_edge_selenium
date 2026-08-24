from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.scenario_engine import ScenarioDraft, draft_to_log_event, taipei_now_iso
from app.sheet_gateway import SheetGateway


SOURCE_SHEET = "26-27疫苗"
PRODUCT = "Fluadd"
HASHTAG = "Fluadd shipping"
PREFERRED_SEND_TIME = "07:30AM"

ORDER_NO = 0
CLINIC_NAME = 4
QTY = 5
UNIT_PRICE = 6
TOTAL_AMOUNT = 7
CONTACT_NAME = 8
CONTACT_PHONE = 9
PAYMENT_METHOD = 10
SHIPPING_ADDRESS = 11
SHORT_NAME = 12
CUSTOMER_ID = 13
DRAFT_MESSAGE = 15


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Fluadd shipping LINE_Drafts from 26-27疫苗.")
    parser.add_argument("--source-sheet", default=SOURCE_SHEET)
    parser.add_argument("--hashtag", default=HASHTAG)
    parser.add_argument("--preferred-send-time", default=PREFERRED_SEND_TIME)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env(require_google=True)
    gateway = SheetGateway.from_settings(settings)
    worksheet = gateway.spreadsheet.worksheet(args.source_sheet)
    values = worksheet.get_all_values()

    created_at = taipei_now_iso()
    drafts: list[ScenarioDraft] = []
    blank_customer_id_rows: list[int] = []
    blank_message_rows: list[int] = []

    for row_number, row in enumerate(values[1:], start=2):
        customer_id = cell(row, CUSTOMER_ID)
        if not customer_id:
            blank_customer_id_rows.append(row_number)
            continue
        message = cell(row, DRAFT_MESSAGE)
        if not message:
            blank_message_rows.append(row_number)
            continue
        order_no = cell(row, ORDER_NO)
        clinic_name = cell(row, CLINIC_NAME) or cell(row, SHORT_NAME)
        source_key = f"{args.source_sheet}|{row_number}|{order_no}|{customer_id}|{PRODUCT}"
        draft_id = "fluadd_" + hashlib.sha1(source_key.encode("utf-8")).hexdigest()[:12]
        drafts.append(
            ScenarioDraft(
                draft_id=draft_id,
                created_at=created_at,
                trigger_type="logistics",
                source_sheets=(args.source_sheet,),
                source_refs={
                    "tab": args.source_sheet,
                    "row": row_number,
                    "order_no": order_no,
                    "line_query_source": "customer_id column N",
                    "draft_message_source": "column P",
                },
                customer_id=customer_id,
                customer_name=clinic_name,
                line_query=customer_id,
                product=PRODUCT,
                signal_summary=signal_summary(row, order_no),
                draft_message=message,
                risk_level="low",
                hashtag=args.hashtag,
                preferred_send_time=args.preferred_send_time,
                remark=(
                    "Generated from 26-27疫苗; Line_Query uses column N customer_id; "
                    "blank customer_id rows were left untouched."
                ),
            )
        )

    existing_ids = set()
    if gateway._maybe_worksheet(settings.draft_sheet_name) is not None:
        existing_ids = {row.draft.draft_id for row in gateway.read_draft_rows() if row.draft.draft_id}
    new_drafts = [draft for draft in drafts if draft.draft_id not in existing_ids]

    written_drafts = 0
    written_logs = 0
    if not args.no_write:
        written_drafts = gateway.append_drafts(new_drafts)
        force_preferred_send_time_text(gateway, [draft.draft_id for draft in new_drafts], args.preferred_send_time)
        written_logs = gateway.append_log_events([draft_to_log_event(draft) for draft in new_drafts])

    print(f"source_sheet={args.source_sheet}")
    print(f"source_row_count={max(len(values) - 1, 0)}")
    print(f"blank_customer_id_rows={','.join(map(str, blank_customer_id_rows))}")
    print(f"blank_message_rows={','.join(map(str, blank_message_rows))}")
    print(f"candidate_draft_count={len(drafts)}")
    print(f"existing_draft_skip_count={len(drafts) - len(new_drafts)}")
    print(f"new_draft_count={len(new_drafts)}")
    print(f"draft_count={written_drafts}")
    print(f"log_count={written_logs}")
    print(f"draft_sheet={settings.draft_sheet_name}")
    print(f"sheets_written={str(not args.no_write).lower()}")
    return 0


def cell(row: list[str], index: int) -> str:
    return str(row[index]).strip() if index < len(row) else ""


def signal_summary(row: list[str], order_no: str) -> str:
    parts = [
        "Fluadd shipping confirmation",
        f"order {order_no}" if order_no else "",
        f"qty {cell(row, QTY)}" if cell(row, QTY) else "",
        f"unit NT$ {cell(row, UNIT_PRICE)}" if cell(row, UNIT_PRICE) else "",
        f"total NT$ {cell(row, TOTAL_AMOUNT)}" if cell(row, TOTAL_AMOUNT) else "",
        f"contact {cell(row, CONTACT_NAME)}" if cell(row, CONTACT_NAME) else "",
        f"phone {cell(row, CONTACT_PHONE)}" if cell(row, CONTACT_PHONE) else "",
        f"payment {cell(row, PAYMENT_METHOD)}" if cell(row, PAYMENT_METHOD) else "",
        f"address {cell(row, SHIPPING_ADDRESS)}" if cell(row, SHIPPING_ADDRESS) else "",
    ]
    return "; ".join(part for part in parts if part)


def force_preferred_send_time_text(gateway: SheetGateway, draft_ids: list[str], value: str) -> None:
    if not draft_ids:
        return
    worksheet = gateway.ensure_draft_sheet()
    headers = worksheet.row_values(1)
    try:
        column = headers.index("Preferred_Send_Time") + 1
    except ValueError:
        return
    draft_id_set = set(draft_ids)
    updates = [
        {"range": a1(row.row_number, column), "values": [[value]]}
        for row in gateway.read_draft_rows()
        if row.draft.draft_id in draft_id_set
    ]
    if updates:
        worksheet.batch_update(updates, value_input_option="RAW")


def a1(row: int, column: int) -> str:
    letters = ""
    current = column
    while current:
        current, remainder = divmod(current - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


if __name__ == "__main__":
    raise SystemExit(main())
