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

while ($true) {
    Clear-Host
    Write-Host "LINE Daily Runbook" -ForegroundColor Cyan
    Write-Host "Project: $ProjectRoot"
    Write-Host ""
    Write-Host "1. Search picture materials" -ForegroundColor Green
    Write-Host "2. Show live-ready picture materials" -ForegroundColor Green
    Write-Host "3. Create one picture review draft" -ForegroundColor Yellow
    Write-Host "4. Build all scenario LINE_Drafts" -ForegroundColor Yellow
    Write-Host "5. Preview approved LINE_Drafts" -ForegroundColor Yellow
    Write-Host "6. Run unit tests" -ForegroundColor Cyan
    Write-Host "7. Show Git status/diff" -ForegroundColor Cyan
    Write-Host "8. Open written runbook" -ForegroundColor Cyan
    Write-Host "9. Show persistent worker status" -ForegroundColor Cyan
    Write-Host "10. Start persistent worker hidden" -ForegroundColor Green
    Write-Host "11. Capture passive LINE observation" -ForegroundColor Green
    Write-Host "12. Stop persistent worker" -ForegroundColor Yellow
    Write-Host "13. LIVE send approved rows" -ForegroundColor Red
    Write-Host "Q. Quit"
    Write-Host ""

    $Choice = Read-Host "Choose"
    switch ($Choice.ToUpperInvariant()) {
        "1" {
            $Search = Read-Host "Product, topic, audience, Material_ID, or hashtag"
            Invoke-Python -m app.material_picker --search $Search --limit 30
        }
        "2" {
            Invoke-Python -m app.material_picker --live-only --limit 100
        }
        "3" {
            $LineQuery = Read-Host "Exact LINE friend/group query"
            $MaterialId = Read-Host "Approved Material_ID (for example MAT-ACT-006)"
            Invoke-Python -m app.line_picture_drafts `
                --line-query $LineQuery `
                --material-id $MaterialId
        }
        "4" {
            Invoke-Python -m app.line_draft_builder --types all --max-per-type 10
        }
        "5" {
            Invoke-Python -m app.approved_draft_sender --max-rows 10
        }
        "6" {
            Invoke-Python -m unittest discover -s tests
        }
        "7" {
            git status --short --branch
            git diff --stat
        }
        "8" {
            Start-Process notepad.exe -ArgumentList (Join-Path $ProjectRoot "LINE_RUNBOOK.md")
        }
        "9" {
            Invoke-Python -m app.handoff_worker --status
        }
        "10" {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
                (Join-Path $ProjectRoot "automations\10_LINE_Message_Test\start_worker_hidden.ps1")
        }
        "11" {
            Invoke-Python -m app.handoff_worker --observe
        }
        "12" {
            Invoke-Python -m app.handoff_worker --stop
        }
        "13" {
            Write-Host "This can send real LINE messages." -ForegroundColor Red
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
    Write-Host ""
    Read-Host "Press Enter to return to the menu"
}
