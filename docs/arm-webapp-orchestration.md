# ARM WebApp Orchestration Observer

`line_edge_selenium` does not call the ARM WebApp and owns no ARM WebApp URL.
It is registered because it reads the same production spreadsheet and must be
notified when that shared integration evolves.

Its read-only probe is:

```powershell
.\.venv\Scripts\python.exe scripts\check_arm_webapp_compatibility.py
```

The canonical orchestrator temporarily supplies the candidate URL, expected
spreadsheet ID, contract, contract version, and release through process
environment variables. The probe confirms:

- `LINE_SOURCE_SPREADSHEET_ID` still equals the registered ARM spreadsheet;
- the candidate endpoint reports the expected contract and release;
- no LINE draft, LINE message, worksheet, or local configuration is changed.

The canonical `psr-gas` registry is mandatory. Release changes are incomplete
until `C:\Dev\psr-gas\tools\arm_webapp_release.py --confirm-deploy` updates
Apps Script cloud, proves all four registered projects, and records audit
evidence. This observer must not accept a changed ARM WebApp release from any
other repository.

Do not add `ARM_WEBAPP_URL` to this project unless it becomes a real API
consumer. If that happens, update the canonical registry with explicit
capabilities and a new read-only probe before applying any URL.

ARM alone owns the full queue preview. EasyFlow is a second observer with its
own read-only sheet/header probe. Never copy another project's `.env` or
credential JSON into this repository, add live LINE/EasyFlow actions to a
probe, or claim success from an unverified audit response.

## Nightly health handoff

Codex automation `line` (`每日專案健康 LINE 報告`) runs at 22:45 Asia/Taipei,
after the 22:30 World Cup Hello. It executes the four-project dry-run from
the canonical `C:\Dev\psr-gas` checkout, builds one combined Traditional Chinese summary, and
submits one exact-friend request to this project's existing
`app.handoff_worker`.

If the earlier job is still running, this request waits in the same inbox. It
must never launch a second Edge or bypass the queue. Health failures are sent
as one red summary; uncertain LINE state is not retried. After success the
worker remains live and returns to idle for later tasks.

Current implementation notes:

- the daily run also writes a ledger at `data\project_health\YYYY-MM-DD.json`;
- Gmail self-delivery is the primary guarantee that the operator receives the
  report;
- LINE now targets `洪啓明` with `unique_contains_friend`;
- if the worker is not live, only `start_worker_hidden.ps1` may be used once;
- a LINE retry is allowed only when the first failure is proven to be pre-send.
