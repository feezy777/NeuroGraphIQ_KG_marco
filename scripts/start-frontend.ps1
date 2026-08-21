# NeuroGraphIQ KG V3 - start frontend dev server (Vite, fixed port 5173)
# NOTE: keep this file UTF-8 with BOM so Windows PowerShell 5.1 decodes it correctly.
# Node runs DETACHED so it survives this launcher window; output goes to a log file.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$FrontendDir = Join-Path $Root "frontend"
$LogDir = Join-Path $Root "scripts\logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$viteLog = Join-Path $LogDir "vite-$stamp.log"

# kill stale vite
Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "vite" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

Write-Host "Starting frontend: http://localhost:5173 (log: $viteLog)" -ForegroundColor Green

# locate node explicitly (PATH may differ when launched from .lnk)
$nodeExe = "node"
if (Test-Path "D:\Tool\Coding\Environment\node\node.exe") {
    $nodeExe = "D:\Tool\Coding\Environment\node\node.exe"
}

# detached node with output redirect — survives launcher window
# NOTE: RedirectStandardOutput and RedirectStandardError must be DIFFERENT files
$viteErrLog = Join-Path $LogDir "vite-err-$stamp.log"
Start-Process -FilePath $nodeExe -ArgumentList "node_modules\vite\bin\vite.js","--port","5173","--strictPort" `
    -WorkingDirectory $FrontendDir `
    -RedirectStandardOutput $viteLog `
    -RedirectStandardError $viteErrLog `
    -WindowStyle Hidden
