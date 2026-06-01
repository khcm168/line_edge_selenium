# Stability And Precautions

LINE automation is riskier than ordinary sheet processing because the UI is live and message sending is irreversible.

Core precautions:

- Preview is the default. Live send requires `--send`.
- Do not send on ambiguous LINE search results.
- Do not send to groups unless the task explicitly allows a known test group.
- Retry search and chat-open steps only. Do not blindly retry after pressing Enter.
- Save snapshots for every match, skip, error, and send.
- Keep credentials in environment variables or `.env`, never in source files.
- Run Selenium through one handoff worker whenever several scripts need LINE access.
- Track quota before live sends and stop when quota or UI health checks fail.

Stability suggestions:

- Keep one browser session per batch to avoid repeated login and phone verification.
- Prefer selectors over coordinates. Use CDP or coordinate fallbacks only inside isolated helper functions.
- Log every fallback method so future failures can be diagnosed from `data/logs/` and `data/snapshots/`.
- Keep scheduled jobs preview-only until a small live test has been reviewed.
- Treat UI checks as breakage detection only: verify login state, search box, and composer; screenshot failures and alert the operator through audit records.
