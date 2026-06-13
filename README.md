# LINE Edge Selenium Project

This project drives Microsoft Edge with the LINE extension loaded.

## Setup

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Launch / Probe

```powershell
.\.venv\Scripts\python.exe .\launch_line_extension.py
```

The script:

- starts Edge through Selenium
- loads the installed LINE extension
- opens `chrome-extension://ophjlpahpchlmihnnnihgmmeilfjmjjc/index.html`
- saves a screenshot under `screenshots/`
- prints the page title, URL, and visible text

## Credentials

Do not put LINE credentials in source files. If a later automation script needs login, pass them through environment variables:

```powershell
$env:LINE_EMAIL="your-line-email@example.com"
$env:LINE_PASSWORD="your-line-password"
```

Before any script submits LINE credentials, confirm the action in chat.

## Messaging Automation

See `LINE_MESSAGING_AUTOMATION_PLAN.md` for the current refactor plan around stable friend/group matching, batch messaging, audit logs, dry-run mode, and safer expansion.

## Scenario Draft Workflow

The newer workflow is sheet-review first:

1. Build scenario drafts from Google Sheets into `LINE_Drafts`.
2. Review the message text in `LINE_Drafts`.
3. Set `Status=approved` and `Send_Mode=live` only for rows that should be eligible to send.
4. Run the approved sender with an explicit live-send command.

Build all scenario drafts:

```powershell
.\.venv\Scripts\python.exe -m app.line_draft_builder --types all --max-per-type 10
```

Preview approved rows without sending:

```powershell
.\.venv\Scripts\python.exe -m app.approved_draft_sender --max-rows 10
```

Live-send approved rows:

```powershell
.\.venv\Scripts\python.exe -m app.approved_draft_sender --send-approved --max-rows 10
```

Live sending still requires a nonblank approved draft, `Send_Mode=live`, quota allowance, safe risk flags, and an unambiguous LINE match. Group rows are blocked unless the target is listed in `LINE_ALLOWED_GROUP_TARGETS`.

## PSR-Style Automations

Safe first commands:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m app.line_draft_builder --date 2026-06-06 --source-json data\fixtures\line_sources_sample.json --no-write --no-ai
automations\10_LINE_Message_Test\preview.cmd
automations\20_Shipping_Notice_Schedule\run_preview.cmd --max-rows 10
automations\30_Reminder_Builder\run_preview.cmd --types all --max-rows 20
```

The new workflow is preview-only by default. Live sends require `--send` and a nonblank `Line暱稱` for the task `Customer_ID` in the `List` sheet. Group sends still require `LINE_ALLOWED_GROUP_TARGETS`.

Reference docs:

- `docs/line-with-pictures.md`
- `docs/line-messaging-runbook.md`
- `docs/line-bot-scenario-reference.md`
- `docs/development-reference.md`
- `docs/google-sheet-dy2-reference.md`
- `docs/stability-and-precautions.md`
