# LINE Messaging Runbook

For implementation details and lessons learned from live Selenium tests, see `docs/development-reference.md`.

## Safe Run Order

1. Build or preview tasks before any live send.
2. Review `data/tasks/*.json` and `data/logs/*.jsonl`.
3. Run LINE preview against the controlled test targets.
4. Only then run a live test with `--send`, and only for approved targets.

## Commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
automations\10_LINE_Message_Test\preview.cmd
automations\20_Shipping_Notice_Schedule\run_preview.cmd --max-rows 10
automations\30_Reminder_Builder\run_preview.cmd --types all --max-rows 20
```

For live Google Sheets reads, copy `.env.example` to `.env`, set `GOOGLE_APPLICATION_CREDENTIALS` or `SERVICE_ACCOUNT_FILE`, and share `地區會議資料V8.0 beta` with that service account. The workflow also accepts `SPREADSHEET_ID` from `psr-aios-v1` as an alias for `LINE_SOURCE_SPREADSHEET_ID`.

## Manual Approval Mode

Use this before a limited live test. It searches, resolves the safe friend/group policy, opens the matched chat, writes snapshots/audit, and stops before typing or sending:

```powershell
.\.venv\Scripts\python.exe -m app.line_batch --manual-approve --tasks data\tasks\shipping_notice_2026-06-01.json
```

After you visually confirm the chat, close Edge or run the live command separately. Do not add `--send` to the manual approval command.

## Handoff Mode

Preferred handoff mode uses a persistent worker. Start it in Terminal 1:

```powershell
.\.venv\Scripts\python.exe -m app.handoff_worker
```

Before starting the worker, close old automation-controlled Edge windows that use this project profile. Only one process can own `edge-profile` at a time.

Leave Terminal 1 and Edge open. Submit work from Terminal 2:

```powershell
.\.venv\Scripts\python.exe -m app.handoff_worker --submit --manual-approve --tasks data\tasks\manual_test_2_contacts.json
```

For live send after visual confirmation:

```powershell
.\.venv\Scripts\python.exe -m app.handoff_worker --submit --send --tasks data\tasks\manual_test_2_contacts.json
```

Generated reminder batches are marked `manual_required=true`, so they cannot be sent live by accident. Use them for preview and manual chat-open approval; keep live sends to the controlled smoke targets unless the allowlist and rule file are deliberately changed.

Stop the worker:

```powershell
.\.venv\Scripts\python.exe -m app.handoff_worker --stop
```

There is also an experimental `app.line_batch --handoff-start` / `--attach-existing` path, but the worker is more reliable because it keeps the original WebDriver process alive.

Install the preview-only scheduled task:

```powershell
automations\20_Shipping_Notice_Schedule\install_preview_task.cmd 09:00
```

## Live Send Gate

Live sends require `--send`, a non-empty message, an unambiguous match, writable audit logs, snapshots, quota allowance, no `manual_required` flag, and an allowed target. The default workflow is preview only.

## Reminder Builder

The all-reminder preview builder reads `DY2` and `Acts`, then writes a local task JSON:

```powershell
.\.venv\Scripts\python.exe -m app.reminder_builder --date 2026-06-01 --types all --max-rows 20
```

Rules live in `data/reminder_rules.json`. The defaults include shipping, required feedback, free goods, usage, activity follow-up, repurchase, and app reminders. Missing or disabled templates are skipped during preview rather than guessed.
