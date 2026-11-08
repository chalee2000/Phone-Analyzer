# Build "Phone Analysis" for Windows on a Windows machine.
#   powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
# Needs: Python 3.12, Node.js 20+, internet access (npm, PyPI, dl.google.com).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "== UI ==" -ForegroundColor Yellow
Push-Location frontend
npm ci
npm run build
Pop-Location

Write-Host "== Android platform-tools (adb) ==" -ForegroundColor Yellow
if (-not (Test-Path "resources\platform-tools\adb.exe")) {
    $zip = Join-Path $env:TEMP "platform-tools.zip"
    Invoke-WebRequest "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile $zip
    Expand-Archive $zip -DestinationPath "resources" -Force
}

Write-Host "== Python ==" -ForegroundColor Yellow
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev]"

if (-not (Test-Path "resources\agent\spni-agent.apk")) {
    Write-Host "resources\agent\spni-agent.apk not found - the build will work, but without the Android helper app." -ForegroundColor DarkYellow
}

Write-Host "== PyInstaller ==" -ForegroundColor Yellow
.\.venv\Scripts\pyinstaller spni.spec --noconfirm
Write-Host "Done: dist\Phone Analysis\Phone Analysis.exe" -ForegroundColor Green
