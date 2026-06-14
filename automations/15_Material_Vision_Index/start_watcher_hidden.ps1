$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Project Python was not found: $PythonExe"
}

$StateDir = Join-Path $ProjectRoot "data\material_ingest"
$StatePath = Join-Path $StateDir "worker_state.json"
$StdoutPath = Join-Path $StateDir "worker.stdout.log"
$StderrPath = Join-Path $StateDir "worker.stderr.log"
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

if (Test-Path -LiteralPath $StatePath) {
    try {
        $State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
        if ($State.pid -and (Get-Process -Id $State.pid -ErrorAction SilentlyContinue)) {
            Write-Host "Material watcher is already running with PID $($State.pid)."
            exit 0
        }
    }
    catch {
    }
}

$Arguments = @(
    "-m",
    "app.material_ingest",
    "--watch"
)
$Process = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList $Arguments `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $StdoutPath `
    -RedirectStandardError $StderrPath `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Material watcher started with PID $($Process.Id)."
Write-Host "Status: automations\15_Material_Vision_Index\status.cmd"
