# Google Sheet Reference

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

## Scenario Draft Sheets

The scenario draft workflow uses the same workbook, but the service account must have read/write scope:

```text
https://www.googleapis.com/auth/spreadsheets
```

The bot creates or updates `LINE_Drafts` with these headers:

```text
Draft_ID, Created_At, Trigger_Type, Source_Sheets, Source_Refs, Customer_ID,
Customer_Name, Line_Query, Product, Signal_Summary, Draft_Message, Risk_Level,
Safety_Flags, Status, Send_Mode, Approved_By, Approved_At, Sent_At, Result,
Error_Message
```

Human review fields:

- `Status`: defaults to `pending_review`; set to `approved` only after review.
- `Send_Mode`: defaults to `review`; set to `live` only when the row may be sent.
- `Approved_By` and `Approved_At`: optional but recommended for traceability.
- `Sent_At`, `Result`, and `Error_Message`: updated by the approved sender.

The mandatory `log` sheet uses:

```text
Timestamp, Bot_Name, Trigger_Type, Source_Sheets, Customer_ID, Customer_Name,
Product, Draft_Status, Message_Risk_Level, Human_Review_Required, Result,
Error_Message
```

If `LINE_Drafts` or `log` already exists with different first-row headers, the Python gateway stops with a header mismatch error instead of rewriting row 1. Fix the sheet header deliberately before rerunning.

## Scenario Commands

Build drafts into Sheets:

```powershell
.\.venv\Scripts\python.exe -m app.line_draft_builder --types all --max-per-type 10
```

Preview approved rows:

```powershell
.\.venv\Scripts\python.exe -m app.approved_draft_sender --max-rows 10
```

Live-send approved rows:

```powershell
.\.venv\Scripts\python.exe -m app.approved_draft_sender --send-approved --max-rows 10
```
