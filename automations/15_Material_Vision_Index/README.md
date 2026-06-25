# Material Vision Index

This automation scans image files below `Material`, identifies hashes that are
not already present in the reviewed catalog or pending overlay, and asks local
Ollama `gemma3:12b` for draft metadata. Generated rows are stored in the
ignored runtime overlay `data/material_ingest/pending_catalog.json`; the picker
loads reviewed and pending records together.

Every imported row is forced to:

- `Sendability=internal_only`
- `Review_Status=pending_review`
- `human_review_required`
- `ai_vision_generated`

The model cannot approve or send a picture.

Commands:

```powershell
automations\15_Material_Vision_Index\scan_once.cmd
powershell -ExecutionPolicy Bypass -File automations\15_Material_Vision_Index\start_watcher_hidden.ps1
automations\15_Material_Vision_Index\status.cmd
automations\15_Material_Vision_Index\stop.cmd
```

The low-impact watcher analyzes one image, rests for five minutes, then scans
again. It runs below normal process priority, is hash-idempotent, and writes
each successful catalog row immediately, so a restart resumes with the next
image.

For a one-glance colored health report, double-click
`MATERIAL_WATCHER_STATUS.bat` in the project root or run `status.cmd`. The
report verifies both the saved PID and the live process, shows Ollama status,
the latest completed image or error, and reviewed/pending catalog counts.
Every completed scan also updates
`data\material_ingest\latest_notice.json`.
An image that still returns invalid metadata after the bounded retry is written
to `data\material_ingest\failed_images.json` and skipped so it cannot block
the rest of the folder. Requeue quarantined images deliberately with:

```powershell
python -m app.material_ingest --retry-failed
```
Vision defaults to CPU-only inference (`OLLAMA_VISION_NUM_GPU=0`) to avoid
competing with Edge for limited Vulkan memory. Machines with sufficient VRAM
can opt into GPU layers explicitly.

Resource controls:

```text
OLLAMA_VISION_NUM_THREAD=4
MATERIAL_WATCH_BATCH_SIZE=1
MATERIAL_WATCH_POLL_SECONDS=300
```
