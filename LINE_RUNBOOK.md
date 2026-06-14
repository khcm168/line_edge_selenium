# LINE Daily Runbook

Start with `OPEN_LINE_RUNBOOK.bat`. The menu keeps preview, review, and live
actions visibly separate.

## Daily Choice

1. Browse picture materials by product, topic, audience, or hashtag.
2. Choose an approved `Material_ID` and create one picture review draft.
3. Review text, image, target, risk flags, and `Material_ID` in Google Sheets.
4. Set `Status=approved` and `Send_Mode=live` only for rows you intend to send.
5. Preview approved rows.
6. Use the live-send command only after that review.

## Persistent Session

Leaving Edge visible is not sufficient: the WebDriver owner must remain alive
too. Start one hidden worker at the beginning of a supervised session:

```powershell
powershell -ExecutionPolicy Bypass -File automations\10_LINE_Message_Test\start_worker_hidden.ps1
automations\10_LINE_Message_Test\worker_status.cmd
```

Capture passive observations without sending:

```powershell
automations\10_LINE_Message_Test\observe.cmd
```

The worker keeps one authenticated browser session and processes queued work
sequentially. End it deliberately with `stop_worker.cmd`; routine jobs should
not repeatedly launch and log in.

## Material Tags

The JPG filenames under `C:\Dev\line_edge_selenium\Material\行動力` are not
renamed. They are identified by SHA-256 and described in
`data/line_material_catalog.json`.

Each catalog row has:

- `Material_ID` and filename
- product, topic, and audience
- campaign and trigger types
- sendability, review status, risk, and safety flags
- reviewed customer caption
- SHA-256, which prevents sending a changed or substituted file

The picker renders those structured fields as searchable hashtags:

```powershell
python -m app.material_picker --search "睡眠"
python -m app.material_picker --product "iMuso"
python -m app.material_picker --material-id MAT-ACT-006
python -m app.material_picker --live-only
```

Finding a material does not authorize sending it. Live sending still requires
an approved catalog record and an approved `LINE_Drafts` row.

`MAT-ACT-006` and the supervised sleep reference `MAT-ACT-021` have completed
material approval. Search results marked `REVIEW/BLOCKED` are visible for
planning but cannot pass the sender.

## New Material Vision Index

The material watcher recursively scans `C:\Dev\line_edge_selenium\Material`.
It uses local Ollama `gemma3:12b` to propose:

- objective visual description and readable text
- topic, audience, and searchable hashtags
- medical-claim, privacy, prescription, comparison, and dense-reference risks
- a neutral Traditional Chinese caption

List files that are not represented by an existing SHA-256:

```powershell
python -m app.material_ingest --list-new
```

Analyze only one picture:

```powershell
python -m app.material_ingest --max-files 1
```

Run continuous detection in the background:

```powershell
powershell -ExecutionPolicy Bypass -File automations\15_Material_Vision_Index\start_watcher_hidden.ps1
automations\15_Material_Vision_Index\status.cmd
automations\15_Material_Vision_Index\stop.cmd
```

Each completed hash is appended immediately, so restarting resumes instead of
duplicating work. AI-generated rows are always `internal_only` and
`pending_review`; they cannot be selected by `--live-only` or sent until a
human explicitly reviews and approves them. Generated rows live in the ignored
runtime overlay `data/material_ingest/pending_catalog.json`, keeping Git clean
until a reviewed record is deliberately promoted into the main catalog.

The background watcher is intentionally low impact: four CPU threads, one
image per cycle, a five-minute rest, and below-normal process priority.

## Safe Commands

```powershell
python -m unittest discover -s tests
python -m app.line_draft_builder --types all --max-per-type 10
python -m app.approved_draft_sender --max-rows 10
```

Live sending is deliberately separate:

```powershell
python -m app.approved_draft_sender --send-approved --max-rows 10
```

## Git

Use `tools\solo_git.ps1 status`, `start <task-name>`, and `check`.
See `docs/solo-git-workflow.md`.
