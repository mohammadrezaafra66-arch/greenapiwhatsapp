[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host '============================================'
Write-Host '   آدرس اشتراک‌گذاری در شبکه محلی'
Write-Host '============================================'
Write-Host ''

Write-Host 'در حال یافتن آدرس IP این دستگاه...'
$ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
       Where-Object { $_.IPAddress -match '^(192\.168|10)\.' } |
       Select-Object -First 1).IPAddress
if (-not $ip) { $ip = 'localhost' }
Write-Host ''

Write-Host '============================================'
Write-Host '   این آدرس را برای افراد دیگر بفرستید:'
Write-Host ''
Write-Host "         http://${ip}:3002" -ForegroundColor Green
Write-Host ''
Write-Host '   (باید به همان شبکه/وای‌فای متصل باشند)'
Write-Host '============================================'
Read-Host "`nبرای بستن این پنجره Enter را بزنید"
