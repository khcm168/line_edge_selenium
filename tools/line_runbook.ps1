$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = "python"
}

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $PythonExe @Arguments
}

function Wait-ForMenu {
    Write-Host ""
    Read-Host "Press Enter to return to the menu" | Out-Null
}

function Show-WorkerStatus {
    Invoke-Python -m app.handoff_worker --status
    $OwnerPath = Join-Path $ProjectRoot "data\handoff\worker_owner.json"
    if (Test-Path -LiteralPath $OwnerPath) {
        Write-Host ""
        Write-Host "Owner file: $OwnerPath" -ForegroundColor Cyan
        Get-Content -LiteralPath $OwnerPath -Raw -Encoding UTF8
    }
}

function Show-EdgeLaunchInventory {
    $ProfileDir = $env:LINE_EDGE_PROFILE_DIR
    if (-not $ProfileDir) {
        $ProfileDir = Join-Path $ProjectRoot "edge-profile"
    }
    Write-Host "LINE Edge profile: $ProfileDir" -ForegroundColor Cyan
    Write-Host ""
    $Processes = Get-CimInstance Win32_Process -Filter "name = 'msedge.exe' or name = 'msedgedriver.exe'" |
        Where-Object {
            ($_.CommandLine -like "*$ProfileDir*") -or
            ($_.CommandLine -like "*ophjlpahpchlmihnnnihgmmeilfjmjjc*") -or
            ($_.Name -eq "msedgedriver.exe")
        } |
        Sort-Object ProcessId

    if (-not $Processes) {
        Write-Host "No LINE automation Edge/msedgedriver process found." -ForegroundColor Yellow
        return
    }

    foreach ($Process in $Processes) {
        Write-Host ("PID {0}  PPID {1}  {2}" -f $Process.ProcessId, $Process.ParentProcessId, $Process.Name) -ForegroundColor Green
        Write-Host ("Started: {0}" -f $Process.CreationDate)
        Write-Host ("Command: {0}" -f $Process.CommandLine)
        Write-Host ""
    }
}

function Open-Runbook {
    Start-Process notepad.exe -ArgumentList (Join-Path $ProjectRoot "LINE_RUNBOOK.md")
}

while ($true) {
    Clear-Host
    Write-Host "LINE Operator Console" -ForegroundColor Cyan
    Write-Host "Project: $ProjectRoot"
    Write-Host "Python:  $PythonExe"
    Write-Host ""
    Write-Host "Worker / Edge ownership" -ForegroundColor Cyan
    Write-Host "  1. Show worker status + owner file"
    Write-Host "  2. Show Edge launch inventory"
    Write-Host "  3. Reclaim stale worker owner"
    Write-Host "  4. Start persistent worker hidden"
    Write-Host "  5. Capture passive LINE observation"
    Write-Host "  6. Stop persistent worker"
    Write-Host ""
    Write-Host "Draft generation" -ForegroundColor Cyan
    Write-Host " 10. Preview Presence Engine drafts"
    Write-Host " 11. Generate Presence Engine drafts to Sheets"
    Write-Host " 12. Build all scenario LINE_Drafts"
    Write-Host " 13. Preview approved LINE_Drafts"
    Write-Host ""
    Write-Host "Picture materials" -ForegroundColor Cyan
    Write-Host " 20. Search picture materials"
    Write-Host " 21. Show live-ready picture materials"
    Write-Host " 22. Create one picture review draft"
    Write-Host " 23. List newly detected material pictures"
    Write-Host " 24. Analyze one new picture with Ollama vision"
    Write-Host " 25. Start material vision watcher hidden"
    Write-Host " 26. Show material vision watcher status"
    Write-Host " 27. Stop material vision watcher"
    Write-Host ""
    Write-Host "Checks / docs" -ForegroundColor Cyan
    Write-Host " 30. Run unit tests"
    Write-Host " 31. Show Git status/diff"
    Write-Host " 32. Open written runbook"
    Write-Host ""
    Write-Host "Live send" -ForegroundColor Red
    Write-Host " 90. LIVE send approved rows"
    Write-Host "  Q. Quit"
    Write-Host ""

    $Choice = Read-Host "Choose"
    switch ($Choice.ToUpperInvariant()) {
        "1" {
            Show-WorkerStatus
        }
        "2" {
            Show-EdgeLaunchInventory
        }
        "3" {
            Invoke-Python -m app.handoff_worker --reclaim-stale-owner
        }
        "4" {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
                (Join-Path $ProjectRoot "automations\10_LINE_Message_Test\start_worker_hidden.ps1")
        }
        "5" {
            Invoke-Python -m app.handoff_worker --observe
        }
        "6" {
            Invoke-Python -m app.handoff_worker --stop
        }
        "10" {
            $MaxClinics = Read-Host "Max clinics [10]"
            if (-not $MaxClinics) { $MaxClinics = "10" }
            Invoke-Python -m app.line_presence_engine --max-clinics $MaxClinics --no-write --no-ai
        }
        "11" {
            $MaxClinics = Read-Host "Max clinics to write [10]"
            if (-not $MaxClinics) { $MaxClinics = "10" }
            Invoke-Python -m app.line_presence_engine --max-clinics $MaxClinics
        }
        "12" {
            Invoke-Python -m app.line_draft_builder --types all --max-per-type 10
        }
        "13" {
            Invoke-Python -m app.approved_draft_sender --max-rows 10
        }
        "20" {
            $Search = Read-Host "Product, topic, audience, Material_ID, or hashtag"
            Invoke-Python -m app.material_picker --search $Search --limit 30
        }
        "21" {
            Invoke-Python -m app.material_picker --live-only --limit 100
        }
        "22" {
            $LineQuery = Read-Host "Exact LINE friend/group query"
            $MaterialId = Read-Host "Approved Material_ID, for example MAT-ACT-006"
            Invoke-Python -m app.line_picture_drafts `
                --line-query $LineQuery `
                --material-id $MaterialId
        }
        "23" {
            Invoke-Python -m app.material_ingest --list-new
        }
        "24" {
            Invoke-Python -m app.material_ingest --max-files 1
        }
        "25" {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
                (Join-Path $ProjectRoot "automations\15_Material_Vision_Index\start_watcher_hidden.ps1")
        }
        "26" {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
                (Join-Path $ProjectRoot "automations\15_Material_Vision_Index\status.ps1")
        }
        "27" {
            Invoke-Python -m app.material_ingest --stop
        }
        "30" {
            Invoke-Python -m unittest discover -s tests
        }
        "31" {
            git status --short --branch
            git diff --stat
        }
        "32" {
            Open-Runbook
        }
        "90" {
            Write-Host "This can send real LINE messages." -ForegroundColor Red
            Write-Host "Rows must already be reviewed with Status=approved and Send_Mode=live." -ForegroundColor Red
            $Confirm = Read-Host "Type SEND APPROVED to continue"
            if ($Confirm -ceq "SEND APPROVED") {
                Invoke-Python -m app.approved_draft_sender --send-approved --max-rows 10
            }
            else {
                Write-Host "Live send cancelled."
            }
        }
        "Q" {
            break
        }
        default {
            Write-Host "Unknown choice."
        }
    }
    if ($Choice.ToUpperInvariant() -eq "Q") {
        break
    }
    Wait-ForMenu
}
