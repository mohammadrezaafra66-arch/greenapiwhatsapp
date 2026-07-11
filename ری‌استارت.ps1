[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host '============================================'
Write-Host '   ری‌استارت سرویس‌های افراکالا'
Write-Host '============================================'
Write-Host ''

Write-Host 'در حال ری‌استارت سرویس‌ها...'
docker compose restart backend worker-general worker-webhooks beat frontend
Write-Host ''
Write-Host 'ری‌استارت کامل شد.'
Read-Host "`nبرای بستن این پنجره Enter را بزنید"
