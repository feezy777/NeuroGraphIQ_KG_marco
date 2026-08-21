# NeuroGraphIQ KG V3 - one-click workbench launcher (backend 8002 + frontend 5173 + browser)
# NOTE: keep this file UTF-8 with BOM so Windows PowerShell 5.1 decodes it correctly.
# Each service gets its own titled window + transcript log under scripts/logs/ for diagnosis.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "scripts\logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

# 0) kill stale workbench windows/processes first so repeated double-clicks
#    never race each other (each click starts exactly one backend + one frontend).
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "NeuroGraphIQ (Backend|Frontend)" -or $_.CommandLine -match "start-backend\.ps1" -or $_.CommandLine -match "npm run dev" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "run_server" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "vite" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

$backendScript = Join-Path $PSScriptRoot "start-backend.ps1"
$frontendScript = Join-Path $PSScriptRoot "start-frontend.ps1"
$backendLog = Join-Path $LogDir "backend-$stamp.log"
$frontendLog = Join-Path $LogDir "frontend-$stamp.log"

# 1) backend: titled window + output tee (no Start-Transcript — it locks the log file)
Start-Process powershell -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass",
    "-Command",
    "`$Host.UI.RawUI.WindowTitle='NeuroGraphIQ Backend 8002'; & '$backendScript' 2>&1 | Tee-Object -FilePath '$backendLog'"
)

# 2) frontend: titled window; start-frontend.ps1 runs node detached with its own log
Start-Process powershell -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass",
    "-Command",
    "`$Host.UI.RawUI.WindowTitle='NeuroGraphIQ Frontend 5173'; & '$frontendScript'"
)

# 3) wait for both ports, then open the browser
function Wait-Port([int]$Port, [int]$TimeoutSec) {
    for ($i = 0; $i -lt $TimeoutSec; $i++) {
        Start-Sleep -Seconds 1
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port" -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -lt 500) { return $true }
        } catch { }
    }
    return $false
}

Write-Host "Waiting for backend 8002 and frontend 5173 ..." -ForegroundColor DarkGray
$backendOk = Wait-Port 8002 90
$frontendOk = Wait-Port 5173 90
if ($backendOk) { Write-Host "[OK] backend  http://127.0.0.1:8002" -ForegroundColor Green }
else { Write-Host "[FAIL] backend did not start - see log: $backendLog" -ForegroundColor Yellow }
if ($frontendOk) { Write-Host "[OK] frontend http://localhost:5173" -ForegroundColor Green }
else { Write-Host "[FAIL] frontend did not start - see log: $frontendLog" -ForegroundColor Yellow }
if ($frontendOk) { Start-Process "http://localhost:5173" }
