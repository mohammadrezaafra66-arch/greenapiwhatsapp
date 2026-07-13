# Registers the Afrakala ngrok watchdog as a Windows Scheduled Task (runs every 2
# minutes). Uses schtasks so NO admin/elevation is required for a current-user task.
# Run once:  powershell -NoProfile -ExecutionPolicy Bypass -File install-ngrok-watchdog.ps1
$ErrorActionPreference = "Stop"

$taskName = "AfrakalaNgrokWatchdog"
$script = Join-Path $PSScriptRoot "ngrok-watchdog.ps1"
$run = "powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""

schtasks /create /tn $taskName /tr $run /sc minute /mo 2 /f | Out-Host

Write-Host ""
Write-Host "Registered '$taskName' (every 2 minutes)."
Write-Host "It relaunches ngrok on the reserved domain if the tunnel dies, and no-ops when healthy."
Write-Host "Log: .\logs\ngrok-watchdog.log"
