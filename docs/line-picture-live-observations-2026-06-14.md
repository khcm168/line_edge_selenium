# LINE Picture Live Observations - 2026-06-14

## Controlled Result

A supervised exact-friend test successfully sent:

1. A normal Chinese sleep-care text.
2. `MAT-ACT-021` (`投影片21.JPG`).
3. A neutral contextual caption after the image.

The image path was resolved from `LINE_MATERIAL_ROOT`, its SHA-256 matched the
catalog, and LINE displayed the image and caption in the expected order.

## File Picker Behavior

LINE Edge extension 3.7.2 called `window.showOpenFilePicker()`. The one-shot
provider was consumed once and LINE auto-sent the returned file. Verification
required a new image-message count and disappearance of upload progress.

No second click, Enter, native-window typing, or retry was needed.

## Session Behavior

`--keep-open` leaves Edge visible after the Python command exits, but the
WebDriver session is gone. A detached visible Edge window is therefore not a
reusable automation session.

Attempts to attach afterward failed before any LINE action because:

- the default handoff port did not belong to that session;
- `DevToolsActivePort` could remain present even when its browser endpoint was
  no longer reachable;
- the old EdgeDriver service had no active WebDriver sessions.

The reliable low-login design is a persistent `app.handoff_worker` process that
keeps both Edge and its original WebDriver owner alive.

## Operating Rule

- Start one persistent worker for a supervised work period.
- Submit preview, observation, and approved-send requests to that worker.
- Use passive observation requests to capture evidence without typing or
  sending.
- Stop the worker deliberately when the supervised period is over.
- Do not treat a merely visible detached Edge window as attachable.
