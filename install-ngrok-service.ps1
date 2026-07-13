# Installs ngrok as a Windows SERVICE so the reserved-domain tunnel
#   https://multidisciplinary-jeri-physiognomically.ngrok-free.dev  ->  localhost:8002
# auto-starts on boot and auto-restarts on crash (Windows SCM supervises it).
#
# This REPLACES the old every-2-min "AfrakalaNgrokWatchdog" scheduled task, which
# relaunched a command-line tunnel. Two supervisors would fight over the one
# reserved domain, so this script removes the task before installing the service.
#
# REQUIRES ADMIN. Run once in an elevated PowerShell:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install-ngrok-service.ps1
$ErrorActionPreference = "Stop"

# --- resolve the real ngrok.exe (npm ships it under node_modules) ---
$exe = "$env:APPDATA\npm\node_modules\ngrok\bin\ngrok.exe"
if (-not (Test-Path $exe)) {
    $cmd = Get-Command ngrok.exe -ErrorAction SilentlyContinue
    if ($cmd) { $exe = $cmd.Source }
}
if (-not (Test-Path $exe)) { throw "ngrok.exe not found. Expected at $exe" }

$config = "$env:LOCALAPPDATA\ngrok\ngrok.yml"
if (-not (Test-Path $config)) { throw "ngrok config not found at $config" }

# --- admin check ---
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin) {
    throw "Not elevated. Re-run this in an ADMIN PowerShell (right-click > Run as administrator)."
}

Write-Host "ngrok.exe : $exe"
Write-Host "config    : $config"
Write-Host ""

# --- 1) retire the old watchdog scheduled task (stop dueling supervisors) ---
schtasks /query /tn AfrakalaNgrokWatchdog 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Removing old AfrakalaNgrokWatchdog scheduled task..."
    schtasks /end    /tn AfrakalaNgrokWatchdog 2>$null | Out-Null
    schtasks /delete /tn AfrakalaNgrokWatchdog /f | Out-Host
}

# --- 2) stop any running command-line ngrok so the service can bind the domain ---
Write-Host "Stopping any running ngrok processes (brief tunnel blip during switchover)..."
Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# --- 3) (re)install the service, pointing at the config that defines the tunnel ---
# Uninstall first in case a prior/partial install exists, so this script is idempotent.
& $exe service stop     2>$null | Out-Null
& $exe service uninstall 2>$null | Out-Null
Start-Sleep -Seconds 1

Write-Host "Installing ngrok service..."
& $exe service install --config $config | Out-Host

# Make Windows auto-restart the service if the process ever dies.
sc.exe failure ngrok reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Host
sc.exe config  ngrok start= auto | Out-Host

Write-Host "Starting ngrok service..."
& $exe service start | Out-Host

Start-Sleep -Seconds 6

# --- 4) verify ---
Write-Host ""
Write-Host "===== ngrok service status ====="
& $exe service status | Out-Host
Write-Host ""
Write-Host "===== active tunnels (local agent API) ====="
try {
    (Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -TimeoutSec 5).tunnels |
        Select-Object public_url, @{n='addr';e={$_.config.addr}} | Format-Table -AutoSize | Out-Host
} catch {
    Write-Host "  :4040 not answering yet - give it a few seconds and re-check with: ngrok service status"
}
Write-Host ""
Write-Host "Done. The tunnel is now supervised by Windows and survives reboots + crashes."
