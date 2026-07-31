# تجزیه کامل وضعیت پروژه Afrakala WhatsApp Sender
# اجرا کن: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; & ".\status_complete.ps1"

$repo = "C:\Users\AFRA\Desktop\bots\claudegreenapi"
Set-Location $repo

Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "📊 تجزیه کامل وضعیت پروژه" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan

Write-Host "`n🔗 وضعیت Git:" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

$branch = git rev-parse --abbrev-ref HEAD
$hash = git rev-parse --short HEAD
Write-Host "فعلی: $branch ($hash)" -ForegroundColor Green

Write-Host "`nتمام branches:" -ForegroundColor Cyan
git branch -v | ForEach-Object { Write-Host "   $_" }

Write-Host "`n\n📜 آخرین 20 commit:" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
git log --all --oneline --graph --decorate | Select-Object -First 20 | ForEach-Object { Write-Host $_ }

Write-Host "`n\n📄 Prompt Files (موجود):" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
$prompts = Get-ChildItem -Path $repo -Filter "V*.md" -File | Sort-Object Name
$prompts += Get-ChildItem -Path $repo -Filter "V*.txt" -File | Sort-Object Name

if ($prompts.Count -eq 0) {
    Write-Host "❌ هیچ prompt پیدا نشد" -ForegroundColor Red
} else {
    $prompts | ForEach-Object {
        $size = $_.Length / 1KB
        Write-Host "   ✅ $($_.Name) ($([math]::Round($size, 1)) KB)"
    }
}

Write-Host "`n\n🔍 تمام Versions و Commits:" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

$allCommits = git log --all --oneline --format="%h | %s"
$versionMap = @{}

foreach ($line in $allCommits -split "`n") {
    if ($line -match 'V(\d+)') {
        $version = [int]$matches[1]
        if (-not $versionMap.ContainsKey($version)) {
            $versionMap[$version] = @()
        }
        $versionMap[$version] += $line
    }
}

if ($versionMap.Count -eq 0) {
    Write-Host "❌ هیچ V-tagged commit پیدا نشد" -ForegroundColor Red
} else {
    $versionMap.Keys | Sort-Object { [int]$_ } | ForEach-Object {
        $v = $_
        $hasPrompt = $prompts | Where-Object { $_.Name -match "V$v" } | Measure-Object | Select-Object -ExpandProperty Count
        $promptIcon = if ($hasPrompt -gt 0) { "✅" } else { "❌" }
        Write-Host "`n   V$v $promptIcon"
        foreach ($commit in $versionMap[$v]) {
            Write-Host "      • $commit"
        }
    }
}

Write-Host "`n\n🔥 V51 و V52 (جزئی):" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

Write-Host "`n   V51:" -ForegroundColor Cyan
$v51_prompt = $prompts | Where-Object { $_.Name -match "V51" }
$v51_commits = git log --all --oneline | Where-Object { $_ -match "V51" }
Write-Host "      Prompt: $(if ($v51_prompt) { '✅ موجود' } else { '❌ نیست' })" -ForegroundColor $(if ($v51_prompt) { 'Green' } else { 'Red' })
Write-Host "      Commits: $($v51_commits.Count) تا"
if ($v51_commits) {
    $v51_commits | ForEach-Object { Write-Host "         • $_" }
}

# بررسی product_ai_merge.py
$product_ai = Join-Path $repo "backend\app\services\product_ai_merge.py"
if (Test-Path $product_ai) {
    $size = (Get-Item $product_ai).Length
    Write-Host "      📁 product_ai_merge.py: ✅ ($size bytes)" -ForegroundColor Green
} else {
    Write-Host "      📁 product_ai_merge.py: ❌ نیست" -ForegroundColor Red
}

Write-Host "`n   V52:" -ForegroundColor Cyan
$v52_prompt = $prompts | Where-Object { $_.Name -match "V52" }
$v52_commits = git log --all --oneline | Where-Object { $_ -match "V52" }
Write-Host "      Prompt: $(if ($v52_prompt) { '✅ موجود' } else { '❌ نیست' })" -ForegroundColor $(if ($v52_prompt) { 'Green' } else { 'Red' })
Write-Host "      Commits: $($v52_commits.Count) تا"
if ($v52_commits) {
    $v52_commits | ForEach-Object { Write-Host "         • $_" }
}

Write-Host "`n\n🌳 وضعیت Branches:" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

$main_hash = git rev-parse main 2>$null
$redesign_hash = git rev-parse afrapayam-redesign 2>$null

Write-Host "   main:               $main_hash"
Write-Host "   afrapayam-redesign: $(if ($redesign_hash) { $redesign_hash } else { 'ندارد' })"

if ($main_hash -and $redesign_hash -and $main_hash -ne $redesign_hash) {
    Write-Host "   ⚠️  شاخه‌ها جدا شده‌اند!" -ForegroundColor Yellow
    Write-Host "`n   Commits در redesign که در main نیستند:" -ForegroundColor Yellow
    git log main..afrapayam-redesign --oneline | Select-Object -First 10 | ForEach-Object { 
        Write-Host "      • $_" 
    }
} elseif ($main_hash -and $redesign_hash) {
    Write-Host "   ✅ شاخه‌ها sync هستند" -ForegroundColor Green
}

Write-Host "`n\n📊 خلاصه نهایی:" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

$maxVersion = $versionMap.Keys | Sort-Object { [int]$_ } | Select-Object -Last 1
Write-Host "   • آخرین Version: V$maxVersion"
Write-Host "   • Prompts موجود: $($prompts.Count)"
Write-Host "   • V-tagged commits: $($versionMap.Count) version"
Write-Host "   • V51: $(if ($v51_commits) { '✅ وجود دارد' } else { '❌ ندارد' })"
Write-Host "   • V52: $(if ($v52_commits) { '✅ وجود دارد' } else { '❌ ندارد' })"
Write-Host "   • product_ai_merge.py: $(if (Test-Path $product_ai) { '✅' } else { '❌' })"

Write-Host "`n════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "✅ تجزیه کامل شد" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan