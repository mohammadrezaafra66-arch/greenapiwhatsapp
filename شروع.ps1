[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$domain = 'https://multidisciplinary-jeri-physiognomically.ngrok-free.dev'

Write-Host '============================================'
Write-Host '   راه‌اندازی سیستم افراکالا'
Write-Host '============================================'
Write-Host ''

Write-Host '[1/4] بررسی اجرای Docker...'
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host '   [خطا] Docker Desktop در حال اجرا نیست. ابتدا آن را باز کنید.' -ForegroundColor Red
    Read-Host "`nبرای بستن این پنجره Enter را بزنید"
    exit 1
}
Write-Host '   Docker فعال است.' -ForegroundColor Green
Write-Host ''

Write-Host '[2/4] راه‌اندازی کانتینرها (docker compose up -d)...'
docker compose up -d
Write-Host ''

Write-Host '[3/4] راه‌اندازی ngrok روی دامنه ثابت...'
Start-Process -FilePath 'ngrok.cmd' -ArgumentList 'http', "--url=$domain", '8002'
Write-Host '   ngrok در یک پنجره جدید اجرا شد.'
Write-Host ''

Write-Host '[4/4] چند لحظه صبر کنید تا سرویس‌ها آماده شوند...'
Start-Sleep -Seconds 8
Start-Process 'http://localhost:3002'
Write-Host ''

$ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
       Where-Object { $_.IPAddress -match '^(192\.168|10)\.' } |
       Select-Object -First 1).IPAddress
if (-not $ip) { $ip = 'localhost' }

Write-Host '============================================'
Write-Host '   سیستم آماده است!'
Write-Host ''
Write-Host "   آدرس روی این کامپیوتر:  http://localhost:3002"
Write-Host "   آدرس برای شبکه/وای‌فای:  http://${ip}:3002"
Write-Host '============================================'
Read-Host "`nبرای بستن این پنجره Enter را بزنید"
