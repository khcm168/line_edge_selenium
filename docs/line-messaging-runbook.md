# LINE Messaging Runbook

For implementation details and lessons learned from live Selenium tests, see `docs/development-reference.md`.

## Safe Run Order

1. Build or preview tasks before any live send.
2. Review `data/tasks/*.json` and `data/logs/*.jsonl`.
3. Run LINE preview against the controlled test targets.
4. Only then run a live test with `--send`, and only for approved targets.

For scenario drafts, use the sheet-review flow:

1. Build drafts into `LINE_Drafts`.
2. Human reviews the draft text and risk flags in the sheet.
3. Human sets `Status=approved` and `Send_Mode=live`.
4. Run the approved sender preview.
5. Live-send only with `--send-approved`.

## Commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m app.line_draft_builder --date 2026-06-06 --source-json data\fixtures\line_sources_sample.json --no-write --no-ai
automations\10_LINE_Message_Test\preview.cmd
automations\20_Shipping_Notice_Schedule\run_preview.cmd --max-rows 10
automations\30_Reminder_Builder\run_preview.cmd --types all --max-rows 20
```

To inspect generated shipping notice quality in `LINE_Drafts`, add `--write-drafts`:

```powershell
automations\20_Shipping_Notice_Schedule\run_preview.cmd --date 2026-06-08 --max-rows 20 --write-drafts
```

For live Google Sheets reads, copy `.env.example` to `.env`, set `GOOGLE_APPLICATION_CREDENTIALS` or `SERVICE_ACCOUNT_FILE`, and share `地區會議資料V8.0 beta` with that service account. The workflow also accepts `SPREADSHEET_ID` from `psr-aios-v1` as an alias for `LINE_SOURCE_SPREADSHEET_ID`. The service account now needs read/write access because the scenario workflow creates or updates `LINE_Drafts` and appends rows to `log`.

## Scenario Draft Builder

Build all scenario drafts from Google Sheets and append missing `LINE_Drafts` rows plus `log`:

```powershell
.\.venv\Scripts\python.exe -m app.line_draft_builder --types all --max-per-type 10
```

`LINE_Drafts` writes are keyed by `Draft_ID`; rerunning the builder skips draft IDs that are already present so pending-review rows are not duplicated. Review decisions in existing rows remain the source of truth.

Build deterministic template drafts without AI rewriting:

```powershell
.\.venv\Scripts\python.exe -m app.line_draft_builder --types all --no-ai --max-per-type 10
```

Run locally against the sample fixture without writing Sheets:

```powershell
.\.venv\Scripts\python.exe -m app.line_draft_builder --date 2026-06-06 --source-json data\fixtures\line_sources_sample.json --no-write --no-ai
```

AI rewriting defaults to local Ollama and is controlled by `LINE_AI_ENABLED`, `LINE_AI_PROVIDER`, `OLLAMA_BASE_URL`, and `OLLAMA_MODEL`. Set `LINE_AI_PROVIDER=openai` with `OPENAI_API_KEY` and `OPENAI_MODEL` only when OpenAI should be used. If AI is disabled or unavailable, the builder falls back to the approved scenario templates and records the fallback in the draft result.

## Approved Draft Sender

Preview approved rows without opening LINE:

```powershell
.\.venv\Scripts\python.exe -m app.approved_draft_sender --max-rows 10
```

Write approved rows to a local task JSON for inspection:

```powershell
.\.venv\Scripts\python.exe -m app.approved_draft_sender --write-tasks data\tasks\approved_line_drafts.json --max-rows 10
```

Live-send approved rows:

```powershell
.\.venv\Scripts\python.exe -m app.approved_draft_sender --send-approved --max-rows 10
```

Rows are skipped unless all are true: `Status=approved`, `Send_Mode=live`, message is nonblank, `Sent_At` is blank, risk is not high, privacy/overclaim flags are absent, and LINE matching is unambiguous. Group sends are blocked unless the `Line_Query` is listed in `LINE_ALLOWED_GROUP_TARGETS`.

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

Generated reminder batches are marked `manual_required=true`, so they cannot be sent live by accident. Use them for preview and manual chat-open approval; live eligibility comes from `Customer_ID` plus `Line暱稱` in the `List` sheet.

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

Live sends require `--send`, a non-empty message, an unambiguous match, writable audit logs, snapshots, quota allowance, no `manual_required` flag, and `Customer_ID` plus `Line_Contact` from the `List` sheet. The default workflow is preview only.

## Reminder Builder

The all-reminder preview builder reads `DY2` and `Acts`, then writes a local task JSON:

```powershell
.\.venv\Scripts\python.exe -m app.reminder_builder --date 2026-06-01 --types all --max-rows 20
```

Rules live in `data/reminder_rules.json`. The defaults include shipping, required feedback, free goods, usage, activity follow-up, repurchase, and app reminders. Missing or disabled templates are skipped during preview rather than guessed.
