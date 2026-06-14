param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "start", "check")]
    [string]$Action = "status",

    [Parameter(Position = 1)]
    [string]$TaskName = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = "python"
}

switch ($Action) {
    "status" {
        git status --short --branch
        git log -5 --oneline --decorate
    }
    "start" {
        if (-not $TaskName.Trim()) {
            throw "Usage: tools\solo_git.ps1 start <task-name>"
        }
        $Slug = $TaskName.Trim().ToLowerInvariant()
        $Slug = $Slug -replace "[^a-z0-9._-]+", "-"
        $Slug = $Slug.Trim("-")
        if (-not $Slug) {
            throw "Task name must contain an ASCII letter or number."
        }
        if ((git status --porcelain)) {
            throw "Working tree is not clean. Commit or resolve current work first."
        }
        git switch master
        git pull --ff-only
        git switch -c "codex/$Slug"
    }
    "check" {
        git status --short --branch
        git diff --check
        & $PythonExe -m unittest discover -s tests
    }
}
