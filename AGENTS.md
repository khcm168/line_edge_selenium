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
