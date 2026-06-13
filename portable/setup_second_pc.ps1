$ErrorActionPreference = "Stop"

$KitRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceRoot = Join-Path $KitRoot "source"
$MaterialRoot = Join-Path $KitRoot "materials\行動力"
$VenvPython = Join-Path $SourceRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $SourceRoot)) {
    throw "Portable source directory is missing: $SourceRoot"
}
if (-not (Test-Path -LiteralPath $MaterialRoot)) {
    throw "Portable material directory is missing: $MaterialRoot"
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv (Join-Path $SourceRoot ".venv")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv (Join-Path $SourceRoot ".venv")
    } else {
        throw "Python 3 is not installed or not available on PATH."
    }
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $SourceRoot "requirements.txt")

$Template = Get-Content -LiteralPath (Join-Path $KitRoot "portable.env.example") -Raw
$MaterialValue = $MaterialRoot.Replace("\", "/")
$Config = $Template.Replace("__MATERIAL_ROOT__", $MaterialValue)
Set-Content -LiteralPath (Join-Path $SourceRoot ".env") -Value $Config -Encoding UTF8

Write-Host "Portable environment prepared."
Write-Host "Dependency installation may require internet access."
Write-Host "Credentials were not included. Add Google credentials separately when needed."
& $VenvPython (Join-Path $KitRoot "doctor_second_pc.py")
