<div dir="rtl">

# افراکالا واتس‌اپ سندر 🟢

پلتفرم حرفه‌ای ارسال انبوه پیام واتس‌اپ مبتنی بر **Green API** — با مدیریت چند حساب، تولید پیام شخصی‌سازی‌شده با هوش مصنوعی، محدودسازی هوشمند نرخ ارسال بر اساس ساعات کاری ایران، و داشبورد مانیتورینگ زنده.

---

## ۱. معرفی پروژه

این سیستم برای ارسال کمپین‌های تبلیغاتی و اطلاع‌رسانی واتس‌اپ به‌صورت انبوه و ایمن طراحی شده است. ویژگی‌های اصلی:

- **مدیریت چند حساب**: هر شماره واتس‌اپ یک Instance در Green API است؛ ارسال به‌صورت چرخشی (Round-Robin) بین حساب‌های فعال تقسیم می‌شود.
- **تولید پیام با GPT**: هر پیام به‌صورت منحصربه‌فرد و شخصی‌سازی‌شده با نام مشتری توسط OpenAI تولید می‌شود تا از الگوهای تکراری (و در نتیجه مسدود شدن) جلوگیری شود.
- **محدودسازی نرخ زمان‌محور**: تعداد پیام مجاز در هر ساعت بر اساس ساعت تهران تنظیم می‌شود (شب‌ها ارسال متوقف است).
- **سقف روزانه هوشمند هر حساب**: بر اساس فرمول `روزهای فعال + پیام‌های دریافتی دیروز + پاسخ‌های سریع`.
- **ورود مخاطبین از اکسل**: با نرمال‌سازی خودکار شماره‌های ایرانی.
- **وب‌هوک دریافت پیام و تشخیص مسدودی**: پیام‌های ورودی ذخیره و تغییر وضعیت حساب‌ها (مسدود/قطع) به‌صورت آنی شناسایی می‌شود.
- **داشبورد مانیتورینگ زنده** با رابط فارسی راست‌به‌چپ.
- **پردازش پس‌زمینه** با Celery + Redis.

---

## ۲. پیش‌نیازها

- [Docker](https://www.docker.com/) و Docker Compose
- Python 3.11 (در صورت اجرای محلی بدون Docker)
- یک حساب [Green API](https://green-api.com/) با حداقل یک Instance
- کلید API از [OpenAI](https://platform.openai.com/) (برای تولید پیام با هوش مصنوعی)

---

## ۳. نصب و راه‌اندازی

```bash
# ۱) کلون کردن مخزن
git clone https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp.git
cd greenapiwhatsapp

# ۲) ساخت فایل تنظیمات از روی نمونه
cp .env.example .env
# سپس .env را ویرایش کنید و OPENAI_API_KEY و سایر مقادیر را وارد کنید

# ۳) اجرای کل سرویس‌ها
docker-compose up -d
```

پس از اجرا:

- **API و مستندات**: <http://localhost:8000/docs>
- **بررسی سلامت**: <http://localhost:8000/health>
- **داشبورد (React)**: رابط کاربری در پوشه `frontend/` به‌صورت یک اپ React + Vite ساخته شده است:

```bash
cd frontend
npm install
npm run dev        # روی http://localhost:5173
```

برای ساخت نسخه تولید: `npm run build` (خروجی در `frontend/dist/`). آدرس بک‌اند پیش‌فرض `http://localhost:8000/api/v1` است و با متغیر `VITE_API_BASE` قابل تغییر است (نمونه در `frontend/.env.example`).

داشبورد شامل صفحات: داشبورد زنده، حساب‌ها، کمپین‌ها، مخاطبین، صندوق ورودی، گروه‌ها، استوری‌ها، قالب‌ها و لیست سیاه — همگی با رابط فارسی راست‌به‌چپ.

### اجرای محلی برای توسعه (بدون Docker کامل)

```bash
# فقط دیتابیس و Redis را با Docker بالا بیاورید
docker-compose -f docker-compose.dev.yml up -d

cd backend
pip install -r requirements.txt

# اجرای سرور
uvicorn app.main:app --reload

# در ترمینال دیگر: اجرای Worker
celery -A app.workers.celery_app worker --loglevel=info

# در ترمینال سوم: اجرای زمان‌بند
celery -A app.workers.celery_app beat --loglevel=info
```

---

## ۴. راهنمای استفاده

۱. **افزودن حساب**: با `POST /api/v1/accounts/` و ارسال `name`، `instance_id` و `api_token`. وب‌هوک به‌صورت خودکار تنظیم می‌شود.
۲. **بررسی وضعیت حساب**: `GET /api/v1/accounts/{id}/status` — اتصال (authorized) را تأیید می‌کند.
۳. **ورود مخاطبین**: فایل اکسل را با `POST /api/v1/contacts/import` آپلود کنید. ستون‌ها می‌توانند فارسی یا انگلیسی باشند (`phone/شماره`، `first_name/نام`، ...).
۴. **ساخت کمپین**: `POST /api/v1/campaigns/` با تنظیم `use_gpt`، `gpt_prompt` یا `message_template`.
۵. **افزودن مخاطب به کمپین**: `POST /api/v1/campaigns/{id}/contacts` با لیست شناسه‌ها.
۶. **شروع/توقف کمپین**: `POST /api/v1/campaigns/{id}/start` و `/pause` و `/resume`.
۷. **پایش زنده**: داشبورد را باز کنید؛ هر ۱۰ ثانیه به‌روزرسانی می‌شود.

> **قالب پیام**: در حالت بدون GPT می‌توانید از متغیرهای `{{first_name}}` و `{{last_name}}` در `message_template` استفاده کنید.

---

## ۵. نقاط API

| متد | مسیر | توضیح |
|-----|------|-------|
| GET | `/health` | بررسی سلامت سرویس |
| GET | `/api/v1/accounts/` | لیست حساب‌ها |
| POST | `/api/v1/accounts/` | افزودن حساب (تنظیم خودکار وب‌هوک) |
| GET | `/api/v1/accounts/{id}/status` | بررسی وضعیت اتصال حساب |
| DELETE | `/api/v1/accounts/{id}` | حذف حساب |
| GET | `/api/v1/contacts/` | لیست/جستجوی مخاطبین |
| POST | `/api/v1/contacts/import` | ورود مخاطبین از اکسل |
| POST | `/api/v1/contacts/{id}/check-whatsapp` | بررسی داشتن واتس‌اپ |
| POST | `/api/v1/contacts/blacklist` | افزودن به لیست سیاه |
| GET | `/api/v1/campaigns/` | لیست کمپین‌ها |
| POST | `/api/v1/campaigns/` | ساخت کمپین |
| POST | `/api/v1/campaigns/{id}/contacts` | افزودن مخاطب به کمپین |
| POST | `/api/v1/campaigns/{id}/start` | شروع کمپین |
| POST | `/api/v1/campaigns/{id}/pause` | توقف کمپین |
| POST | `/api/v1/campaigns/{id}/resume` | ادامه کمپین |
| GET | `/api/v1/campaigns/{id}/progress` | پیشرفت کمپین |
| POST | `/api/v1/webhook/{instance_id}` | دریافت رویدادهای Green API |
| GET | `/api/v1/dashboard/stats` | آمار زنده داشبورد |
| GET | `/api/v1/blacklist/` | لیست سیاه |
| GET | `/api/v1/blacklist/inbox/recent` | آخرین پیام‌های دریافتی |

مستندات تعاملی کامل در <http://localhost:8000/docs> در دسترس است.

---

## ۶. مراحل اتصال Green API

1. در [green-api.com](https://green-api.com/) ثبت‌نام کنید و یک **Instance** بسازید (به ازای هر شماره واتس‌اپ یک Instance).
2. `idInstance` و `apiTokenInstance` را کپی کنید.
3. این مقادیر را با `POST /api/v1/accounts/` در سیستم ثبت کنید.
4. در پنل Green API، **QR Code** را با اپلیکیشن واتس‌اپ آن شماره اسکن کنید تا حساب متصل شود.
5. وضعیت را با `GET /api/v1/accounts/{id}/status` بررسی کنید؛ باید `authorized` باشد.

> **وب‌هوک عمومی**: برای اینکه Green API بتواند رویدادها را به سیستم شما ارسال کند، آدرس `WEBHOOK_BASE_URL` باید عمومی و در دسترس باشد. برای توسعه از [ngrok](https://ngrok.com/) استفاده کنید:
> ```bash
> ngrok http 8000
> ```
> سپس آدرس ngrok را در `.env` به‌عنوان `WEBHOOK_BASE_URL` قرار دهید.

> **سقف رایگان Green API**: ۲۰۰ پیام در روز. برای محیط تولید پلن پولی تهیه کنید.

---

## ۷. ساختار پروژه

```
greenapiwhatsapp/
├── backend/
│   ├── app/
│   │   ├── main.py            # نقطه ورود FastAPI
│   │   ├── config.py          # تنظیمات (pydantic-settings)
│   │   ├── database.py        # موتور Async SQLAlchemy
│   │   ├── models/            # مدل‌های دیتابیس (Account, Contact, Campaign, Inbox)
│   │   ├── schemas/           # اسکیماهای Pydantic
│   │   ├── api/v1/            # روترهای API
│   │   ├── services/          # Green API، GPT، قیمت‌ها، نرخ‌سنج، اکسل، اجرای کمپین
│   │   └── workers/           # Celery (تسک‌ها و زمان‌بند)
│   ├── migrations/            # Alembic
│   ├── tests/                 # تست‌های pytest
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic.ini
├── frontend/
│   └── index.html             # داشبورد مانیتورینگ
├── docker-compose.yml         # استقرار کامل
├── docker-compose.dev.yml     # فقط db + redis برای توسعه
├── .env.example
└── README.md
```

---

## ۸. اجرای تست‌ها

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

---

## ⚠️ نکات مهم

- پیام‌ها با تأخیر تصادفی انسانی (۴۵ تا ۱۱۰ ثانیه به‌صورت پیش‌فرض) ارسال می‌شوند تا از مسدود شدن جلوگیری شود.
- ارسال فقط در ساعات کاری تهران انجام می‌شود؛ شب‌ها به‌صورت خودکار متوقف است.
- شماره‌های لیست سیاه و شماره‌های بدون واتس‌اپ به‌صورت خودکار رد می‌شوند.
- مخاطبینی که عدد «۱۱» را ارسال کنند باید به لیست سیاه افزوده شوند (لغو اشتراک).

---

**Stack:** FastAPI · PostgreSQL · Redis · Celery · Green API · OpenAI

</div>
