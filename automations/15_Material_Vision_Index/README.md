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

The watcher polls every 30 seconds. It is hash-idempotent and writes each
successful catalog row immediately, so a restart resumes with the next image.
