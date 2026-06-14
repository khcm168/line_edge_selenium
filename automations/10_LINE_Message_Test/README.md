# 10 LINE Message Test

Preview or optionally send to the controlled test targets:

- 洪啓明
- P103003
- 001N1備份區
- Ya.ping

Safe first command:

```powershell
preview.cmd
```

Live sending is blocked unless `--send` is passed and the task has `Customer_ID` plus `Line暱稱` from the `List` sheet. Group sends still require `LINE_ALLOWED_GROUP_TARGETS`.

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
