Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

& ".\.venv\Scripts\python.exe" -m PyInstaller `
    --noconsole `
    --onefile `
    --name TaskPlannerDesktop `
    --paths "$Root" `
    --collect-submodules pystray `
    --collect-submodules PIL `
    "desktop_app\main.py"

Write-Host "Built: $Root\dist\TaskPlannerDesktop.exe"