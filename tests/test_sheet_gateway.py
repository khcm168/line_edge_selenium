import unittest

from app.scenario_engine import ScenarioDraft, ScenarioEvent
from app.sheet_gateway import SheetGateway


class FakeWorksheet:
    def __init__(self, title):
        self.title = title
        self.values = []
        self.batch_updates = []

    def row_values(self, row):
        if row <= len(self.values):
            return self.values[row - 1]
        return []

    def update(self, cell, values, value_input_option=None):
        if cell != "A1":
            raise AssertionError(cell)
        if self.values:
            self.values[0] = values[0]
        else:
            self.values.append(values[0])

    def append_rows(self, rows, value_input_option=None):
        self.values.extend(rows)

    def get_all_values(self):
        return self.values

    def batch_update(self, cells, value_input_option=None):
        self.batch_updates.extend(cells)


class FakeSpreadsheet:
    def __init__(self):
        self.sheets = {}

    def worksheet(self, title):
        if title not in self.sheets:
            raise KeyError(title)
        return self.sheets[title]

    def add_worksheet(self, title, rows, cols):
        worksheet = FakeWorksheet(title)
        self.sheets[title] = worksheet
        return worksheet


def sample_draft():
    return ScenarioDraft(
        draft_id="draft1",
        created_at="2026-06-06T09:00:00+08:00",
        trigger_type="new_customer",
        source_sheets=("adr",),
        source_refs={"tab": "adr", "row": 2},
        customer_id="P100",
        customer_name="Clinic A",
        line_query="P100",
        product="",
        signal_summary="new customer",
        draft_message="您好",
    )


class SheetGatewayTest(unittest.TestCase):
    def test_appends_drafts_and_log_events_with_headers(self):
        spreadsheet = FakeSpreadsheet()
        gateway = SheetGateway(spreadsheet, draft_sheet_name="LINE_Drafts", log_sheet_name="log")

        self.assertEqual(gateway.append_drafts([sample_draft()]), 1)
        self.assertEqual(
            gateway.append_log_events(
                [
                    ScenarioEvent(
                        timestamp="2026-06-06T09:00:00+08:00",
                        trigger_type="new_customer",
                        source_sheets=("adr",),
                        draft_status="generated",
                        result="ok",
                    )
                ]
            ),
            1,
        )

        self.assertEqual(spreadsheet.sheets["LINE_Drafts"].values[0][0], "Draft_ID")
        self.assertEqual(spreadsheet.sheets["LINE_Drafts"].values[1][0], "draft1")
        self.assertEqual(spreadsheet.sheets["log"].values[0][0], "Timestamp")
        self.assertEqual(spreadsheet.sheets["log"].values[1][2], "new_customer")

    def test_append_drafts_skips_existing_draft_ids(self):
        spreadsheet = FakeSpreadsheet()
        gateway = SheetGateway(spreadsheet, draft_sheet_name="LINE_Drafts", log_sheet_name="log")

        self.assertEqual(gateway.append_drafts([sample_draft()]), 1)
        self.assertEqual(gateway.append_drafts([sample_draft()]), 0)

        self.assertEqual(len(spreadsheet.sheets["LINE_Drafts"].values), 2)
        self.assertEqual(spreadsheet.sheets["LINE_Drafts"].values[1][0], "draft1")

    def test_append_drafts_deduplicates_ids_within_batch(self):
        spreadsheet = FakeSpreadsheet()
        gateway = SheetGateway(spreadsheet, draft_sheet_name="LINE_Drafts", log_sheet_name="log")

        self.assertEqual(gateway.append_drafts([sample_draft(), sample_draft()]), 1)

        self.assertEqual(len(spreadsheet.sheets["LINE_Drafts"].values), 2)
        self.assertEqual(spreadsheet.sheets["LINE_Drafts"].values[1][0], "draft1")

    def test_reads_and_updates_draft_rows(self):
        spreadsheet = FakeSpreadsheet()
        gateway = SheetGateway(spreadsheet, draft_sheet_name="LINE_Drafts", log_sheet_name="log")
        gateway.append_drafts([sample_draft()])

        rows = gateway.read_draft_rows()
        gateway.update_draft_result(rows[0].row_number, status="sent", sent_at="now", result="sent")

        updated_ranges = {item["range"] for item in spreadsheet.sheets["LINE_Drafts"].batch_updates}
        self.assertIn("N2", updated_ranges)
        self.assertIn("R2", updated_ranges)
        self.assertIn("S2", updated_ranges)

    def test_existing_header_mismatch_is_not_overwritten(self):
        spreadsheet = FakeSpreadsheet()
        worksheet = FakeWorksheet("LINE_Drafts")
        worksheet.values = [["Wrong", "Header"]]
        spreadsheet.sheets["LINE_Drafts"] = worksheet
        gateway = SheetGateway(spreadsheet, draft_sheet_name="LINE_Drafts", log_sheet_name="log")

        with self.assertRaises(RuntimeError):
            gateway.append_drafts([sample_draft()])

        self.assertEqual(worksheet.values[0], ["Wrong", "Header"])

    def test_existing_legacy_draft_header_is_extended(self):
        spreadsheet = FakeSpreadsheet()
        worksheet = FakeWorksheet("LINE_Drafts")
        worksheet.values = [[
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
        ]]
        spreadsheet.sheets["LINE_Drafts"] = worksheet
        gateway = SheetGateway(spreadsheet, draft_sheet_name="LINE_Drafts", log_sheet_name="log")

        gateway.ensure_draft_sheet()

        self.assertIn("Line_Contact", worksheet.values[0])
        self.assertIn("Line_Message_Style", worksheet.values[0])
        self.assertIn("Material_ID", worksheet.values[0])
        self.assertIn("Image_Path", worksheet.values[0])
        self.assertIn("Message_Kind", worksheet.values[0])
        self.assertIn("Material_SHA256", worksheet.values[0])


if __name__ == "__main__":
    unittest.main()
