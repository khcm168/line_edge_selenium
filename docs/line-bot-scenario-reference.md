# LINE Bot Scenario Reference

This document summarizes the Python hybrid scenario layer implemented in `app.scenario_engine`.

## Review Contract

All generated rows are drafts, not sends. A row becomes eligible for live sending only when a human sets:

- `Status=approved`
- `Send_Mode=live`
- `Sent_At` is blank

The sender still blocks blank messages, high-risk drafts, privacy/overclaim flags, quota violations, ambiguous LINE matches, and unapproved group targets.

## Scenario Types

| Trigger type | Primary source candidates | Required signal | Default risk |
| --- | --- | --- | --- |
| `logistics` | `DY2`, `Y2`, `OPSR2` | Product, line query/customer code, sale date within today/tomorrow | low |
| `stocking_reorder` | `LOST_Recovery`, `Bridge_Logic`, `DY2` | Product, line query, low stock/reorder/old sale signal | low |
| `promotion` | `marketing`, `discount`, `母親節` | Approved campaign/event row and line query | medium |
| `referral_thanks` | `推薦`, `cases`, `V`, `List` | Referral event and line query | low |
| `new_product` | `DY2` | New product flag marked Y/yes/true and product | medium |
| `usage_reminder` | `DY2`, `Product_Master`, `HA客戶n` | HA product or explicit usage education flag | low |
| `new_customer` | `adr` | New customer row, preferably created today | low |
| `lost_recovery` | `LOST_Recovery`, `XLOST_Recovery` | Lost flag or long interval days | low |
| `price_adjustment` | `Price_Adjustment`, `checkVariations`, `Y2`, `DY2` | Price change/variation flag | medium |
| `continue_topic` | `Line`, `今日拜訪`, `List`, `V` | Last topic/open loop/next action | low |
| `relationship_temperature` | `Line`, `List`, `今日拜訪` | Low/cold response quality or old last contact | low |
| `activity_followup` | `Acts`, `ACT4P12`, `大型活動` | Activity date within the lookback window and line query/medical unit | low |

## Header Policy

The detector accepts simple English headers such as `product`, `customer_id`, `sales_date`, `line_query`, `status`, `interval_days`, and `activity_date`. It also keeps positional fallbacks for known `DY2` and `Acts` layouts.

When a sheet is missing, a trigger logs `skipped: source sheet not available`. When a sheet exists but required fields are missing, it logs `skipped: no matching signal`. It does not guess message recipients or products from unrelated columns.

## AI Drafting

`app.ai_drafter` treats AI as a constrained rewrite step:

- The scenario engine chooses the trigger and approved template first.
- AI receives only minimal business context.
- The output must include message, risk level, safety flags, and rationale.
- Local Ollama is the default provider; OpenAI is opt-in with `LINE_AI_PROVIDER=openai`.
- If AI is unavailable or returns invalid output, the approved template is used.
- Medical overclaim and patient privacy terms raise the risk to high and block live send.

## Output Sheets

`LINE_Drafts` is the human review surface. `log` is the execution ledger. See `docs/google-sheet-dy2-reference.md` for columns and command examples.
