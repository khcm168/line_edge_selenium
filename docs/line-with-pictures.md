# LINE With Pictures

## Review Queue

`LINE_Drafts` remains the only outbox. Picture rows append `Material_ID`,
`Image_Path`, `Message_Kind`, and `Material_SHA256` to the legacy columns.
Only rows with `Status=approved`, `Send_Mode=live`, safe flags, and a material
that is approved and sendable in the catalog can reach the live sender.

Browse the catalog by product, topic, audience, ID, or generated hashtag:

```powershell
.\.venv\Scripts\python.exe -m app.material_picker --search "sleep"
.\.venv\Scripts\python.exe -m app.material_picker --product "iMuso"
.\.venv\Scripts\python.exe -m app.material_picker --live-only
```

The hashtags are views of structured catalog fields; filenames remain stable
and SHA-256 verification binds the selected `Material_ID` to the exact JPG.

Configure the external library:

```powershell
$env:LINE_MATERIAL_ROOT="C:\Dev\line_edge_selenium\Material\行動力"
.\.venv\Scripts\python.exe -m app.material_catalog_builder
```

Create a material-aware draft in the same queue:

```powershell
.\.venv\Scripts\python.exe -m app.line_picture_drafts `
  --line-query "001N1備份區" `
  --material-id "MAT-ACT-003" `
  --campaign "internal_acceptance"
```

The drafting pipeline uses local Ollama `gemma4:latest` by default. If Ollama
is unavailable or returns invalid content, the approved catalog caption is
kept deterministically. Every draft remains human-review required.

## Vision Import For New Folders

`app.material_ingest` recursively detects image hashes that are not already in
the catalog. Visual analysis uses `OLLAMA_VISION_MODEL` (`gemma3:12b` by
default), which is separate from the text rewriting model.
It defaults to CPU-only inference through `OLLAMA_VISION_NUM_GPU=0` so the
background watcher does not exhaust GPU memory used by Edge.

```powershell
.\.venv\Scripts\python.exe -m app.material_ingest --list-new
.\.venv\Scripts\python.exe -m app.material_ingest --max-files 1
.\.venv\Scripts\python.exe -m app.material_ingest --watch
```

Folder-relative filenames such as `睡眠(SleepHA)/投影片1.JPG` remain unchanged.
SHA-256 makes ingestion idempotent even when different folders reuse the same
leaf filename. Vision output adds explicit tags to `material_hashtags`, but
all imported records remain `internal_only` and `pending_review`.
Generated records are written to the ignored overlay
`data/material_ingest/pending_catalog.json`; `load_catalog` merges that overlay
with the reviewed catalog for search and validation.

## Image Upload

LINE extension 3.7.2 implements the chat attachment button with
`window.showOpenFilePicker()`. It does not keep an HTML
`input[type="file"]` in `#modal-root` or the `ltsmSandbox.html` iframe.

The sender therefore installs a one-shot picker provider for the approved
image, clicks the accessible `Send file` button, and immediately restores the
browser API. LINE auto-sends the returned `File`; no second Enter or Open
action is required. Success requires all of the following:

- the one-shot picker was consumed exactly once;
- the chat image-message count increased;
- LINE's upload progress control disappeared.

The Windows dialog fallback is fail-closed. It never types or clicks through
the general foreground window, and an uncertain submission is never retried.

Group delivery uses two independent gates: the task must set `allow_group`,
and the normalized group name must appear in `LINE_ALLOWED_GROUP_TARGETS`.
The built-in internal test allowlist contains `001N1備份區` and
`100分的自己`. Duplicate matching rows remain ambiguous and are never opened.

## Response Evidence

Successful approved sends schedule local follow-up records at 24, 48, 72
hours, and 7 days under `data/responses/followups.jsonl`.

Record a response screenshot:

```powershell
.\.venv\Scripts\python.exe -m app.line_response_intake `
  --draft-id "<Draft_ID>" `
  --message-id "<message-id>" `
  --screenshot "C:\evidence\response.png" `
  --response-class material_request `
  --result "customer requested information" `
  --next-action "prepare reviewed material" `
  --reviewer "operator"
```

The optional group watcher is disabled by default and creates drafts only:

```powershell
$env:LINE_RESPONSE_WATCHER_ENABLED="true"
$env:LINE_RESPONSE_WATCH_GROUPS="001N1備份區"
.\.venv\Scripts\python.exe -m app.line_group_watcher --attach-existing
```

## Portable Kit

Build a new credential-free directory on a USB drive:

```powershell
.\.venv\Scripts\python.exe tools\export_usb_kit.py `
  --destination "E:\LINE-With-Pictures" `
  --material-root "C:\Dev\line_edge_selenium\Material\行動力"
```

The exporter refuses an existing destination and excludes `.env`,
credentials, Edge profile/browser state, logs, snapshots, response evidence,
and customer exports. On the second PC, run `setup_second_pc.ps1`, then the
included `doctor_second_pc.py`.
