import unittest
from datetime import date

from app.sheet_source import (
    add_business_days,
    build_shipping_message,
    filter_shipping_window,
    parse_acts_rows,
    parse_dy2_rows,
)


class SheetSourceTest(unittest.TestCase):
    def test_parse_dy2_rows_uses_a_i_ad(self):
        values = [
            ["品名", "包裝", "郵區", "客戶", "數量", "顆數", "單價", "總金額", "銷售日期"] + [""] * 20 + ["代號"],
            ["A+HA", "30", "104", "生泉婦產科診所", "6", "", "2,100", "10,500", "2026/5/29"] + [""] * 20 + ["P104062"],
        ]

        rows = parse_dy2_rows(values, tab_name="DY2")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].product, "A+HA")
        self.assertEqual(rows[0].sales_date, date(2026, 5, 29))
        self.assertEqual(rows[0].code, "P104062")
        self.assertEqual(rows[0].source_row, 2)

    def test_filter_shipping_window_keeps_today_and_tomorrow(self):
        values = [
            ["品名", "", "", "", "", "", "", "", "銷售日期"] + [""] * 20 + ["代號"],
            ["A+HA", "", "", "", "", "", "", "", "2026/5/29"] + [""] * 20 + ["P104062"],
            ["Q10HA", "", "", "", "", "", "", "", "2026/5/30"] + [""] * 20 + ["P247010"],
            ["iMuso", "", "", "", "", "", "", "", "2026/5/31"] + [""] * 20 + ["S247008"],
        ]

        rows = parse_dy2_rows(values)
        selected = filter_shipping_window(rows, today=date(2026, 5, 29), days=1)

        self.assertEqual([row.code for row in selected], ["P104062", "P247010"])

    def test_build_shipping_message_uses_template(self):
        row = parse_dy2_rows(
            [
                ["品名", "", "", "", "", "", "", "", "銷售日期"] + [""] * 20 + ["代號"],
                ["A+HA", "", "", "", "", "", "", "", "2026/5/29"] + [""] * 20 + ["P104062"],
            ]
        )[0]

        self.assertEqual(
            build_shipping_message(row),
            "A+HA 預計三個工作天（2026-06-03）到貨，先跟您提醒，請再留意一下。",
        )

    def test_business_days_skip_weekends(self):
        self.assertEqual(add_business_days(date(2026, 5, 29), 3), date(2026, 6, 3))

    def test_parse_acts_rows_uses_visible_columns(self):
        values = [
            ["", "", "日期", "PSR", "醫療單位", "活動類型", "產品一", "產品二", "產品三", "講師", "餐飲費用", "樣品費", "講師費", "兩季銷售額"],
            ["", "", "2026/6/3", "N1", "民生興安藥局", "健康師", "iMuso", "A+HA", "Q10HA", "Kevin", "4,000", "1,800", "", "0"],
        ]

        rows = parse_acts_rows(values)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].activity_date, date(2026, 6, 3))
        self.assertEqual(rows[0].medical_unit, "民生興安藥局")
        self.assertEqual(rows[0].products, ("iMuso", "A+HA", "Q10HA"))


if __name__ == "__main__":
    unittest.main()
