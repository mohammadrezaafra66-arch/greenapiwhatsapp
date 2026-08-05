# گزارش جامع مأموریت تکمیل Phase 7 (میان‌دوره‌ای — Session 2 Day 0)

این گزارش به زبان فارسی و به‌صورت روایت مهندسی نوشته شده است. پذیرش نهایی Phase 7 در این لحظه اعلام نمی‌شود.

## 1. چه چیزی قبل از شروع اشتباه بود

پیاده‌سازی Phase 7، ممیزی 7.1، پیش‌پرواز 7.2 و فعال‌سازی کنترل‌شده 7.3 انجام شده بود و Day 0 Session 1 رسماً شروع شده بود. اما داده‌های زندهٔ ENV-A بعداً با واقعیت اسناد هم‌خوان نبود: `fleet_accounts` و `fleet_shadow_snapshots` و حتی `fleet_policies` صفر شده بودند، در حالی که پرچم‌های Shadow روشن مانده بودند. یعنی پنجرهٔ مشاهده از نظر یکپارچگی داده شکسته بود و Phase 7 قابل پذیرش نبود.

## 2. چرا Observation نامعتبر شد

علت ریشه‌ای این بود که تست‌های round-trip مهاجرت Alembic داخل کانتینر Backend روی همان `SYNC_DATABASE_URL` زندهٔ ENV-A (`whatsapp_sender`) اجرا می‌شدند. دستور downgrade جدول‌های `fleet_*` را حذف و upgrade آن‌ها را خالی بازسازی کرد. شواهد زمانی فایل‌های heap حدود UTC 18:16 تا 18:17 و تیک‌های بعدی با `processed: 0` این موضوع را تأیید می‌کند. این یک نقص جداسازی محیط تست از پایگاه مشاهده است، نه خطای خود موتور Shadow.

## 3. چگونه ایزوله کردن تست مهاجرت پیاده‌سازی شد

پایگاه یکبارمصرف `whatsapp_sender_migtest` اضافه شد. همهٔ تست‌های مهاجرت Phase 2 تا 5 و roundtrip Phase 7 فقط به آن وصل می‌شوند. لایهٔ محافظ `migration_db_guard` اگر هدف `whatsapp_sender` باشد فوراً شکست می‌خورد. در `migrations/env.py` هم downgrade روی ENV-A بدون `V67_ALLOW_ENV_A_ALEMBIC_DOWNGRADE=1` ممنوع شد. تست‌های نگهبان اثبات می‌کنند CLI downgrade روی ENV-A fail-closed است. پس از اجرای این تست‌ها ENV-A آسیب ندید.

## 4. چگونه بازیابی انجام شد

ابتدا Session 1 به‌عنوان INVALID بایگانی شد. Scheduler موقتاً خاموش شد تا بازیابی بدون مسابقه با تیک دوره‌ای انجام شود. سپس فقط متادیتای V67 از مسیرهای تأییدشده بازسازی شد. به accounts، campaigns و incidents دست زده نشد؛ شمار آن‌ها 26 / 3 / 11 ماند.

## 5. چگونه متادیتا بازسازی شد

از `python -m app.scripts.fleet_seed` استفاده شد. Policy پیش‌فرض CONSERVATIVE با مکانیزم seed تأییدشده ایجاد شد. هیچ SQL دستی برای درج FleetAccount یا Policy اجرا نشد. اعمال دوبارهٔ seed برابر `skipped=1` بود و تکراری نساخت.

## 6. چگونه Stage A دوباره ساخته شد

همان حساب ماسک‌شدهٔ `b12dbd81` پس از بررسی وضعیت active، نبودن حادثهٔ باز، و sent_today=0 دوباره انتخاب شد. dry-run حالت `INBOUND_BUILDING` با دلیل `activity_inbound_only` را نشان داد؛ بدون CAMPAIGN_READY، بدون MATURE، cutover=false. پس از apply یک FleetAccount با version=1 ثبت شد. Gate A dry-run و Gate B persist و retry تکراری مطابق معماری اجرا شد.

## 7. چگونه Session 2 شروع شد

پس از Gate B، Scheduler دوباره روشن شد. اولین snapshot موفق با منبع `CELERY_PERIODIC` در UTC `2026-08-05 19:13:46.331651` با run_id `9197e53f-4a25-404f-92b8-ad8a8d5e6acf` ثبت شد. این لحظه شروع رسمی Session 2 / DAY 0 است. Session 1 بازنویسی یا backdate نشد.

## 8. چه در هر روز مشاهده رخ داد

تا این گزارش فقط Day 0 Session 2 آغاز شده است. هنوز هیچ روز کامل UTC معتبری سپری نشده است. روزهای Session 1 شمارش نمی‌شوند. ساختن یا فشرده‌سازی ۱۴ روز ممنوع است و انجام نشده است.

## 9. شواهد جمع‌آوری‌شده در هر روز

برای Day 0 Session 2: یک ردیف CLI Gate B و حداقل یک ردیف CELERY_PERIODIC با `simulation_only=true`، `executes=false`، `mutates_runtime=false`، mismatch کلاس `RUNTIME_UNKNOWN`، severity `HIGH`، threshold `UNRATIFIED`. گزارش روزانهٔ CLI برای تاریخ UTC 2026-08-05 دو snapshot و یک account covered را نشان داد و یادآوری کرد snapshotهای دستی به‌تنهایی روز مشاهده نیستند.

## 10. مشکلات مواجهه‌شده

Session 1 به‌خاطر تست مهاجرت روی ENV-A از بین رفت. ویرایش `.env` در PowerShell یک‌بار به‌خاطر quoting شکست خورد و با اسکریپت فایل اصلاح شد. اولین تلاش تست مهاجرت روی migtest به‌خاطر `create_all` بدون قیدهای Alembic یک assertion را شکست؛ با reset جدول‌های additive و stamp از baseline برطرف شد.

## 11. اصلاحات اعمال‌شده

ایزوله‌سازی migtest، گارد downgrade، بازنویسی تست‌های مهاجرت، بایگانی Session 1، بازیابی seed، Gate A/B، شروع Session 2، و اسناد `104` تا `108`.

## 12. نتایج Regression

نگهبان و مهاجرت و بخش Shadow: حداقل ۲۴ تست هدفمند پاس شد؛ سری مهاجرت ایزوله ۱۲ از ۱۲ پاس شد. `send_gate.py` در diff بدون تغییر بود. Alembic head روی ENV-A همچنان `v67_07_fleet_shadow_snapshots` است. `cutover_true=0`.

## 13. عملکرد

تیک Session 2 حدود ۰.۳۵ ثانیه طول کشید و `processed=1` بود. نشانه‌ای از storm یا catch-up دیده نشد. فاصلهٔ زمان‌بندی همچنان ۳۰۰ ثانیه است.

## 14. امنیت

توکن اپراتور Shadow فقط Backend است و در این گزارش مقدار آن چاپ نشده است. نقش از تنظیمات سرور می‌آید نه از هدر کلاینت. Downgrade ENV-A بدون اجازهٔ صریح ممکن نیست. API Shadow همچنان نیازمند احراز هویت است.

## 15. انطباق Green API

مسیر Shadow ارسال Green API ندارد؛ تست‌ها و بازرسی کد این را حفظ می‌کنند. هیچ حلقهٔ مصنوعی پیام از Shadow ساخته نشد. Mesh WRAP خارج از مسیر Shadow باقی است.

## 16. انطباق معماری

Shadow فقط مشاهده است. Journey فقط preview/compare. Eligibility توصیه‌ای است. Cutover false است. Canary و Human Contacts معوق‌اند. تصمیمات D-P7 و D-SE رعایت شده‌اند، با این قید که ۱۴ روز معتبر هنوز طی نشده است.

## 17. اثبات Runtime

پرچم‌ها پس از شروع Session 2: runtime=true و scheduler=true. Worker تیک `tasks.fleet_shadow_tick` را دریافت و با persist واقعی کامل کرد. لاگ `shadow_run_complete` با منبع CELERY_PERIODIC موجود است.

## 18. اثبات نبود ارسال زنده

خروجی تیک و snapshotها `executes=false` و `mutates_runtime=false` و `simulation_only=true` هستند. Seed و Shadow CLI مسیر send را صدا نمی‌زنند. `send_gate` تغییر نکرده است.

## 19. اثبات Cutover خاموش

FleetAccount با cutover=false ایجاد شد؛ شمارش `cutover_true=0` است؛ Shadow در صورت cutover=true رد می‌کند.

## 20. اثبات Human Contacts خاموش

هیچ پیاده‌سازی Human/Native Contacts در این مأموریت اضافه نشد؛ سند آمادگی مربوطه همچنان not started است.

## 21. اثبات Canary خاموش

Canary پیاده‌سازی یا فعال نشد؛ طبق D-P7-06 معوق است.

## 22. اثبات تغییر نکردن send_gate

`git diff --stat -- backend/app/services/send_gate.py` خالی بود.

## 23. اثبات اینکه تست مهاجرت دیگر ENV-A را خراب نمی‌کند

تست‌ها فقط به `whatsapp_sender_migtest` می‌روند؛ گارد هدف ENV-A را رد می‌کند؛ Alembic downgrade روی ENV-A بدون override شکست می‌خورد؛ پس از اجرای تست‌های مهاجرت، شمارنده‌های ENV-A آسیب ندیدند و بعداً بازیابی کنترل‌شده جداگانه انجام شد.

## 24. تاریخچهٔ Commit

شاخه: `feature/v67-autonomous-fleet-manager`

- `d33e1f1` — `fix(v67): isolate alembic migration tests from ENV-A`
- `191dcb4` — `docs(v67): archive session 1 and record session 2 day 0`

پیش از این مأموریت، آخرین commit عملیاتی Session 1: `7700970`. این دو commit هنوز روی origin push نشده‌اند مگر مالک دستور دهد.

## 25. فایل‌های تغییر یافته

از جمله: `migration_db_guard.py`، `migrations/env.py`، `tests/migration_test_db.py`، تست‌های مهاجرت Phase 2–5 و Phase 7، `test_v67_migration_db_guard.py`، اسناد `104` تا `108` و به‌روزرسانی `75`.

## 26. Migrations

هیچ migration طرحی جدید برای بازیابی داده لازم نبود. Head همان `v67_07_fleet_shadow_snapshots` ماند. بازیابی داده از seed تأییدشده بود نه از SQL خام.

## 27. تغییرات پیکربندی

پرچم‌های `.env` برای بازیابی موقتاً scheduler=false و سپس برای Session 2 دوباره true شدند؛ runtime true ماند؛ توکن اپراتور set باقی ماند. مقادیر Secret در git نیست.

## 28. Feature flags

پیش‌فرض کد همچنان false است. روی ENV-A برای Session 2 هر دو پرچم true هستند. Persistence Shadow فعال است. Threshold UNRATIFIED است.

## 29. بدهی فنی باقی‌مانده

باید ۱۴ روز متوالی معتبر UTC واقعاً سپری شود. `RUNTIME_UNKNOWN` به‌خاطر `live_state_missing` فعلاً غالب است و نیاز به پایش روزانه دارد. سند قدیمی `49` هنوز با وضعیت عملیات هم‌تراز کامل نیست. مفهوم Observation Session فقط در اسناد عملیاتی آمده و مدل DB جدا ندارد. Human Contacts و Canary بیرون از Phase 7 مانده‌اند.

## 30. درس‌ها

هرگز تست مخرب schema را روی پایگاه مشاهدهٔ PRODUCTION_LIKE اجرا نکنید. Observation DB و Migration Test DB باید از روز اول جدا باشند. پس از هر suite کامل، شمارنده‌های cohort/shadow باید دوباره تأیید شوند. Day 0 تاریخی با دادهٔ زنده‌ای که بعداً پاک شده برای پذیرش کافی نیست.

## 31. ارزیابی نهایی معماری

معماری Shadow برای مشاهده درست است و مسیر خطرناک send/cutover/canary باز نشده است. شکست Session 1 از جنس عملیات/تست بود نه انحراف محصولی Shadow. با ایزوله‌سازی، همان معماری اکنون برای ادامهٔ مشاهده قابل دفاع است.

## 32. آیا Phase 7 پذیرفته شده است؟

خیر.

Phase 7 هنوز کاملاً پذیرفته نیست، چون:

1. ۱۴ روز متوالی معتبر Session 2 سپری نشده است.
2. ممیزی تکمیل پس از ۱۴ روز هنوز اجرا نشده است.
3. ساختن یا فشرده‌سازی روزها ممنوع است و انجام نشده است.

وضعیت صادقانهٔ فعلی:

`SESSION 2 / DAY 0 / WINDOW STARTED — PHASE 7 NOT FULLY ACCEPTED`

هویت Master Phase 8 = Graduation / Maintenance حفظ شده است (`109`). Remap به Shadow Bridge رد شده است. اجرای موازی Phase 8 در طول Session 2 ممنوع است. Gapهای تشخیصی فقط در `110` فهرست شده‌اند و پیاده‌سازی نشده‌اند.

Phase 8 Graduation/Maintenance شروع نشده است. شروع آن تنها پس از `PHASE 7 FULLY ACCEPTED` و دستور صریح بعدی مالک مجاز است. تا آن زمان:

`PHASE 8 NOT STARTED`  
`NEXT GATE: 14 VALID CONSECUTIVE DAYS + PHASE 7 COMPLETION AUDIT`
