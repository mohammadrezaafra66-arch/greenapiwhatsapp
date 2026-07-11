[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host '============================================'
Write-Host '   پشتیبان‌گیری از پایگاه داده'
Write-Host '============================================'
Write-Host ''

$dir = Join-Path $PSScriptRoot 'backups'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$out = Join-Path $dir "whatsapp_sender_$stamp.sql"

Write-Host 'فایل خروجی:'
Write-Host "   $out"
Write-Host ''

Write-Host 'در حال تهیه پشتیبان (docker exec pg_dump)...'
# Redirect via cmd so the dump is written as raw UTF-8 bytes.
# (Windows PowerShell 5.1 '>' would save as UTF-16, corrupting the SQL file.)
cmd /c "docker exec claudegreenapi-db-1 pg_dump -U afrakala whatsapp_sender > `"$out`""
if ($LASTEXITCODE -eq 0 -and (Test-Path $out)) {
    $mb = [math]::Round((Get-Item $out).Length / 1MB, 2)
    Write-Host "   پشتیبان با موفقیت ذخیره شد ($mb مگابایت)." -ForegroundColor Green
} else {
    Write-Host '   [خطا] پشتیبان‌گیری ناموفق بود. مطمئن شوید کانتینر پایگاه داده در حال اجراست.' -ForegroundColor Red
}
Read-Host "`nبرای بستن این پنجره Enter را بزنید"
