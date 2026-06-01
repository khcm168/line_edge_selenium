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
$env:LINE_EMAIL="kevin@top-pharm.com.tw"
$env:LINE_PASSWORD="0178JmLut"
```

Before any script submits LINE credentials, confirm the action in chat.

## Messaging Automation

See `LINE_MESSAGING_AUTOMATION_PLAN.md` for the current refactor plan around stable friend/group matching, batch messaging, audit logs, dry-run mode, and safer expansion.

## PSR-Style Automations

Safe first commands:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
automations\10_LINE_Message_Test\preview.cmd
automations\20_Shipping_Notice_Schedule\run_preview.cmd --max-rows 10
automations\30_Reminder_Builder\run_preview.cmd --types all --max-rows 20
```

The new workflow is preview-only by default. Live sends require `--send` and are limited to approved test targets unless `LINE_ALLOWED_LIVE_TARGETS` is changed deliberately.

Reference docs:

- `docs/line-messaging-runbook.md`
- `docs/development-reference.md`
- `docs/google-sheet-dy2-reference.md`
- `docs/stability-and-precautions.md`
