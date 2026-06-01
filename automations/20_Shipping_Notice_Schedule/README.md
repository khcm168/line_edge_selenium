# 20 Shipping Notice Schedule

Builds preview LINE task files from `地區會議資料V8.0 beta` tab `DY2`.

Source mapping:

- `A`: 品名
- `I`: 銷售日期
- `AD`: 代號

Safe first command:

```powershell
run_preview.cmd --date 2026-05-31 --max-rows 10
```

This command only writes local task and audit files. It does not open LINE and does not send.

After reviewing the task file, open the matched chat without sending:

```powershell
..\10_LINE_Message_Test\preview.cmd --manual-approve --tasks data\tasks\shipping_notice_2026-06-01.json
```

For Windows Task Scheduler, point the action at:

```text
automations\20_Shipping_Notice_Schedule\run_preview.cmd
```

Or install a daily preview-only task:

```powershell
install_preview_task.cmd 09:00
```
