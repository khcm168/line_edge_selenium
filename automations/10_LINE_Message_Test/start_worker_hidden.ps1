$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectRoot

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$RuntimeRoot = $ProjectRoot
$SharedRuntimeRoot = "C:\Dev\line_edge_selenium"
if (
    -not (Test-Path -LiteralPath $PythonExe) -and
    (Test-Path -LiteralPath (Join-Path $SharedRuntimeRoot ".venv\Scripts\python.exe"))
) {
    $RuntimeRoot = $SharedRuntimeRoot
    $PythonExe = Join-Path $RuntimeRoot ".venv\Scripts\python.exe"
}
elseif (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = "python"
}

$EnvPath = Join-Path $RuntimeRoot ".env"
if (Test-Path -LiteralPath $EnvPath) {
    Get-Content -LiteralPath $EnvPath | ForEach-Object {
        $Line = $_.Trim()
        if ($Line -and -not $Line.StartsWith("#") -and $Line.Contains("=")) {
            $Parts = $Line.Split("=", 2)
            [Environment]::SetEnvironmentVariable(
                $Parts[0].Trim(),
                $Parts[1].Trim().Trim('"').Trim("'"),
                "Process"
            )
        }
    }
}
if (-not $env:LINE_EDGE_PROFILE_DIR) {
    $env:LINE_EDGE_PROFILE_DIR = Join-Path $RuntimeRoot "edge-profile"
}
if (-not $env:LINE_MATERIAL_ROOT) {
    $MaterialBase = Join-Path $RuntimeRoot "Material"
    $MaterialFolder = Get-ChildItem -LiteralPath $MaterialBase -Directory |
        Select-Object -First 1
    $env:LINE_MATERIAL_ROOT = if ($MaterialFolder) {
        $MaterialFolder.FullName
    }
    else {
        $MaterialBase
    }
}

& $PythonExe -m app.handoff_worker --status *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Output "handoff_worker_already_running=true"
    exit 0
}

$LogDir = Join-Path $ProjectRoot "data\handoff"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stdout = Join-Path $LogDir "worker.stdout.log"
$Stderr = Join-Path $LogDir "worker.stderr.log"
Start-Process `
    -FilePath $PythonExe `
    -ArgumentList "-m", "app.handoff_worker" `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $Stdout `
    -RedirectStandardError $Stderr

Start-Sleep -Seconds 4
& $PythonExe -m app.handoff_worker --status
