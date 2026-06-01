# 30 Reminder Builder

Builds preview LINE task files for all safe reminder types from `DY2` and `Acts`.

Safe first command:

```powershell
run_preview.cmd --date 2026-06-01 --types all --max-rows 20
```

This only writes local task and audit files. Submit generated tasks to the handoff worker with manual approval before any live testing:

```powershell
..\10_LINE_Message_Test\handoff_submit_manual.cmd --tasks data\tasks\reminders_2026-06-01_all.json
```
