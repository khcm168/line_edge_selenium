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

Live sending is blocked unless `--send` is passed and the target is in `LINE_ALLOWED_LIVE_TARGETS`.

Manual approval mode opens the matched chat and stops before typing:

```powershell
preview.cmd --manual-approve
```
