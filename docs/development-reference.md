# LINE Selenium Development Reference

This project automates the LINE Edge extension for small, controlled internal tasks. It must stay conservative: preview first, one browser owner, one recipient at a time, and no routine massive messaging.

## Current Architecture

Main modules:

- `app.line_batch`: preview/send runner for a task JSON file.
- `app.handoff_worker`: persistent single-owner worker. Use this when multiple scripts need to submit jobs without overlapping browser clicks.
- `app.line_draft_builder`: builds `LINE_Drafts` rows from all manual scenario types and appends workbook `log` rows.
- `app.approved_draft_sender`: previews or sends only `LINE_Drafts` rows with `Status=approved` and `Send_Mode=live`.
- `app.scenario_engine`, `app.ai_drafter`, and `app.sheet_gateway`: scenario detection, constrained AI rewrite, and Google Sheets write helpers.
- `app.line_client`: Edge/LINE session creation, login, and friend-list readiness.
- `app.line_messaging`: search, candidate collection, chat opening, composer detection, and message sending.
- `app.line_matcher`: friend/group match policies.
- `app.reminder_builder`: builds preview reminder tasks from `DY2` and `Acts`.
- `app.rate_limiter`: local quota and randomized live-send delay support for the worker.

Important data files:

- `data/reminder_rules.json`: reminder templates, timing defaults, quota, and delay settings.
- `data/tasks/*.json`: generated or hand-written task files.
- `data/logs/*.jsonl`: audit records.
- `data/snapshots/*.json` and `.png`: UI state captured for matches, sends, skips, and failures.
- `LINE_Drafts`: Google Sheet review queue for scenario-generated LINE drafts.
- `log`: Google Sheet execution ledger required by the operating manual.

## Known-Good Commands

Run tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Preview controlled smoke targets:

```powershell
.\.venv\Scripts\python.exe -m app.line_batch --test-targets --keep-open
```

Generate all reminder previews:

```powershell
.\.venv\Scripts\python.exe -m app.reminder_builder --date 2026-06-01 --types all --max-rows 20
```

Generate all scenario drafts without writing Sheets:

```powershell
.\.venv\Scripts\python.exe -m app.line_draft_builder --date 2026-06-06 --source-json data\fixtures\line_sources_sample.json --no-write --no-ai
```

Generate all scenario drafts into `LINE_Drafts`:

```powershell
.\.venv\Scripts\python.exe -m app.line_draft_builder --types all --max-per-type 10
```

Start persistent handoff worker:

```powershell
.\.venv\Scripts\python.exe -m app.handoff_worker
```

Submit manual-approval work to the worker:

```powershell
.\.venv\Scripts\python.exe -m app.handoff_worker --submit --manual-approve --tasks data\tasks\<task-file>.json
```

Live sends require `--send` and a nonblank `Line暱稱` for the task `Customer_ID` in the `List` sheet. Group sends still require `LINE_ALLOWED_GROUP_TARGETS`.

## Browser Session Rules

The normal Edge driver is configured with `detach=True` in `login_probe.build_driver()`. This is intentional. Without it, `--keep-open` can skip `driver.quit()` but Edge may still close when the Python/WebDriver process exits.

For long workflows, prefer `app.handoff_worker` over repeated `app.line_batch` runs:

- It keeps one browser session alive.
- It avoids repeated login and phone verification.
- It prevents overlapping clicks from multiple scripts.
- It gives a natural place for quota, delay, and stop-on-error policy.

Important: `--keep-open` preserves a visible detached Edge window, but not the
WebDriver session after the Python process exits. It is useful for visual
inspection, not later automation reuse. See
`docs/line-picture-live-observations-2026-06-14.md`.

Only one automation-controlled Edge window should use this project profile at a time. Close old controlled Edge windows before starting the persistent worker if the profile is locked or behavior becomes strange.

## Search And Match Behavior

LINE search results are asynchronous and can briefly show stale rows from the previous query. `app.line_messaging.search_line()` must:

- Clear the search box.
- Wait until the input value is empty.
- Type the new query.
- Wait until the input value exactly equals the new query.
- Wait for stable visible candidates that include the new query context.

Do not change this back to "return as soon as any row exists"; that caused stale-row false `no_match` results and disappearing search rows.

Current smoke targets:

| Target | Kind | Policy | Notes |
| --- | --- | --- | --- |
| `洪啓明` | friend | `unique_contains_friend` | LINE displays it with code text such as `洪啓明 P103003`. |
| `P103003` | friend lookup by code | `unique_contains_friend` | Useful when customer code is embedded in the display name. |
| `001N1備份區` | group | `unique_contains_group` | LINE may display group counts such as `001N1備份區(2)` or `001N1備份區\n(2)`. |
| `Ya.ping` | friend | `exact_friend` | Stable exact friend row in tests so far. |

Group matching should generally use `unique_contains_group`, not `exact_group`, unless the row text shape is known to be stable. Group sends must still set `allow_group=true`.

`LineCandidate.primary_normalized_name` compares only the first display line. This is important for groups because LINE appends member counts on a later line.

## Live Send Safety

Preview mode is the default. A task is live only when all are true:

- Command includes `--send`.
- Message is non-empty.
- Match is unambiguous.
- The task has `Customer_ID` plus `Line_Contact` from the `List` sheet.
- Group sends have `allow_group=true`.
- Task does not have `manual_required=true`.
- Audit and snapshot writing are available.
- Worker quota checks pass when using `app.handoff_worker`.

Generated reminder batches are intentionally marked `manual_required=true`. They are for preview and manual approval, not direct live sends.

Do not add retry-after-Enter behavior. If the send step reaches Enter, do not retry blindly. Use audit logs and screenshots to decide what happened.

## Reminder Generation

`app.reminder_builder` reads:

- `DY2`: product from column `A`, sales date from `I`, customer code from `AD`.
- `Acts`: visible activity columns from the screenshot, including date, PSR, medical unit, activity type, products, lecturer, costs, and sales context.

Supported reminder types:

- `shipping`
- `feedback`
- `free_goods`
- `usage`
- `activity_followup`
- `repurchase`
- `app`

Shipping template default:

```text
{product}產品預計三個工作天({arrival_date})到貨，請留意
```

The three-working-day arrival date skips Saturday and Sunday. Holiday calendars are not implemented yet.

If a reminder template is missing or disabled in `data/reminder_rules.json`, skip generation rather than guessing message text.

## UI Breakage Detection

The goal is to detect UI breakage, not bypass detection.

Required checks:

- Login/friends view is reachable.
- Search box exists.
- Search result candidates stabilize before matching.
- Chat composer exists before live sending.
- Screenshot and JSON snapshot are written on failures.

If LINE changes class names or behavior, inspect the latest snapshot files first. Do not immediately loosen match policy; first decide whether the candidate data is stale, misclassified, or truly ambiguous.

## Last Verified Live Behavior

On 2026-06-14, a supervised exact-friend picture test succeeded:

- Chinese sleep-care text sent through the shadow-DOM composer.
- `MAT-ACT-021` uploaded through the one-shot `showOpenFilePicker()` provider.
- LINE image auto-send completion was verified before the neutral caption was
  sent.
- The resulting image and caption were visible in the chat screenshot.

On 2026-06-01, these controlled live sends succeeded:

- `hello` to `Ya.ping`.
- `hello` to `洪啓明`.
- `hello` to group `001N1備份區`.
- `這是測試的訊息，請忽略` to all four smoke targets.

Observed fixes from that session:

- `detach=True` is required for reliable `--keep-open`.
- `unique_contains_group` is better for LINE group rows with member counts.
- Search settling must wait for the input value and stable query-specific results.
- Chat opening should accept either header visibility, composer visibility, or expected visible chat text because the header selector can time out even when the chat is open.
