# Google Sheet DY2 Reference

Main source workbook:

- Title: `地區會議資料V8.0 beta`
- Spreadsheet ID: `1eTnZppbhu7fpwdFTrnFoQmxchylsZus0Sw4j1t61Zzo`
- Tab: `DY2`

Shipping notice source columns:

| Field | Column | Header |
| --- | --- | --- |
| Product | A | 品名 |
| Sales date | I | 銷售日期 |
| Customer code | AD | 代號 |

The generated LINE message is:

```text
{品名}產品預計三個工作天({銷售日期}+3 working days)到貨，請留意
```

The first implementation uses `代號` as the LINE search query because existing LINE display names may include customer codes.

`Acts` reminder previews use the visible activity sheet columns: date, PSR, medical unit, activity type, product one/two/three, lecturer, dining cost, sample fee, speaker fee, and two-season sales. Activity follow-up messages search by medical unit and are always manual-review tasks.
