# Repository Working Agreement

## Git

- The default branch is `master`.
- Use one `codex/<task-name>` branch per Codex thread.
- Rename and pin the thread at the start of substantial work.
- Inspect `git status` before edits and never discard unrelated changes.
- Review `git diff` and run tests before committing.
- Prefer `git pull --ff-only` on `master`.
- Squash merge reviewed pull requests, then update `master` and delete the
  merged feature branch.

## LINE Safety

- Preview is the default.
- Never send live LINE messages without explicit user approval in the current
  turn.
- Picture sends require an approved catalog material, verified SHA-256, and an
  approved `LINE_Drafts` row.
- Never retry an uncertain text or picture submission.
- Keep group allowlisting and ambiguity checks intact.

## Entry Points

- Daily operator menu: `OPEN_LINE_RUNBOOK.bat`
- Written operator guide: `LINE_RUNBOOK.md`
- Solo Git guide: `docs/solo-git-workflow.md`
- Full test suite: `python -m unittest discover -s tests`

## Shared ARM integration

Read `docs/arm-webapp-orchestration.md` before changing the source spreadsheet
or shared ARM compatibility probe. This project is an observer, not a WebApp
client: orchestration must never send LINE messages or edit LINE sheets.
ARM alone owns the full queue preview. Never copy another project's `.env` or
credentials here, and require the logged all-project proof plus row readback
before claiming compatibility.
Nightly project health is automation `line`: one combined message through the
existing handoff inbox. Never create per-project browsers, parallel senders, or
stop Edge after the report.

<!-- PRO-AI GOVERNANCE START -->
## Shared Multi-Project Agent Governance

This repository participates in a four-project autonomous health system on a
single Lenovo Z13 operated by one programmer with Codex capability, internet,
and VPN access.

### Required Role Separation

- `monitor` agents run read-only probes only.
- `diagnose` agents classify failures and choose escalation scope.
- `repair` agents may run only allowlisted, idempotent repairs.
- `summary` agents generate concise Traditional Chinese reports.
- `delivery` agents send prepared artifacts only and must not reinterpret
  health.

### Shared Resource Rules

- Shared mutable resources require an explicit lease.
- `ARM` is the only queue-preview owner.
- `line_edge_selenium` is the only LINE delivery executor.
- Observer projects must remain read-only during orchestration.
- No agent may copy secrets, token files, or service-account JSON between
  repositories.

### Autonomy Rules

- Degrade on uncertainty. Do not silently skip reporting.
- Shared config mismatch must be reported as `CONFIG FAIL`, not masked.
- Delivery failure must not erase health evidence.
- Any deployment, registry, or `.env` mutation requires human escalation unless
  an explicit local policy says otherwise.

### Shared Summary Contract

Nightly summary must include:

1. `???亙?獢摨瑕??YYYY-MM-DD?
2. overall `?` or `?`
3. one line for each of the four projects
4. shared release / audit / worker status when known
5. one short next-action line

## Project Agent Policy: line_edge_selenium

### Role

`line_edge_selenium` is the single LINE delivery executor and a shared
spreadsheet observer. It must preserve one persistent browser session.

### Allowed Automatic Repairs

- run the approved hidden worker start script once
- re-check `app.handoff_worker --status`
- clear expired local worker lease when no live process owns it
- re-run shared spreadsheet compatibility probe

### Forbidden Automatic Repairs

- open a second Edge session for LINE
- stop the persistent worker during nightly health
- use one-off `app.line_batch` instead of persistent worker
- resend when delivery state is uncertain
- log out LINE to recover automation

### Required State Outcomes

- `ready_to_deliver` only when worker is live and safe
- `blocked` after one failed restart attempt
- never retry same-run delivery after `error` or uncertainty
<!-- PRO-AI GOVERNANCE END -->

