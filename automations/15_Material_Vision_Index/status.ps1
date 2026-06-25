$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$StateDir = Join-Path $ProjectRoot "data\material_ingest"
$StatePath = Join-Path $StateDir "worker_state.json"
$NoticePath = Join-Path $StateDir "latest_notice.json"
$FailedPath = Join-Path $StateDir "failed_images.json"
$ReviewedCatalog = Join-Path $ProjectRoot "data\line_material_catalog.json"
$PendingCatalog = Join-Path $StateDir "pending_catalog.json"

function Get-RecordCount {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return 0
    }
    try {
        $Catalog = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        return @($Catalog.records).Count
    }
    catch {
        return "INVALID"
    }
}

Write-Host ""
Write-Host "LINE Material Vision Watcher" -ForegroundColor Cyan
Write-Host "============================"

if (-not (Test-Path -LiteralPath $StatePath)) {
    Write-Host "[NOT STARTED] No watcher state file." -ForegroundColor Red
    Write-Host "Start: powershell -ExecutionPolicy Bypass -File automations\15_Material_Vision_Index\start_watcher_hidden.ps1"
    exit 1
}

$State = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
$Process = Get-Process -Id $State.pid -ErrorAction SilentlyContinue
$Ollama = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
$Heartbeat = [DateTimeOffset]::Parse($State.heartbeat_at).ToLocalTime()
$HeartbeatAge = [Math]::Round(([DateTimeOffset]::Now - $Heartbeat).TotalSeconds)

if ($Process) {
    Write-Host "[RUNNING] PID $($State.pid) | $($State.status.ToString().ToUpperInvariant())" -ForegroundColor Green
}
else {
    Write-Host "[STOPPED] Recorded PID $($State.pid) is not alive." -ForegroundColor Red
}

if ($Ollama) {
    Write-Host "[OLLAMA OK] Model $($State.model)" -ForegroundColor Green
}
else {
    Write-Host "[OLLAMA OFFLINE] Start Ollama before analyzing images." -ForegroundColor Red
}

Write-Host "Heartbeat: $($Heartbeat.ToString('yyyy-MM-dd HH:mm:ss zzz')) ($HeartbeatAge seconds ago)"
Write-Host "Watching:  $($State.root)"

if (Test-Path -LiteralPath $NoticePath) {
    $Notice = Get-Content -LiteralPath $NoticePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $NoticeTime = [DateTimeOffset]::Parse($Notice.completed_at).ToLocalTime()
    $NoticeColor = switch ($Notice.result) {
        "success" { "Green" }
        "error" { "Red" }
        default { "Yellow" }
    }
    Write-Host ""
    Write-Host "Last completed cycle: $($NoticeTime.ToString('yyyy-MM-dd HH:mm:ss zzz'))"
    Write-Host "[$($Notice.result.ToString().ToUpperInvariant())] $($Notice.message)" -ForegroundColor $NoticeColor
    if ($Notice.path) {
        Write-Host "Picture: $($Notice.path)"
    }
    if ($Notice.material_id) {
        Write-Host "Technical ID: $($Notice.material_id)" -ForegroundColor DarkGray
    }
}
elseif ($State.last_cycle_at) {
    Write-Host "Last cycle: $($State.last_cycle_at) | imported=$($State.imported) failed=$($State.failed)"
}

Write-Host ""
Write-Host "Catalogs"
Write-Host "Reviewed: $(Get-RecordCount $ReviewedCatalog) records"
Write-Host "  $ReviewedCatalog"
Write-Host "Pending Ollama review: $(Get-RecordCount $PendingCatalog) records"
Write-Host "  $PendingCatalog"
Write-Host "Quarantined after failed analysis: $(Get-RecordCount $FailedPath) records"
Write-Host "  $FailedPath"
Write-Host ""

if (-not $Process -or -not $Ollama) {
    exit 1
}
if ($Notice -and $Notice.result -eq "error") {
    exit 2
}
exit 0
