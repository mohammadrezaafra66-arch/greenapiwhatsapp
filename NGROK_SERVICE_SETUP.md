# ngrok به‌عنوان سرویس ویندوز — راه‌اندازی و نگهداری

> هدف: ngrok به‌جای اجرای دستی (`شروع.bat`)، به‌صورت **سرویس ویندوز** اجرا شود تا هنگام
> روشن‌شدن سیستم خودکار بالا بیاید و در صورت کرش، دوباره اجرا شود. این کار از قطع خاموش
> شدن webhook جلوگیری می‌کند (که قبلاً باعث ۲ روز قطعی شده بود).

---

## ✅ وضعیت فعلی (بررسی‌شده)

سرویس **همین‌الان نصب و در حال اجراست** — نیازی به اقدام فوری نیست:

- نام سرویس: `ngrok` · وضعیت: **RUNNING** · نوع شروع: **AUTO_START** (خودکار در بوت)
- مسیر اجرا: `C:\Users\AFRA\AppData\Roaming\npm\node_modules\ngrok\bin\ngrok.exe service run --config C:\Users\AFRA\AppData\Local\ngrok\ngrok.yml`
- تونل فعال: `https://multidisciplinary-jeri-physiognomically.ngrok-free.dev → http://localhost:8002`

بررسی سریع وضعیت (نیازی به ادمین ندارد):
```powershell
sc query ngrok
Invoke-RestMethod http://localhost:4040/api/tunnels | % tunnels | Select public_url,@{n='addr';e={$_.config.addr}}
```

اگر خروجی بالا را دیدید، همه‌چیز درست است و بقیهٔ این فایل فقط برای **نصب مجدد، پشتیبان‌گیری،
جایگزین‌ها و بازگردانی** است.

---

## پیکربندی (نسخهٔ ۳)

- فایل واقعی: `C:\Users\AFRA\AppData\Local\ngrok\ngrok.yml` (شامل authtoken — محرمانه، در گیت نیست).
- الگوی نسخه‌کنترل‌شده (بدون توکن): [`ngrok.yml.example`](./ngrok.yml.example).
- پشتیبان امن: `C:\Users\AFRA\AppData\Local\ngrok\ngrok.yml.backup-v16` (قبل از هر تغییر ساخته شد).

محتوای درست (نسخهٔ ۳، دامنهٔ ثابت رایگان، پورت ۸۰۰۲ که webhook به آن فوروارد می‌شود):
```yaml
version: "3"
agent:
    authtoken: <YOUR_NGROK_AUTHTOKEN>
tunnels:
    afrakala:
        proto: http
        addr: 8002
        domain: multidisciplinary-jeri-physiognomically.ngrok-free.dev
        inspect: true
```

---

## نصب سرویس (اگر لازم شد از نو) — **PowerShell با دسترسی Administrator**

> ⚠️ فقط وقتی این را اجرا کنید که سرویس نصب نباشد یا بخواهید از نو نصب کنید. اجرای مجدد
> نصب، تونل زنده را چند ثانیه قطع می‌کند. اگر تونل الان کار می‌کند، دست نزنید.

```powershell
# 1) بررسی مسیر و نسخهٔ ngrok.exe (از shim npm استفاده نکنید؛ همین exe درست است)
$ngrok = "C:\Users\AFRA\AppData\Roaming\npm\node_modules\ngrok\bin\ngrok.exe"
& $ngrok version                       # باید 3.x باشد
$cfg = "C:\Users\AFRA\AppData\Local\ngrok\ngrok.yml"
& $ngrok config check --config $cfg    # باید «Valid configuration file» بدهد

# 2) اگر از قبل نصب است، اول متوقف و حذف کنید (وگرنه این مرحله را رد کنید)
& $ngrok service stop      2>$null
& $ngrok service uninstall 2>$null

# 3) نصب + شروع
& $ngrok service install --config $cfg
& $ngrok service start

# 4) خودکار-ری‌استارت روی کرش + شروع خودکار در بوت
sc.exe failure ngrok reset= 86400 actions= restart/5000/restart/5000/restart/5000
sc.exe config  ngrok start= auto
```

### تأیید نصب
```powershell
sc query ngrok                                            # STATE باید RUNNING باشد
& "C:\Users\AFRA\AppData\Roaming\npm\node_modules\ngrok\bin\ngrok.exe" service status
Invoke-RestMethod http://localhost:4040/api/tunnels | % tunnels | Select public_url
# انتظار: https://multidisciplinary-jeri-physiognomically.ngrok-free.dev
```

---

## جایگزین ۱ — NSSM (اگر `service install` با خطای exit code 5 / دسترسی شکست خورد)

```powershell
# NSSM را از https://nssm.cc دانلود و در PATH قرار دهید، سپس (با ادمین):
$ngrok = "C:\Users\AFRA\AppData\Roaming\npm\node_modules\ngrok\bin\ngrok.exe"
$cfg   = "C:\Users\AFRA\AppData\Local\ngrok\ngrok.yml"
nssm install ngrok "$ngrok" "start --all --config `"$cfg`""
nssm set ngrok Start SERVICE_AUTO_START
nssm set ngrok AppExit Default Restart          # ری‌استارت خودکار روی کرش
nssm start ngrok
nssm status ngrok                               # باید SERVICE_RUNNING باشد
```
حذف: `nssm stop ngrok ; nssm remove ngrok confirm`

---

## جایگزین ۲ — Task Scheduler «هنگام روشن‌شدن» (بدون سرویس)

```powershell
# با ادمین. تونل را در بوت اجرا می‌کند (بدون خودکار-ری‌استارت روی کرش سرویس؛ ساده‌تر).
$ngrok = "C:\Users\AFRA\AppData\Roaming\npm\node_modules\ngrok\bin\ngrok.exe"
$cfg   = "C:\Users\AFRA\AppData\Local\ngrok\ngrok.yml"
$action  = New-ScheduledTaskAction -Execute $ngrok -Argument "start --all --config `"$cfg`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings= New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "ngrok-tunnel" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -User "SYSTEM"
Start-ScheduledTask -TaskName "ngrok-tunnel"
```
حذف: `Unregister-ScheduledTask -TaskName "ngrok-tunnel" -Confirm:$false`

---

## بازگردانی (Rollback) — بازگشت به اجرای دستی با `شروع.bat`

```powershell
# با ادمین:
$ngrok = "C:\Users\AFRA\AppData\Roaming\npm\node_modules\ngrok\bin\ngrok.exe"
& $ngrok service stop
& $ngrok service uninstall
# بازگرداندن کانفیگ در صورت نیاز:
Copy-Item "C:\Users\AFRA\AppData\Local\ngrok\ngrok.yml.backup-v16" "C:\Users\AFRA\AppData\Local\ngrok\ngrok.yml" -Force
# سپس تونل را دستی اجرا کنید (همان روش قبلی):
& $ngrok start --all --config "C:\Users\AFRA\AppData\Local\ngrok\ngrok.yml"
```

> نکته: webhook همیشه باید به پورت **۸۰۰۲** (backend) فوروارد شود و دامنهٔ ثابت
> `multidisciplinary-jeri-physiognomically.ngrok-free.dev` تغییر نکند. حالت **polling** هرگز
> فعال نشود — webhook و polling با هم ناسازگارند.
