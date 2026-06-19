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

Production release `37` and all four registered projects were proven on
2026-06-19 by run `arm-webapp-1781860828-637d4a12`; the evidence is spreadsheet
`log` row 6133. Independent readback confirmed `psr-aios-v1`, `ARM`,
`line_edge_selenium`, and `easyflow` passed.

Do not add `ARM_WEBAPP_URL` to this project unless it becomes a real API
consumer. If that happens, update the canonical registry with explicit
capabilities and a new read-only probe before applying any URL.

ARM alone owns the full queue preview. EasyFlow is a second observer with its
own read-only sheet/header probe. Never copy another project's `.env` or
credential JSON into this repository, add live LINE/EasyFlow actions to a
probe, or claim success from an unverified audit response.
