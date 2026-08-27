# NeuroGraphIQ KG V3 - stop backend + frontend started by start-workbench.ps1.
# python/node command lines are relative under the launched cwd, so besides the
# cmdline match we also walk the parent chain to find THIS project's path.
# PostgreSQL stays running (system service) - stop it via services.msc if needed.
$ErrorActionPreference = "Continue"
$project = "NeuroGraphIQ_KG_V3_1"
$all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)

function Test-ProjectChain {
    param([int]$ProcId)
    for ($chain = 0; $ProcId -gt 0 -and $chain -lt 8; $chain++) {
        $p = $all | Where-Object { $_.ProcessId -eq $ProcId } | Select-Object -First 1
        if (-not $p) { break }
        if ($p.CommandLine -match $project -or $p.ExecutablePath -match $project) { return $true }
        $ProcId = $p.ParentProcessId
    }
    return $false
}

$stopped = $false
$all | Where-Object {
    $_.Name -eq "python.exe" -and $_.CommandLine -match "run_server" -and (Test-ProjectChain $_.ProcessId)
} | ForEach-Object {
    Write-Host "Stopping backend PID $($_.ProcessId)..." -ForegroundColor Yellow
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    $stopped = $true
}
# node is an orphaned child (its launcher powershell exits), so the parent chain
# is gone - anchor instead on the fixed command-line args of this project's vite.
$all | Where-Object {
    $_.Name -eq "node.exe" -and $_.CommandLine -match "vite" -and $_.CommandLine -match "--port 5173"
} | ForEach-Object {
    Write-Host "Stopping frontend PID $($_.ProcessId)..." -ForegroundColor Yellow
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    $stopped = $true
}
# esbuild is a vite child; its cmdline carries the full project path
$all | Where-Object {
    $_.Name -eq "esbuild.exe" -and $_.CommandLine -match $project
} | ForEach-Object {
    Write-Host "Stopping esbuild helper PID $($_.ProcessId)..." -ForegroundColor Yellow
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
# the hidden PowerShell wrapper processes exit by themselves once python/node die
if ($stopped) {
    Write-Host "NeuroGraphIQ services stopped." -ForegroundColor Green
} else {
    Write-Host "No NeuroGraphIQ services are running." -ForegroundColor DarkGray
}
