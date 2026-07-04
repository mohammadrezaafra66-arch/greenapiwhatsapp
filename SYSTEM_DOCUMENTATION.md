# سند کامل سیستم افراکالا واتساپ سندر

**تاریخ:** 2026-07-04
**آخرین commit:** `9e70ff0` (fix: Groups page — member count, type filter, broadcast list support)
**Repository:** https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp

> این سند به‌صورت خودکار از روی کد واقعی پروژه تولید شده است (نه از روی فرض).
> Auto-generated from the actual codebase.

---

## ۱. خلاصه اجرایی (Executive Summary)

افراکالا واتساپ سندر یک سامانه‌ی بازاریابی و ارسال انبوه پیام واتساپ برای عمده‌فروشی لوازم خانگی است. سیستم چند حساب واتساپ (از طریق Green API) را مدیریت می‌کند، کمپین‌های هوشمند با تولید پیام توسط هوش مصنوعی (OpenAI / DeepSeek / Gemini با fallback خودکار) اجرا می‌کند، قیمت لحظه‌ای محصولات را از Supabase می‌خواند، و با رعایت محدودیت‌های ضدمسدودی (anti-ban) شامل زمان‌بندی ساعتی، تأخیر تصادفی و نشانگر «در حال تایپ» پیام‌ها را ارسال می‌کند. رابط کاربری کامل فارسی (RTL) با داشبورد زنده، صندوق ورودی، مدیریت گروه‌ها، و گزارش‌گیری روزانه ارائه می‌شود.

---

## ۲. معماری تکنیکال (Technical Architecture)

### Stack
- **Backend:** FastAPI 0.111 · Python 3.11 · SQLAlchemy 2.0 (async) · Pydantic 2.7
- **Frontend:** React 18.3 · Vite 5.3 · TailwindCSS 3.4 · React Router 6 · Recharts 2.15 · Axios (RTL Persian, dark theme)
- **Database:** PostgreSQL 15 (asyncpg 0.29)
- **Queue / Cache:** Redis 7 + Celery 5.4 (worker + beat)
- **WhatsApp:** Green API (instance `7105325764`)
- **AI:** OpenAI (gpt-4o-mini) → DeepSeek (deepseek-chat) → Gemini (gemini-2.0-flash) — چند‌ارائه‌دهنده با fallback
- **Products/Prices:** Supabase REST (self-hosted `http://192.168.170.10:8000`)

### Docker Services (docker-compose.yml)
| سرویس | Image / Build | پورت | نقش |
|---|---|---|---|
| `db` | postgres:15-alpine | داخلی | پایگاه داده |
| `redis` | redis:7-alpine | داخلی | broker صف + کش |
| `backend` | build ./backend | **8002→8000** | API (FastAPI/uvicorn) |
| `worker` | build ./backend | — | Celery worker (اجرای کمپین‌ها) |
| `beat` | build ./backend | — | Celery beat (وظایف زمان‌بندی‌شده) |
| `frontend` | build ./frontend (nginx) | **3002→80** | رابط کاربری |

مقادیر شمارشی کلیدی: **۱۳۱ endpoint** · **۲۶ جدول دیتابیس** · **۷۲ متد Green API** · **۸ وظیفه Celery** · **۱۸ صفحه فرانت‌اند** · **۱۴ سرویس بک‌اند**.

---

## ۳. دیتابیس — همه جداول (۲۶ جدول)

### `accounts`
**هدف:** حساب‌های واتساپ (هر ردیف = یک شماره/Instance مستقل Green API).
**ستون‌های اصلی:** instance_id, api_token, phone, status (active/banned/disconnected/pending), daily_limit, sent_today, received_today, days_active, warmup_enabled, polling_enabled, auto_reply_*, quota_exceeded_at, proxy_host/port/login/password/enabled, is_default.

### `contacts`
**هدف:** مخاطبین (شماره‌های مقصد).
**ستون‌ها:** phone (نرمال‌شده 98…), first_name, last_name, province, city, segment, has_whatsapp, blacklisted, blacklist_reason, source.

### `campaigns`
**هدف:** کمپین‌های ارسال پیام (گروه پیام).
**ستون‌ها:** name, status (draft/running/paused/completed), campaign_type (text/image/poll/interactive_buttons/status), use_gpt, gpt_prompt, message_template, include_products, product_count, campaign_scope (pv/group), group_ids, pause_reason, description, is_active, append_date, append_seller_name/phone, seller_name/phone/phone2, emoji_level, contact_group_id, wa_collection_id, product_label_filter, is_always_on.

### `campaign_contacts`
**هدف:** رابطه‌ی کمپین↔مخاطب + وضعیت ارسال هر پیام.
**ستون‌ها:** campaign_id, contact_id, account_id, status (pending/generating/sent/failed/skipped/no_whatsapp), generated_message, green_api_message_id, delivery_status, error_message, retry_count, sent_at.

### `hour_rate_limits`
**هدف:** جدول سقف ارسال ساعتی سراسری (fallback).

### `account_hour_schedules`
**هدف:** زمان‌بندی ساعتی هر حساب (override سراسری).
**ستون‌ها:** account_id, hour_start, hour_end, max_per_hour, gpt_prompt, message_template, is_active, include_products.

### `account_send_configs`
**هدف:** تأخیر ارسال per-account (min/max ثانیه).

### `keyword_rules`
**هدف:** قوانین پاسخ خودکار بر اساس کلیدواژه.
**ستون‌ها:** account_id, keyword, reply_message, match_type (exact/contains), scope (pv/group/both), is_active, use_count.

### `inbox_messages`
**هدف:** پیام‌های ورودی/رویدادهای دریافتی (webhook).
**ستون‌ها:** instance_id, sender_phone/name, message_type, text_content, is_group, category, auto_replied, call_status, button_reply_id/title, poll_votes, is_deleted, edited_text, original_payload.

### `blacklist`
**هدف:** لیست سیاه شماره‌ها (لغو اشتراک / بلاک).

### `message_templates`
**هدف:** قالب‌های آماده پیام.

### `whatsapp_groups`
**هدف:** گروه‌ها/لیست‌های انتشار واتساپ همگام‌شده.
**ستون‌ها:** green_group_id, account_id, name, description, chat_type (group/broadcast/community), member_count.

### `status_sends`
**هدف:** لاگ ارسال استوری (status).

### `chat_journals`
**هدف:** ژورنال تاریخچه پیام (fetch از Green API).

### `uploaded_files`
**هدف:** فایل‌های آپلودشده به فضای Green API.

### `ai_usage_logs`
**هدف:** لاگ مصرف توکن هوش مصنوعی per-provider.
**ستون‌ها:** provider, model, prompt_tokens, completion_tokens, total_tokens, success, error_text, used_at.

### `contact_groups` / `contact_group_members`
**هدف:** گروه‌بندی مجازی مخاطبین (با رنگ) و اعضای آن.

### `wa_group_collections` / `wa_group_collection_members`
**هدف:** مجموعه‌ی مجازی از چند گروه واتساپ برای هدف‌گیری کمپین گروهی.

### `emergency_contacts`
**هدف:** شماره‌های اضطراری/هشدار.

### `report_subscribers`
**هدف:** گیرندگان گزارش شبانه.

### `daily_send_logs`
**هدف:** لاگ تفصیلی هر پیام ارسالی روزانه (برای گزارش شبانه).

### `product_mention_logs`
**هدف:** رصد ذکر محصولات افراکالا در پیام‌های گروه‌ها (پاک‌سازی خودکار هر ۲ روز).

### `disappearing_chat_settings`
**هدف:** تنظیم پیام‌های ناپدیدشونده per-chat (ephemeral).

### `wa_blocked_contacts`
**هدف:** مخاطبین بلاک‌شده توسط حساب واتساپ (همگام از Green API).

---

## ۴. API Endpoints — کامل (۱۳۱ endpoint)

### حساب‌ها (`/api/v1/accounts`)
- `GET /` — لیست حساب‌ها
- `POST /` — افزودن حساب (و ثبت webhook)
- `GET /{id}/status` — وضعیت زنده (getStateInstance)
- `GET /{id}/qr` — کد QR (فقط در حالت qrCode)
- `POST /{id}/reboot` · `POST /{id}/logout`
- `POST /{id}/apply-settings` — بازتنظیم webhook (همه انواع) + delay 15000ms + proxy
- `PUT /{id}/proxy` · `GET /{id}/proxy` — مدیریت پروکسی SOCKS5
- `GET /{id}/blocked-contacts` — لیست بلاک‌شده‌ها + sync
- `POST /{id}/set-default` — تعیین حساب پیش‌فرض
- `POST /{id}/check-whatsapp-bulk` — بررسی گروهی واتساپ‌دار بودن
- `PUT /{id}/auto-reply` — تنظیم پاسخ خودکار/warmup/polling
- `GET /{id}/queue` · `DELETE /{id}/queue` — صف ارسال
- `POST /{id}/send-typing` · `POST /{id}/messages/{msg}/edit` · `DELETE /{id}/messages/{msg}`
- `POST /{id}/contacts/add` — افزودن به فون‌بوک · `POST /{id}/token/refresh` · `DELETE /{id}`

### کمپین‌ها (`/api/v1/campaigns`)
- `GET /` · `GET /{id}` · `PUT /{id}` · `POST /` · `DELETE /{id}`
- `POST /{id}/toggle-active` — فعال/غیرفعال
- `POST /{id}/contacts` — افزودن مخاطب · `GET /{id}/contacts` — لیست + خطاها
- `POST /{id}/start` · `POST /{id}/pause` · `POST /{id}/resume` · `POST /{id}/test`
- `GET /{id}/progress` — پیشرفت زنده + pause_reason

### مخاطبین (`/api/v1/contacts`)
- `GET /` · `POST /` (افزودن دستی) · `POST /import` (اکسل) · `POST /check-bulk` · `DELETE /{id}`
- `GET /{id}/history` · `POST /{id}/send-file` · `POST /{id}/archive` · `POST /{id}/unarchive` · `POST /{id}/blacklist`
- `POST /{id}/disappearing` — پیام ناپدیدشونده · `POST /{id}/add-to-phonebook` · `PUT /{id}/phonebook`

### Webhook (`/api/v1/webhook`)
- `POST /{instance_id}` — دریافت رویدادهای Green API (پیام ورودی، وضعیت خروجی، تماس، پاسخ دکمه، رأی نظرسنجی، quota، device، catalog، block، تماس خروجی)

### داشبورد و هوش مصنوعی (`/api/v1/dashboard`)
- `GET /stats` — آمار زنده · `GET /rate-limits` · `PUT /rate-limits`
- `GET /product-mentions/recent` — رصد محصولات
- `GET /ai-stats` — مصرف توکن per-provider · `GET /ai-providers` — ارائه‌دهنده‌های پیکربندی‌شده

### صندوق ورودی (`/api/v1/inbox`)
- `GET /` · `GET /stats` · `POST /{msg}/read` · `POST /reply`

### گروه‌ها (`/api/v1/groups`)
- `GET /` (فیلتر: account_id, chat_type, min_members) · `POST /` · `GET /{id}/info`
- `POST /sync/{account_id}` — همگام‌سازی (تشخیص نوع + تعداد اعضا) · `POST /{id}/refresh-members`
- `POST /{id}/members` · `DELETE /{id}/members/{phone}` · `POST /{id}/send`
- `PUT /{id}/name` · `POST /{id}/admin/{phone}` · `DELETE /{id}/admin/{phone}` · `POST /{id}/leave`

### استوری‌ها (`/api/v1/statuses`)
- `POST /text` · `POST /image` · `POST /voice` · `DELETE /{msg}` · `GET /incoming/{account_id}` · `GET /{msg}/stats`

### قالب‌ها (`/api/v1/templates`)
- `GET /` · `POST /` · `POST /{id}/use` · `DELETE /{id}`

### لیست سیاه (`/api/v1/blacklist`)
- `GET /` · `POST /` · `DELETE /{phone}` · `GET /inbox/recent`

### زمان‌بندی حساب (`/api/v1/account-schedules`)
- `GET /presets` — ۶ پیش‌نویس آماده · `POST /{slot}/apply-preset`
- `GET /{account_id}` · `POST /` · `PUT /{slot}` · `DELETE /{slot}` · `PUT /{account_id}/delay`

### کلیدواژه‌ها (`/api/v1/keyword-rules`)
- `GET /` · `POST /` · `PUT /{id}` · `DELETE /{id}`

### گروه مخاطبین (`/api/v1/contact-groups`)
- `GET /` · `POST /` · `PUT /{id}` · `DELETE /{id}` · `POST /{id}/members` · `DELETE /{id}/members/{contact}` · `GET /{id}/contacts`

### مجموعه گروه‌های واتساپ (`/api/v1/wa-collections`)
- `GET /available-groups/{account_id}` — گروه‌های همگام‌شده برای انتخاب
- `GET /` · `POST /` · `PUT /{id}` · `DELETE /{id}` · `POST /{id}/groups` · `DELETE /{id}/groups/{chat_id}` · `GET /{id}/groups`

### گزارش‌ها (`/api/v1/reporting`)
- `GET/POST/DELETE /emergency-contacts` · `GET/POST/DELETE /subscribers`
- `GET /daily-logs` · `GET/DELETE /product-mentions` · `GET /products` · `GET /product-labels`

### ژورنال (`/api/v1/journals`)
- `GET /{id}/incoming` · `GET /{id}/outgoing` · `GET /{id}/chats` · `POST /{id}/download-file` · `GET /{id}/queue-count` · `DELETE /{id}/webhooks-queue`

### فایل‌ها (`/api/v1/files`)
- `POST /upload/{account_id}` · `GET /list/{account_id}`

### صف (`/api/v1/queue`)
- `GET /{account_id}` · `DELETE /{account_id}`

**مجموع کل endpoint‌ها: ۱۳۱**

---

## ۵. Green API — متدهای پیاده‌شده (۷۲ متد در `green_api.py`)

### ارسال (Sending)
`send_message` · `send_image` · `send_file_url` · `send_file_upload` · `send_poll` · `send_location` · `send_contact` · `send_interactive_buttons` · `forward_messages` · `send_group_message` · `send_typing` · `edit_message` · `delete_message` · `upload_file`

### دریافت (Receiving)
`receive_notification` · `delete_notification` · `download_file` · `get_message` · `last_incoming_messages` · `last_outgoing_messages` · `get_chats` · `get_webhooks_count` · `clear_webhooks_queue`

### حساب (Account)
`get_state` · `get_settings` · `set_settings` · `set_webhook` (فعال‌سازی همه انواع notification) · `reboot` · `logout` · `get_qr` · `get_qr_info` · `get_auth_code` · `get_wa_settings` · `set_profile_picture` · `update_api_token` · `set_proxy` · `remove_proxy` · `get_proxy`

### گروه (Group)
`create_group` · `add_group_participant` · `remove_group_participant` · `get_group_data` · `update_group_name` · `set_group_admin` · `remove_group_admin` · `leave_group` · `set_group_picture`

### استوری (Status)
`send_status_text` · `send_status_image` · `get_status_statistics` · `send_voice_status` · `delete_status` · `get_incoming_statuses` · `get_outgoing_statuses`

### مخاطب/سرویس (Contacts & Service)
`check_whatsapp` · `get_avatar` · `get_contacts` · `get_contact_info` · `get_chat_history` · `mark_as_read` · `archive_chat` · `unarchive_chat` · `get_contacts_block` · `add_contact` · `edit_contact` · `delete_contact` · `set_disappearing_chat`

### صف (Queue)
`show_messages_queue` · `clear_messages_queue` · `get_messages_count`

**مجموع: ۷۲ متد async** (شامل چند helper خصوصی مانند `_get`/`_post`/`_chat_id`/`_normalize`).

---

## ۶. Celery Tasks (وظایف پس‌زمینه — ۸ وظیفه)

| Task | کار | زمان‌بندی |
|---|---|---|
| `tasks.run_campaign` | اجرای کمپین PV (round-robin بین حساب‌ها، رعایت پنجره ارسال) | on-demand |
| `tasks.run_group_campaign` | اجرای کمپین گروهی (ارسال به group_ids) | on-demand |
| `tasks.poll_accounts` | polling دریافت پیام برای حساب‌های polling_enabled | هر ۱۰ ثانیه |
| `tasks.sync_account_states` | همگام‌سازی وضعیت حساب‌ها با Green API | هر ۵ دقیقه |
| `tasks.warmup_accounts` | گرم‌سازی حساب‌ها (ارسال استوری روزانه) | هر ۱ ساعت |
| `tasks.reset_daily_counters` | صفر کردن شمارنده‌های روزانه | هر ۲۴ ساعت |
| `tasks.clear_old_product_mentions` | پاک‌سازی رصد محصولات قدیمی‌تر از ۲ روز | هر ۲۴ ساعت |
| `tasks.send_night_report` | ارسال گزارش شبانه واتساپ به مشترکین | **کرون ۲۳:۰۰ تهران** |

> نکته فنی: موتور async با `NullPool` پیکربندی شده تا با اجرای هر task در event-loop جدید (Celery prefork) سازگار باشد و خطای asyncpg «another operation in progress» رخ ندهد.

---

## ۷. صفحات فرانت‌اند (۱۸ صفحه)

منوی جمع‌شونده در ۵ دسته سازمان‌دهی شده است: **داشبورد · ارسال پیام · مخاطبین · حساب‌ها · ابزارها · گزارش‌ها**.

- **`/` داشبورد زنده** — polling هر ۵ ثانیه؛ KPI با انیمیشن شمارش، نمودار BarChart (ارسال per-account) و PieChart (وضعیت حساب‌ها)، پنل نرخ ارسال با نوار ۲۴ ساعته، صندوق ورودی، مصرف هوش مصنوعی، کارت‌های per-account، بنر اخطار حساب مسدود/سقف.
- **`/accounts` حساب‌ها** — لیست حساب‌ها، QR، ری‌بوت، بررسی وضعیت، پروکسی SOCKS5، تعیین پیش‌فرض، همگام‌سازی بلاک‌شده‌ها، افزودن حساب (راهنمای گام‌به‌گام).
- **`/account-schedules` زمان‌بندی ارسال** — بازه‌های ساعتی per-account، تأخیر ارسال، ۶ پیش‌نویس آماده GPT، چک‌باکس «افزودن محصولات».
- **`/campaigns` گروه‌های پیام** — ساخت/ویرایش/فعال‌سازی کمپین، انتخاب نوع، امضای فروشنده، تاریخ شمسی، سطح ایموجی، فیلتر برچسب محصول، پنل گزارش زنده خطاها.
- **`/contacts` مخاطبین** — لیست/جستجو، ورود اکسل، افزودن دستی، بررسی واتساپ، افزودن به کمپین/گروه، پیام ناپدیدشونده، افزودن به فون‌بوک.
- **`/contact-groups` گروه مخاطبین** — گروه‌بندی مجازی رنگی، مدیریت اعضا.
- **`/wa-collections` مجموعه گروه‌های واتساپ** — مجموعه گروه‌ها؛ همگام‌سازی و انتخاب چک‌باکسی گروه‌های واتساپ.
- **`/groups` گروه‌های واتساپ** — همگام‌سازی، فیلتر نوع (گروه/انتشار) و تعداد اعضا، جستجو، تعداد اعضا برجسته، refresh per-group.
- **`/inbox` صندوق ورودی** — پیام‌های ورودی، فیلتر دسته/نوع، پاسخ، نمایش تماس/دکمه/نظرسنجی.
- **`/blacklist` لیست سیاه** — مدیریت شماره‌های مسدود.
- **`/keyword-rules` پاسخ خودکار** — قوانین کلیدواژه (دقیق/شامل، خصوصی/گروه/هردو).
- **`/templates` قالب‌های پیام** — قالب‌های آماده.
- **`/statuses` استوری‌ها** — ارسال استوری متنی/تصویری/صوتی.
- **`/files` فایل‌ها** — آپلود فایل و استفاده در کمپین.
- **`/journals` تاریخچه پیام‌ها** — پیام‌های ورودی/خروجی/چت‌ها از Green API + شمارش صف.
- **`/ai-settings` هوش مصنوعی** — وضعیت ۳ ارائه‌دهنده، اولویت، آمار مصرف زنده.
- **`/reporting` گزارش‌ها** — شماره‌های اضطراری، گیرندگان گزارش شبانه، لاگ روزانه، رصد محصولات.
- **`/products` رصد محصولات** — لیست محصولات با قیمت + ذکرها در گروه‌ها.

---

## ۸. ویژگی‌های کامل سیستم

### مدیریت حساب‌های واتساپ
- چند حساب همزمان؛ ارسال round-robin بین حساب‌های فعال · QR/pairing · ری‌بوت/logout · حساب پیش‌فرض · پروکسی SOCKS5 per-account · refresh توکن API.

### کمپین‌ها و ارسال
- انواع: متنی/تصویری/نظرسنجی/دکمه‌ای/استوری · هدف PV یا گروه · گروه مخاطبین و مجموعه گروه‌ها · امضای فروشنده (نام + ۲ شماره) · تاریخ شمسی (jdatetime) · سطح ایموجی · فیلتر محصول با برچسب · تست تک‌پیام · پنل خطای زنده.

### هوش مصنوعی
- سه ارائه‌دهنده با fallback خودکار (OpenAI→DeepSeek→Gemini) · fallback نهایی قالب فارسی · دسته‌بندی پیام ورودی · لاگ و نمایش مصرف توکن · دستور GPT per-hour.

### زمان‌بندی و نرخ ارسال (Anti-ban)
- پنجره ارسال ۰۸:۰۰–۲۲:۰۰ تهران (سراسری) با override per-account · سقف ساعتی افزایشی · تأخیر تصادفی per-account · نشانگر «در حال تایپ» · توقف خودکار و زمان‌بندی مجدد خارج از پنجره · limit روزانه محاسبه‌شده از warmup.

### دریافت و پاسخ
- webhook همه رویدادها (ورودی، وضعیت خروجی، تماس، دکمه، نظرسنجی، block، device، catalog) · پاسخ خودکار · پاسخ کلیدواژه (با اسکوپ صحیح گروه) · بلاک خودکار در صورت لغو/block · ژورنال Green API.

### گروه‌ها
- همگام‌سازی گروه‌ها/لیست‌های انتشار با تشخیص نوع و تعداد اعضا · فیلتر و جستجو · ارسال به گروه/مجموعه.

### گزارش‌گیری
- داشبورد زنده · گزارش شبانه خودکار واتساپ (۲۳:۰۰) · لاگ تفصیلی روزانه · رصد ذکر محصولات در گروه‌ها · مصرف هوش مصنوعی.

### امنیت و anti-ban
- نرمال‌سازی شماره · لیست سیاه · warmup تدریجی · تأخیر و typing · پروکسی · delaySendMessagesMilliseconds=15000.

---

## ۹. محدودیت‌های شناخته‌شده (Known Limitations)

- **کانال‌های واتساپ (`@newsletter`)** پشتیبانی نمی‌شوند (فقط owner می‌تواند پست کند) — در sync رد می‌شوند.
- **`getContactsBlock`** روی instance فعلی خطای Green API برمی‌گرداند (endpoint به‌صورت graceful خطا را گزارش می‌کند نه ۵۰۰).
- **قیمت محصولات** وابسته به view عمومی `product_computed_prices_public` در Supabase self-hosted است؛ در نبود آن نام محصول نمایش داده می‌شود و قیمت «تماس بگیرید».
- **URL webhook (ngrok)** با هر ری‌استارت تانل تغییر می‌کند؛ باید `WEBHOOK_BASE_URL` به‌روز و `apply-settings` دوباره اجرا شود.
- **پیام‌های `yellowCard`** — Green API برخی ارسال‌ها را مشکوک علامت می‌زند که ممکن است تحویل را کند/متوقف کند.
- **همگام‌سازی مجدد گروه‌ها** برای تعداد بالا (۵۰۰+) کند است چون به‌ازای هر گروه یک `getGroupData` صدا می‌زند (مشمول rate-limit).
- کلید anon سوپابیس (کلید public سمت کلاینت) در `config.py` به‌عنوان default قرار دارد.

---

## ۱۰. نسخه‌بندی (Git History — ۲۰ commit آخر)

```
9e70ff0 fix: Groups page — member count, type filter, broadcast list support
3a3b802 feat: V7 — per-hour presets, group search, wa-collections fix, multi-account UX
b849bb8 feat: V6 — complete remaining Green API features
6364a3f feat(green-api): enable all notification webhook types in set_webhook
ea63a80 feat: V5 — 27 new features
0824ed4 chore: point WEBHOOK_BASE_URL at live ngrok tunnel
9123ecc feat(accounts): add apply-settings endpoint to re-push Green API settings
7e8467f feat(green-api): raise queue send delay to 15000ms
300d5e3 feat(ui): add helpful Persian guidance across key pages
59708d7 feat(campaigns): add product_count input when including daily products
457a51e fix(pricing): read prices from product_computed_prices_public view
c662b0b feat(pricing): point product source at self-hosted Supabase
669f2fe chore(ui): simplify Persian labels to everyday language + verify API wiring
0f21543 fix(journals): correct Green API query-string URL + graceful upstream errors
dcd237d feat: multi-provider AI (OpenAI+DeepSeek+Gemini) with fallback + token tracking
003af6b feat(dashboard): real-time monitoring dashboard with charts
5615283 fix(campaigns): account-aware send window instead of global 08:00
5ee1462 fix(qr): only return base64 when Green API is in qrCode state
8d330e2 feat(campaigns): auto-pause with reason + self-reschedule outside send window
cf3b508 fix(campaigns): unblock stuck 'running' campaign + live error panel
```

**نقشه راه نسخه‌ها:** V1–V2 (پایه) → V3 (زمان‌بندی/کمپین گروهی/کلیدواژه) → V4 (پوشش کامل Green API) → V5 (۲۷ ویژگی: گروه مخاطبین، گزارش شبانه، رصد محصولات) → V6 (پروکسی، ناپدیدشونده، فون‌بوک، بلاک) → V7 (پیش‌نویس ساعتی، جستجو، UX چند‌حسابی) → Groups Fix.
