# 10 LINE Message Test

Preview or optionally send to the controlled test targets:

- `洪啓明`
- `001N1備份區`
- `100分的自己`
- `Ya.ping`

Safe first command:

```powershell
preview.cmd
```

Live sending is blocked unless `--send` is passed and the task has
`Customer_ID` plus `Line Contact` from the `List` sheet. Group sends still
require `LINE_ALLOWED_GROUP_TARGETS`.

Manual approval mode opens the matched chat and stops before typing:

```powershell
preview.cmd --manual-approve
```

For low-profile supervised work, keep one persistent worker alive:

```powershell
powershell -ExecutionPolicy Bypass -File start_worker_hidden.ps1
worker_status.cmd
observe.cmd
```

`observe.cmd` captures the current LINE screen and visible state without
searching, typing, uploading, or sending. Submit approved work to the same
worker instead of launching another browser. Stop it deliberately with
`stop_worker.cmd`.

Series-test task builders:

```powershell
build_series_text_tasks.cmd
build_series_picture_tasks.cmd
```

Series-test worker workflow:

```powershell
powershell -ExecutionPolicy Bypass -File start_worker_hidden.ps1
series_preview_text.cmd
series_preview_picture.cmd
series_send_text.cmd
series_send_picture.cmd
```

These commands write a timestamped task file under
`data/tasks/series_tests/runs/`, submit it to the running worker, wait for the
`data/handoff/done/` or `data/handoff/error/` result file, and print the
matching audit path.

The generated task files live under `data/tasks/series_tests/`. Use them with
the worker preview/send flow so screenshots, JSON snapshots, and JSONL audit
records are preserved for each verification run. See
`docs/line-series-test-plan.md`.
