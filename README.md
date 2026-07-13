<div dir="rtl">

# افراکالا واتس‌اپ سندر 🟢

پلتفرم حرفه‌ای ارسال انبوه پیام واتس‌اپ مبتنی بر **Green API** — مدیریت چند حساب، تولید پیام با هوش مصنوعی چند‌ارائه‌دهنده، محدودسازی هوشمند نرخ ارسال بر اساس ساعت تهران، گرم‌سازی ضدمسدودی، و داشبورد مانیتورینگ زنده با رابط فارسی راست‌به‌چپ.

> 📖 **مستندات کامل سیستم:** [SYSTEM_DOCUMENTATION.md](./SYSTEM_DOCUMENTATION.md) — شرح تمام endpoint‌ها، جداول دیتابیس، سرویس‌ها و ویژگی‌ها.

---

## ویژگی‌ها

- **مدیریت چند حساب** — هر شماره یک Instance؛ ارسال چرخشی (round-robin) بین حساب‌های فعال + حساب پیش‌فرض + پروکسی SOCKS5 per-account.
- **هوش مصنوعی چند‌ارائه‌دهنده** — OpenAI → DeepSeek → Gemini با fallback خودکار و رصد مصرف توکن.
- **کمپین‌ها** — متنی/تصویری/نظرسنجی/دکمه‌ای/استوری، هدف‌گیری خصوصی یا **گروهی**، امضای فروشنده، تاریخ شمسی، درج قیمت لحظه‌ای محصولات.
- **ضدمسدودی (Anti-ban)** — پنجره ارسال ساعت تهران، سقف ساعتی افزایشی، تأخیر تصادفی، نشانگر «در حال تایپ»، و **گرم‌سازی** (Warmup: استوری روزانه ۱۰:۰۰ + سقف ۵ پیام تا روز هفتم).
- **دریافت و پاسخ** — وب‌هوک همه رویدادها، پاسخ خودکار، **پاسخ خودکار کلیدواژه‌ای** (خصوصی/گروه)، بلاک خودکار در لغو اشتراک.
- **پنل تحویل (Deliverability)** — نرخ تحویل/خوانده/یلوکارت با نمودار رنگی و هشدار خودکار.
- **گروه‌ها** — همگام‌سازی با تشخیص نوع و تعداد اعضا + backfill پس‌زمینه.
- **گزارش‌گیری** — داشبورد زنده، گزارش شبانه خودکار واتس‌اپ (۲۳:۰۰)، رصد ذکر محصولات.

**در یک نگاه:** ۱۳۱ endpoint · ۷۲ متد Green API · ۲۶ جدول دیتابیس · ۱۸ صفحه فرانت‌اند · ۸ وظیفه Celery.

---

## پشته فنی (Stack)

**Backend:** FastAPI · SQLAlchemy 2 (async) · PostgreSQL 15 · Redis 7 · Celery
**Frontend:** React 18 · Vite · TailwindCSS · Recharts (RTL فارسی)
**یکپارچه‌سازی:** Green API (واتس‌اپ) · OpenAI/DeepSeek/Gemini · Supabase (قیمت محصولات)

### سرویس‌های Docker

| سرویس | پورت (میزبان) | نقش |
|---|---|---|
| `frontend` | **3002** | داشبورد React (nginx) |
| `backend` | **8002** | API (FastAPI) |
| `worker` | — | اجرای کمپین‌ها (Celery) |
| `beat` | — | وظایف زمان‌بندی‌شده (Celery beat) |
| `db` | داخلی | PostgreSQL |
| `redis` | داخلی | صف + کش |

---

## راه‌اندازی سریع

```bash
git clone https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp.git
cd greenapiwhatsapp
cp .env.example .env      # سپس .env را ویرایش کنید (Green API، کلید(های) هوش مصنوعی، SUPABASE_ANON_KEY، WEBHOOK_BASE_URL)
docker compose up -d --build
```

پس از اجرا:

- **داشبورد:** <http://localhost:3002>
- **مستندات API:** <http://localhost:8002/docs>
- **بررسی سلامت:** <http://localhost:8002/health>

> **وب‌هوک:** برای دریافت رویدادها، `WEBHOOK_BASE_URL` باید عمومی باشد. در توسعه از [ngrok](https://ngrok.com/) استفاده کنید (`ngrok http 8002`) و آدرس را در `.env` قرار دهید؛ سپس `POST /api/v1/accounts/{id}/apply-settings` را صدا بزنید.

---

## اتصال حساب Green API

۱. در [green-api.com](https://green-api.com/) یک **Instance** بسازید (هر شماره = یک Instance).
۲. `idInstance` و `apiTokenInstance` را کپی کنید.
۳. با `POST /api/v1/accounts/` ثبت کنید (وب‌هوک خودکار تنظیم می‌شود).
۴. QR را از صفحه «حساب‌ها» با اپ واتس‌اپ آن شماره اسکن کنید.
۵. وضعیت را با `GET /api/v1/accounts/{id}/status` بررسی کنید (باید `authorized` باشد).

---

## توسعه و تست

```bash
# تست‌های بک‌اند
cd backend && pip install -r requirements.txt && pytest -q     # ۴۷ تست

# فرانت‌اند در حالت توسعه
cd frontend && npm install && npm run dev                      # http://localhost:5173
```

---

## نکات ضدمسدودی

- پیام‌ها با تأخیر تصادفی انسانی و فقط در پنجره ارسال ساعت تهران فرستاده می‌شوند (شب‌ها متوقف).
- حساب تازه: گرم‌سازی را فعال کنید — سقف ۵ پیام/روز تا روز هفتم و استوری روزانه در ۱۰:۰۰.
- شماره‌های لیست سیاه و بدون واتس‌اپ خودکار رد می‌شوند؛ ارسال «۱۱» توسط مخاطب = لغو اشتراک.
- نرخ **یلوکارت** را در پنل تحویلِ داشبورد پایش کنید؛ در صورت عبور از ۵۰٪ هشدار داده می‌شود.

---

## Ops: ngrok tunnel supervision

The webhook ingestion path depends on the ngrok tunnel to the reserved domain
`https://multidisciplinary-jeri-physiognomically.ngrok-free.dev → localhost:8002`.
To make an ngrok outage self-heal across crashes and reboots, ngrok runs as a
**Windows service** (supervised by the Windows Service Manager), not a hand-started
process.

- Tunnel definition lives in `%LOCALAPPDATA%\ngrok\ngrok.yml` (the `tunnels.afrakala`
  block). Committed template: [`ngrok.yml.example`](./ngrok.yml.example) (token redacted).
- Install / re-install (run once in an **admin** PowerShell):
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\install-ngrok-service.ps1`
- Manage: `ngrok service status` · `ngrok service start` · `ngrok service stop`.
- The service replaces the old `AfrakalaNgrokWatchdog` scheduled task (the installer
  removes it so two supervisors don't fight over the one reserved domain).

For a reboot to fully self-recover, Docker Desktop must also be set to start on login
(Settings → General → "Start Docker Desktop when you sign in").

---

**Stack:** FastAPI · PostgreSQL · Redis · Celery · React · Green API · OpenAI/DeepSeek/Gemini

</div>
