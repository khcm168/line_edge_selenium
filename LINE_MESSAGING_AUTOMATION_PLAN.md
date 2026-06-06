# LINE Friends Messaging Automation Plan

## Purpose

Build a stable, expandable Selenium automation layer for LINE Edge extension friend/group messaging.

## Current Implementation Note

The PSR-style workflow now lives in:

- `app/line_batch.py` for LINE preview/send task execution.
- `app/line_draft_builder.py` for scenario-based `LINE_Drafts` generation.
- `app/approved_draft_sender.py` for sheet-approved live sends.
- `app/scenario_engine.py`, `app/ai_drafter.py`, and `app/sheet_gateway.py` for the hybrid draft/review layer.
- `app/shipping_notice.py` for `DY2` shipping notice task generation.
- `automations/10_LINE_Message_Test/` for controlled LINE target previews.
- `automations/20_Shipping_Notice_Schedule/` for preview-only scheduled task generation.
- `docs/line-messaging-runbook.md` for operator instructions.

Current proven behavior:

- Launch Edge with the LINE extension.
- Login through environment variables and phone verification when needed.
- Search LINE contacts/groups.
- Distinguish friend rows from group rows by visible category labels.
- Open a matched chat.
- Send text through the LINE composer, using DOM input fields when available and Chrome DevTools coordinate typing as fallback.
- Run multiple sends in one browser session without quitting/relogging.
- Build all manual scenario types as review-only drafts in `LINE_Drafts`.
- Append generation, skip, error, and send records to the workbook `log` sheet.
- Live-send only rows approved in `LINE_Drafts` with `Status=approved` and `Send_Mode=live`.

For the current scenario workflow, see:

- `docs/line-bot-scenario-reference.md`
- `docs/line-messaging-runbook.md`
- `docs/google-sheet-dy2-reference.md`

## Current Files

- `login_probe.py`
  - Owns Edge setup, extension URL, login, phone verification, screenshots, and visible text dumping.
- `send_test_message.py`
  - Current reusable messaging helpers:
    - `ensure_friends`
    - `search_friend`
    - `visible_rows_with_category`
    - `open_exact_chat`
    - `send_message`
- `send_sequential_test_messages.py`
  - Hard-coded two-message batch test:
    - `洪啓明` as `好友`
    - `001N1備份區` as group/any category
- `rename_bell_matches.py`
  - Friend-name rename workflow. Some interaction helpers may be reusable, but messaging should not depend on this file.

## Stability Goals

1. Keep one browser session for a batch.
   - Login and phone verification are the most fragile steps.
   - A batch should call `ensure_friends` once, then perform many search/open/send operations.

2. Treat matching as a first-class decision.
   - LINE search can return both `群組` and `好友`.
   - A query like `洪啓明` may return many group hits plus one friend hit.
   - The automation must never assume the first result is correct unless the task explicitly says so.

3. Use clear match policies.
   - `exact_friend`: only accept an exact row under `好友`.
   - `exact_group`: only accept an exact row under `群組`.
   - `unique_contains_friend`: accept one friend row containing the query.
   - `unique_contains_any`: accept one visible row containing the query.
   - `all_exact`: send to all exact matches, only for explicitly approved batch tests.
   - `manual_required`: log candidates and skip when ambiguous.

4. Prefer selectors, then fallback to coordinates.
   - Search results are selectable through DOM.
   - The chat composer is sometimes a custom editor, so coordinate click + CDP text insert is a necessary fallback.
   - Coordinate logic should be isolated and logged.

5. Verify after action.
   - After opening a chat, verify header text and category decision.
   - After sending, wait briefly and verify the outgoing message text appears in visible page text when possible.
   - Always screenshot on failure.

## Proposed Refactor

Create these modules:

```text
line_edge_selenium/
  line_client.py
  line_matcher.py
  line_messaging.py
  line_audit.py
  run_message_batch.py
  tasks/
    sample_messages.json
```

### `line_client.py`

Responsibilities:

- Build Edge driver.
- Login and wait for phone verification.
- Navigate to `#/friends`.
- Dump state and screenshots.
- Own common waits and retries.

### `line_matcher.py`

Responsibilities:

- Search for a query.
- Collect candidates as structured data:

```python
{
    "category": "好友",
    "display_name": "洪啓明",
    "normalized_name": "洪啟明",
    "row_index": 0,
    "element": row,
}
```

- Apply match policies.
- Return either one match, many approved matches, or an ambiguity result.

### `line_messaging.py`

Responsibilities:

- Open chat from a matched candidate.
- Verify chat header.
- Send message.
- Verify sent message if possible.

### `line_audit.py`

Responsibilities:

- Write JSONL or CSV audit records.
- Keep enough detail for later sheet update or debugging:

```text
timestamp, action, query, policy, matched_category, matched_name, status, detail, screenshot
```

### `run_message_batch.py`

Responsibilities:

- Load a JSON task list.
- Start one Selenium session.
- Run tasks sequentially.
- Stop only when configured:
  - `continue_on_error=true`
  - `stop_on_ambiguous=true`

## Task Format

Recommended JSON:

```json
[
  {
    "action": "send_message",
    "query": "洪啓明",
    "match_policy": "exact_friend",
    "message": "小測試：洪啓明，這是一則 LINE 自動化測試訊息。",
    "verify_text": true
  },
  {
    "action": "send_message",
    "query": "001N1備份區",
    "match_policy": "exact_group",
    "message": "小測試：001N1備份區，這是一則同一個 Selenium session 的測試訊息。",
    "verify_text": true
  }
]
```

## Retry Strategy

Per task:

1. Clear search box and search.
2. Wait for either candidates or no-result text.
3. Apply match policy.
4. Open chat.
5. Verify header.
6. Click composer.
7. Insert text.
8. Send Enter.
9. Verify/send audit.

Retry only safe steps:

- Search may retry 2 times.
- Opening chat may retry 1 time if header does not change.
- Sending should not blindly retry after Enter unless verification proves no message was sent.

## Safety Rules

- Do not send messages when candidate matching is ambiguous.
- Do not send to groups unless the task policy allows `group`.
- Do not send blank messages.
- Do not reuse stale row elements after a new search.
- Do not keep credentials in source files.
- Save a screenshot on every error or ambiguity.

## Near-Term Work Plan

1. Move shared helpers out of `send_test_message.py` into `line_client.py`, `line_matcher.py`, and `line_messaging.py`.
2. Replace `send_sequential_test_messages.py` hard-coded list with `run_message_batch.py --tasks tasks/sample_messages.json`.
3. Add JSONL audit output under `logs/`.
4. Add `--dry-run` mode:
   - Search and resolve target.
   - Do not open chat/send message.
   - Print matched candidate decision.
5. Add `--keep-open` mode for observed debugging.
6. Add post-send verification and screenshot on failure.
7. Later: connect task input/output to Google Sheets for row-by-row audit.

## Open Questions

- Should group sends be disabled by default and require `allow_group: true`?
- Should the default ambiguity behavior be skip or pause for manual selection?
- Do we want message templates with variables from Google Sheets, such as customer name, AKA, code, or product?
- Should audit be local JSONL first, then optionally written back to Sheets?
