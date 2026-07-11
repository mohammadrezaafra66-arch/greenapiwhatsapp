[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host '============================================'
Write-Host '   وضعیت سیستم افراکالا'
Write-Host '============================================'
Write-Host ''

Write-Host 'وضعیت کانتینرها:'
Write-Host '--------------------------------------------'
docker compose ps
Write-Host ''

Write-Host 'بررسی سلامت سرویس (Backend):'
Write-Host '--------------------------------------------'
try {
    $h = Invoke-RestMethod -Uri 'http://localhost:8002/health/detailed' -TimeoutSec 8
    $h | ConvertTo-Json -Depth 6
} catch {
    Write-Host "   خطا در دریافت سلامت: $($_.Exception.Message)" -ForegroundColor Red
}
Read-Host "`nبرای بستن این پنجره Enter را بزنید"
