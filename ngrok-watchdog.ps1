# Afrakala ngrok watchdog.
# Ensures the reserved-domain ngrok tunnel to the backend (:8002) is alive.
# If the tunnel is down, relaunches ngrok.cmd on the reserved domain.
# Intended to run every ~2 minutes via Task Scheduler (see install-ngrok-watchdog.ps1).
$ErrorActionPreference = "SilentlyContinue"

$domain = "multidisciplinary-jeri-physiognomically.ngrok-free.dev"
$logDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir "ngrok-watchdog.log"
function Write-Log($m) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Out-File -FilePath $log -Append -Encoding utf8
}

# 1) Is the reserved-domain tunnel currently up (via the local ngrok agent API)?
$alive = $false
try {
    $r = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -TimeoutSec 4
    if ($r.tunnels | Where-Object { $_.public_url -like "*$domain*" }) { $alive = $true }
} catch { $alive = $false }

if ($alive) { exit 0 }   # healthy — do nothing (does NOT disturb a working tunnel)

# 2) Tunnel is down — clear any stale ngrok process, then relaunch on the reserved domain.
Write-Log "tunnel DOWN -> relaunching ngrok on $domain"
Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-Process -FilePath "ngrok.cmd" -ArgumentList "http", "--url=https://$domain", "8002" -WindowStyle Hidden

# 3) Confirm it came back up.
Start-Sleep -Seconds 6
try {
    $r2 = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -TimeoutSec 4
    if ($r2.tunnels | Where-Object { $_.public_url -like "*$domain*" }) {
        Write-Log "ngrok relaunched OK"
    } else {
        Write-Log "relaunch attempted; tunnel not visible yet"
    }
} catch {
    Write-Log "relaunch attempted; :4040 not responding yet"
}
