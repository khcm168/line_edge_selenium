# Branch Consolidation Audit - 2026-07-23

This repository was consolidated onto local `master` on 2026-07-23. Treat
`master` as the only normal operating branch for LINE delivery work unless a
new Codex task deliberately creates a fresh `codex/<task-name>` branch.

## Final Operating Commit

- `master` fast-forwarded through `132f7b7`
  (`Merge branch 'codex/line-presence-engine' into codex/consolidate-line-repo`)
  and finalized by the commit that adds this audit note and
  `tests/test_encoding_guards.py`.
- Full verification after finalization:
  `python -m unittest discover -s tests`.
- Result: 196 tests passed.

## Kept In Master

- `origin/master` ARM observer proof and `scripts/check_arm_webapp_compatibility.py`.
- `codex/line-chat-search-row` chat search, draft hardening, audit/lease
  governance, BMP sanitizing, material watcher, and task/login health hardening.
- `codex/line-presence-engine` presence drafts, nightly project health ledger,
  stale owner reclaim, WebApp observer notes, sheet header preservation, and
  the organized `OPEN_LINE_RUNBOOK.bat` operator menu.
- `codex/fix-line-message-encoding` was not cherry-picked literally because
  current reminder wording is newer; its intent is preserved by
  `tests/test_encoding_guards.py` and by sourcing `SHIPPING_NOTICE_TEMPLATE`
  from `DEFAULT_RULES`.

## Superseded Or Already Absorbed

- `codex/line-with-pictures`: `git cherry master codex/line-with-pictures`
  reports both commits as patch-equivalent to `master`. Do not re-merge it.
- `codex/line-chat-search-row-dirty-backup-20260626` and
  `codex/line-drafts-query-schedule`: already represented by the
  `Support nested LINE material paths` history in `master`.
- `codex/low-impact-material-watcher`,
  `codex/fde-material-intelligence-v1`, `codex/ollama-material-cpu-fix`,
  `codex/ollama-material-ingestion`,
  `codex/ollama-personalized-task-messages`,
  `codex/line-contact-ollama-drafts`, and
  `codex/line-bot-scenario-reinvention`: ancestors of `master` after the
  fast-forward.

## Do Not Reapply

- Worktree `C:\Users\khcm1\.codex\worktrees\322a\line_edge_selenium` has an
  uncommitted `app/sheet_gateway.py` based on old
  `codex/idempotent-line-drafts`. It is an obsolete subset: applying it over
  `master` would drop material catalog and presence profile support.
- Root `tmp_*` files and `data\project_health\` / `data\tmp\` are generated
  evidence or scratch fetches. They are intentionally ignored, not deleted.

## Future Bot Rules

- Start with `git status --short --branch` and read this audit, `AGENTS.md`,
  `LINE_RUNBOOK.md`, and `docs/arm-webapp-orchestration.md`.
- For ARM/WebApp changes, `line_edge_selenium` remains an observer. Require
  canonical `psr-gas` release proof and all-project audit readback before
  accepting any shared WebApp release change.
- Never send LINE live traffic outside the persistent handoff worker and never
  retry uncertain delivery in the same run.
- Keep generated health ledgers and scratch web/API captures out of source.
- Before changing `master`, run `python -m unittest discover -s tests` and
  record any intentional exception in the commit message.
