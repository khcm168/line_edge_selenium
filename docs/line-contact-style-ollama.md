# Line Contact, Style, and Ollama Drafting

This workflow uses the `List` sheet as the live-send eligibility source.

## Required Sheet Fields

`List` should include these fields, and `Data_Dictionary` should describe them:

| Sheet | Chinese name | Internal key | Purpose |
| --- | --- | --- | --- |
| `List` | `Line暱稱` | `line_contact` | LINE search name/contact for the customer |
| `List` | `Line風格` | `line_message_style` | Free-form tone guidance for draft rewriting |

The code also needs a customer identifier in the same `List` row. Accepted headers include `Customer_ID`, `customer_id`, `customer_code`, `code`, `代號`, and `客戶代號`.

## Eligibility Rule

A customer is eligible for live LINE sending only when both fields are nonblank:

- `Customer_ID`
- `Line暱稱`

`Line暱稱` becomes the actual LINE search query. `Customer_ID` remains the stable identity for audit records, quota keys, and sheet traceability.

Rows without `Line暱稱` may still be generated into `LINE_Drafts` for review, but they are skipped by live senders with `missing eligible line contact`.

Group-looking contacts still require `LINE_ALLOWED_GROUP_TARGETS`.

## LINE_Drafts Columns

`LINE_Drafts` now appends:

```text
Line_Contact, Line_Message_Style
```

If an older `LINE_Drafts` sheet has the previous header row, the gateway extends row 1 with these new headers. It does not rewrite existing row data.

## Ollama Setup

Default `.env` values:

```env
LINE_AI_ENABLED=true
LINE_AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma4:latest
OLLAMA_TIMEOUT_SECONDS=180
```

Start Ollama locally and make sure the configured model is installed before running AI drafting. To opt into OpenAI instead:

```env
LINE_AI_PROVIDER=openai
OPENAI_MODEL=gpt-4.1-mini
OPENAI_API_KEY=...
```

The AI prompt receives `line_contact` and `line_message_style`. `Line風格` is tone guidance only; safety rules still block patient privacy risk, medical overclaims, blank messages, and high-risk drafts.

## Safe Run Order

```powershell
python -m py_compile app/*.py
python -m unittest discover -s tests
python -m app.line_draft_builder --date 2026-06-06 --source-json data\fixtures\line_sources_sample.json --no-write --no-ai
```

Then review `LINE_Drafts`, set `Status=approved` and `Send_Mode=live`, preview approved rows, and only then live-send.

## Pass / Merge Rule

Keep the work on `codex/line-contact-ollama-drafts` until the compile check, unit tests, and dry-run draft build pass. Merge to `master` only after those checks pass.
