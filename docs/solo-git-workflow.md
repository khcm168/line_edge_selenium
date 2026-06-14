# Solo Git Workflow

This repository currently uses `master`, not `main`. Do not mix both names.
The Codex desktop convention also uses `codex/` for feature branches.

## Start Work

```powershell
git switch master
git pull --ff-only
git switch -c codex/<task-name>
```

Ask Codex to rename and pin the thread immediately. Use one thread and one
branch per task.

## Keep Codex History Findable

- Give the thread a specific result-oriented title before substantial work.
- Pin active feature threads in the sidebar.
- Keep one feature branch associated with one thread.
- Put important decisions, commands, and outcomes in committed runbooks.
- Commit before leaving a long session; sidebar history is not a source-code
  backup.
- Do not archive or delete the thread until its pull request is merged.
- Search by the exact thread title or branch name when returning later.

Git commits are the durable history. A Codex thread may be renamed, filtered,
archived, or absent from a sidebar search even when its branch still exists.

## Review Work

```powershell
git status --short --branch
git diff
python -m unittest discover -s tests
```

## Publish

```powershell
git add <intentional-files>
git commit -m "<clear result>"
git push -u origin HEAD
```

Create a GitHub pull request, review the diff and test result, then squash and
merge.

## Finish

```powershell
git switch master
git pull --ff-only
git branch -d codex/<task-name>
git push origin --delete codex/<task-name>
```

Deploy only from the updated `master`.

## Helper

```powershell
tools\solo_git.ps1 status
tools\solo_git.ps1 start <task-name>
tools\solo_git.ps1 check
```

The helper intentionally does not commit, push, merge, deploy, or delete. Those
actions deserve a visible review step.
