# NeuroGraphIQ KG V3 — start FastAPI (project venv, port 8002)
# Use 8002 so it does not clash with stale listeners on 8001 / apps on 8000.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\backend"
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating venv..." -ForegroundColor Yellow
    python -m venv .venv
    & .\.venv\Scripts\python.exe -m pip install -U pip
}
Write-Host "Syncing dependencies (includes greenlet for async SQLAlchemy)..." -ForegroundColor DarkGray
# pip writes notices to stderr; under $ErrorActionPreference=Stop that aborts the whole
# script (NativeCommandError), so guard the pip call explicitly and fail on real exit codes.
$ErrorActionPreference = "Continue"
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -q 2>$null
if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }
$ErrorActionPreference = "Stop"
if (-not (Test-Path ".\.env")) { Copy-Item .env.example .env }

# Stop uvicorn worker AND reloader parent (Windows: killing only port 8001 respawns stale code).
$port = 8002
$projectBackend = [regex]::Escape("$Root\backend").Replace('\\', '[\\/]')
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $cmd = $_.CommandLine
        $cmd -and (
            $cmd -match "$projectBackend.*run_server\.py" -or
            $cmd -match "$projectBackend.*uvicorn"
        )
    } |
    ForEach-Object {
        Write-Host "Stopping backend PID $($_.ProcessId)..." -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
foreach ($cleanupPort in @($port, 8001)) {
    $pids = netstat -ano | Select-String ":$cleanupPort\s" | ForEach-Object {
        ($_.Line -split '\s+')[-1]
    } | Sort-Object -Unique
    foreach ($procId in $pids) {
        if ($procId -match '^\d+$' -and (Get-Process -Id $procId -ErrorAction SilentlyContinue)) {
            Write-Host "Stopping PID $procId on port $cleanupPort..." -ForegroundColor Yellow
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
}
Start-Sleep -Seconds 2

# idempotent guard: if 8002 is already served (e.g. concurrent double-click), do not
# spawn a second uvicorn that would only fail to bind and linger as a zombie.
$already = netstat -ano | Select-String ":8002\s" | Select-String "LISTENING"
if ($already) {
    Write-Host "Backend already listening on 8002 - skipping start." -ForegroundColor Yellow
    exit 0
}

Write-Host "Starting API: http://127.0.0.1:8002  (docs: http://127.0.0.1:8002/api/docs)" -ForegroundColor Green
# run_server.py sets WindowsSelectorEventLoopPolicy before uvicorn binds (required for psycopg async).
# uvicorn logs to stderr; a direct `2>&1` pipeline under $ErrorActionPreference=Stop
# aborts the server (NativeCommandError). Wrapping in cmd merges streams at the cmd
# layer so PowerShell never sees native stderr; output is tee'd for diagnosis.
$uvicornLog = Join-Path $Root "scripts\logs\uvicorn-$(Get-Date -Format yyyyMMdd-HHmmss).log"
cmd /c ".\.venv\Scripts\python.exe run_server.py 2>&1" | Tee-Object -FilePath $uvicornLog
