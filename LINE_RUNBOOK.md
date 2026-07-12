# LINE Daily Runbook

Start with `OPEN_LINE_RUNBOOK.bat`. The launcher opens `tools\line_runbook.ps1`,
an operator console that keeps worker ownership, draft generation, material
work, checks, and live-send actions visibly separate.

## Launcher Menu

Use these sections in order during a normal day:

1. Worker / Edge ownership
   - `1` shows worker heartbeat plus `data\handoff\worker_owner.json`.
   - `2` lists LINE automation `msedge.exe` / `msedgedriver.exe` processes and
     their command lines, so the visible/logging Edge window can be traced to a
     launch path.
   - `3` reclaims only a stale handoff owner.
   - `4` starts the persistent hidden worker.
   - `5` captures a passive observation without sending.
   - `6` requests worker stop.
2. Draft generation
   - `10` previews Presence Engine drafts without Sheet writes and without AI.
   - `11` writes Presence Engine review rows into `LINE_Drafts`.
   - `12` builds scenario drafts.
   - `13` previews approved rows; it does not send.
3. Picture materials
   - `20` to `27` cover material search, picture draft creation, and the
     material vision watcher.
4. Checks / docs
   - `30` runs tests.
   - `31` shows git status and diff stats.
   - `32` opens this written runbook.
5. Live send
   - `90` is the only live-send menu item and still requires typing
     `SEND APPROVED`.

## Daily Choice

1. Browse picture materials by product, topic, audience, or hashtag.
2. Choose an approved picture by its readable `Material_Label`; the picker also
   shows the technical `Material_ID` needed by the command.
3. Review text, image, target, risk flags, and `Material_Label` in Google Sheets.
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

### Edge Ownership And Reclaim

The handoff worker records ownership at:

```text
data\handoff\worker_owner.json
```

It includes:

- worker PID;
- parent PID;
- command line;
- command-line argv;
- current working directory;
- Edge profile directory;
- launcher source, such as
  `automations\10_LINE_Message_Test\start_worker_hidden.ps1`.

Use launcher option `1` to read the owner file and worker heartbeat. Use option
`2` to inspect the actual `msedge.exe` and `msedgedriver.exe` command lines that
match this project profile or the LINE extension. This is the fastest way to
identify which launch path created a visible or logging Edge instance.

Reclaim is intentionally conservative:

```powershell
python -m app.handoff_worker --reclaim-stale-owner
```

It only clears metadata created by `app.handoff_worker`, refuses to run when the
owner PID is still alive, refuses to run when the worker heartbeat is live, and
uses the Edge profile guard before removing stale profile markers. It must never
be used as a way to clean up a live user Edge session.

If the profile is still locked after reclaim refuses to run, inspect the Edge
launch inventory instead of deleting files by hand.

## Presence Engine

Presence drafts are relationship-maintenance touch points, not sales messages.
They reuse the existing `LINE_Drafts` review queue and are written as
`Status=pending_review` and `Send_Mode=review`.

Profile source tab:

```text
LINE_Presence_Profiles
```

Expected columns:

```text
Enabled, Customer_ID, Clinic_Name, Line_Query, Line_Contact,
Line_Message_Style, Interest_Tags, Cadence_Days, Preferred_Send_Time,
Last_Category, Last_Generated_Date, Remark
```

Safe preview:

```powershell
python -m app.line_presence_engine --max-clinics 10 --no-write --no-ai
```

Write review rows:

```powershell
python -m app.line_presence_engine --max-clinics 10
```

The `洪啓明` generation notice is also draft-only. It is not sent unless a human
later approves the row and changes `Send_Mode` to `live`.

## Material Tags

The JPG filenames under `C:\Dev\line_edge_selenium\Material\行動力` are not
renamed. They are identified by SHA-256 and described in
`data/line_material_catalog.json`.

Each catalog row has:

- `Material_Label`, such as `健管師/投影片2.JPG | 健康照護`
- `Material_ID`, an internal stable key derived from the image hash
- `SHA256`, the full image fingerprint used to detect replacement or changes
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

For the quickest visual check, double-click `MATERIAL_WATCHER_STATUS.bat`.
Green means the watcher process and Ollama are both alive. The report also
shows the latest completed image or error and the current reviewed/pending
catalog counts. The completion notice is stored at
`data\material_ingest\latest_notice.json`.

If Ollama returns invalid metadata twice, the picture is listed in
`data\material_ingest\failed_images.json` and skipped so later pictures can
continue. After correcting the file or model settings, requeue those pictures
with `python -m app.material_ingest --retry-failed`.

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
python -m app.line_presence_engine --max-clinics 10 --no-write --no-ai
python -m app.approved_draft_sender --max-rows 10
```

Live sending is deliberately separate:

```powershell
python -m app.approved_draft_sender --send-approved --max-rows 10
```

## Git

Use `tools\solo_git.ps1 status`, `start <task-name>`, and `check`.
See `docs/solo-git-workflow.md`.
