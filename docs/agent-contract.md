# Project Agent Contract: line_edge_selenium Self-Management

## Project Role

`line_edge_selenium` is the single LINE delivery executor on this Z13. It is
also an observer for shared spreadsheet compatibility. It must preserve one
persistent browser session and must not open a second competing LINE browser.

## Local State Machine

```text
idle
  -> probe_spreadsheet_compatibility
  -> probe_worker_status
  -> diagnose
  -> repairable_worker?
  -> repair_worker_once
  -> reprobe_worker_status
  -> ready_to_deliver | degraded | blocked
```

### Project Healthy Conditions

- Shared spreadsheet compatibility probe passes.
- `handoff_worker_live=true`.
- Worker status is `idle` or another explicitly safe ready state.
- Existing browser session is the only active LINE sender session.

## Lock Usage

- May request `browser:line-primary`.
- May request `delivery:line:hqming`.
- May request `local_runtime:line_edge_selenium`.
- Must not request `queue_preview:arm`.

## Repair Whitelist

### Allowed

- Run the approved hidden worker start script once.
- Re-check `app.handoff_worker --status` after the one safe start.
- Clear a stale local worker lease if TTL expired and no live process owns it.
- Re-run shared spreadsheet compatibility probe.

### Blocked

- Opening a second Edge session for LINE.
- Stopping the persistent worker as part of nightly health.
- Sending a second copy when delivery status is uncertain.
- Using one-off `app.line_batch` instead of the persistent worker.
- Logging out LINE to recover automation.

## Delivery Rules

- Daily quota key must be unique per Taipei date.
- If inbox, done, error, task, or audit state is uncertain, do not resend.
- If worker remains non-live after one approved start attempt, stop.
- If delivery returns `error`, do not retry in the same run.

## Summary Line Format

```text
line_edge_selenium: 🟢 worker live, ready for delivery
line_edge_selenium: 🔴 worker not live, send blocked
line_edge_selenium: 🔴 LINE session uncertain, manual check required
```

## Solo Z13 Operating Note

On a single Z13, browser state is a bottleneck. This agent must be treated as a
delivery specialist, not a general repair bot. Protect session continuity over
aggressive automation.
