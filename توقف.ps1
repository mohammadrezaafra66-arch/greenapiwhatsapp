[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host '============================================'
Write-Host '   توقف سیستم افراکالا'
Write-Host '============================================'
Write-Host ''

Write-Host '[1/2] متوقف کردن کانتینرها (docker compose stop)...'
docker compose stop
Write-Host ''

Write-Host '[2/2] بستن ngrok...'
$p = Get-Process ngrok -ErrorAction SilentlyContinue
if ($p) {
    $p | Stop-Process -Force
    Write-Host '   ngrok بسته شد.'
} else {
    Write-Host '   ngrok در حال اجرا نبود.'
}
Write-Host ''
Write-Host 'سیستم متوقف شد.'
Read-Host "`nبرای بستن این پنجره Enter را بزنید"
