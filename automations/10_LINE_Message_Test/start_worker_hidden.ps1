$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectRoot

function Get-VirtualDesktopState {
    $RegistryPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops"
    if (-not (Test-Path -LiteralPath $RegistryPath)) {
        return $null
    }
    $Property = Get-ItemProperty -LiteralPath $RegistryPath
    if (-not $Property.VirtualDesktopIDs -or -not $Property.CurrentVirtualDesktop) {
        return $null
    }
    $Ids = [byte[]]$Property.VirtualDesktopIDs
    $Current = [guid]([byte[]]$Property.CurrentVirtualDesktop)
    $Desktops = @()
    for ($Index = 0; $Index -lt $Ids.Length; $Index += 16) {
        $Bytes = New-Object byte[] 16
        [Array]::Copy($Ids, $Index, $Bytes, 0, 16)
        $Guid = [guid]$Bytes
        $Desktops += [pscustomobject]@{
            Index = [int](($Index / 16) + 1)
            Guid = $Guid
            IsCurrent = ($Guid -eq $Current)
        }
    }
    return [pscustomobject]@{
        CurrentIndex = [int](($Desktops | Where-Object { $_.IsCurrent } | Select-Object -First 1).Index)
        Desktops = $Desktops
    }
}

function Initialize-VirtualDesktopKeySender {
    if ("LineEdgeSelenium.VirtualDesktopKeySender" -as [type]) {
        return
    }
    Add-Type @"
using System;
using System.Runtime.InteropServices;

namespace LineEdgeSelenium {
    public static class VirtualDesktopKeySender {
        [DllImport("user32.dll")]
        private static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);

        private const uint KEYEVENTF_KEYUP = 0x0002;
        private const byte VK_CONTROL = 0x11;
        private const byte VK_LWIN = 0x5B;
        private const byte VK_LEFT = 0x25;
        private const byte VK_RIGHT = 0x27;

        public static void SwitchDesktop(bool right) {
            byte direction = right ? VK_RIGHT : VK_LEFT;
            keybd_event(VK_LWIN, 0, 0, UIntPtr.Zero);
            keybd_event(VK_CONTROL, 0, 0, UIntPtr.Zero);
            keybd_event(direction, 0, 0, UIntPtr.Zero);
            keybd_event(direction, 0, KEYEVENTF_KEYUP, UIntPtr.Zero);
            keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, UIntPtr.Zero);
            keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, UIntPtr.Zero);
        }
    }
}
"@
}

function Switch-ToWorkerVirtualDesktop {
    if ($env:LINE_WORKER_SKIP_DESKTOP_SWITCH -and $env:LINE_WORKER_SKIP_DESKTOP_SWITCH -ne "0") {
        Write-Output "worker_virtual_desktop=skip_env"
        return
    }

    $TargetText = if ($env:LINE_WORKER_VIRTUAL_DESKTOP_INDEX) {
        $env:LINE_WORKER_VIRTUAL_DESKTOP_INDEX
    }
    else {
        "2"
    }
    $TargetIndex = 0
    if (-not [int]::TryParse($TargetText, [ref]$TargetIndex) -or $TargetIndex -le 0) {
        Write-Output "worker_virtual_desktop=disabled"
        return
    }

    try {
        $State = Get-VirtualDesktopState
        if (-not $State -or -not $State.CurrentIndex) {
            Write-Output "worker_virtual_desktop=unavailable"
            return
        }
        $DesktopCount = @($State.Desktops).Count
        if ($TargetIndex -gt $DesktopCount) {
            Write-Output "worker_virtual_desktop=target_missing:$TargetIndex/$DesktopCount"
            return
        }
        if ($State.CurrentIndex -eq $TargetIndex) {
            Write-Output "worker_virtual_desktop=already:$TargetIndex"
            return
        }

        Initialize-VirtualDesktopKeySender
        $Steps = [Math]::Abs($TargetIndex - $State.CurrentIndex)
        $Right = $TargetIndex -gt $State.CurrentIndex
        for ($Step = 0; $Step -lt $Steps; $Step++) {
            [LineEdgeSelenium.VirtualDesktopKeySender]::SwitchDesktop($Right)
            Start-Sleep -Milliseconds 700
        }
        $After = Get-VirtualDesktopState
        Write-Output "worker_virtual_desktop=current:$($After.CurrentIndex);target:$TargetIndex"
    }
    catch {
        Write-Output "worker_virtual_desktop=warning:$($_.Exception.GetType().Name)"
    }
}

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
$env:LINE_WORKER_LAUNCH_SOURCE = "automations\\10_LINE_Message_Test\\start_worker_hidden.ps1"

$PathValue = [Environment]::GetEnvironmentVariable("Path", "Process")
if (-not $PathValue) {
    $PathValue = [Environment]::GetEnvironmentVariable("PATH", "Process")
}
[Environment]::SetEnvironmentVariable("PATH", $null, "Process")
if ($PathValue) {
    [Environment]::SetEnvironmentVariable("Path", $PathValue, "Process")
}

& $PythonExe -m app.handoff_worker --status *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Output "handoff_worker_already_running=true"
    exit 0
}

& $PythonExe -m app.handoff_worker --reclaim-stale-owner *> $null
Switch-ToWorkerVirtualDesktop

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
