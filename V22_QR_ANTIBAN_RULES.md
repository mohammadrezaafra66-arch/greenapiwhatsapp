# V22 MASTER PROMPT — Afrakala WhatsApp Sender
## Show anti-ban rules on the QR-scan screen (pre-scan + scan-moment rules only)

> **MODE: FULLY AUTONOMOUS.** Execute end-to-end WITHOUT asking questions and WITHOUT
> waiting for approval. Test after the change, then commit and push. Produce a short final
> report.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: **V21**, all tests passing,
`origin/main` clean. Stack: FastAPI + PostgreSQL + Redis + Celery + React/Vite, Green API.
Backend 8002, frontend 3002.

**Goal:** On the QR-code screen — the modal/panel that appears when the user clicks the
"QR" button on an account card (accounts page at `/accounts`) to scan and connect a
WhatsApp number to a Green API instance — display a clear, prominent Persian (RTL)
ANTI-BAN RULES box that the user sees BEFORE scanning. Only include rules relevant to the
moment of connecting (pre-scan and scan-time). Do NOT include post-connection or
sending-behavior rules here.

### NON-NEGOTIABLE GUARDRAILS
1. Do NOT touch backend send logic, the warm-up mesh, polling, ngrok, or webhooks. This is
   a FRONTEND-ONLY UI addition (plus tests).
2. NEVER enable polling; webhook-only stays intact (you're not touching it anyway).
3. All new UI text in Persian (Farsi), RTL. Code/vars/comments English.
4. Commit + push (`V22: anti-ban rules on QR screen`).

---

## PART 1 — Add the anti-ban rules box to the QR screen

### 1.1 Locate the QR component
Find the React component that renders the QR code when the user clicks the "QR" button on
an account card (accounts page). It's a modal/dialog or panel showing the QR image to scan
for linking the device. Add the rules box to THAT screen so it's visible together with the
QR (above or beside the QR image, clearly readable before scanning).

### 1.2 The rules box (Persian, RTL) — use this EXACT content
Render a visually prominent box titled **«⚠️ قوانین مهم قبل از اسکن (برای جلوگیری از بلاک)»**
containing these rules (keep wording; format as a clean, readable list with the first one
emphasized as the most important):

- **۱. حداقل ۲۴ ساعت صبر کنید (مهم‌ترین قانون):** بین ثبت واتساپ روی گوشی و اسکن این کد QR
  باید حداقل ۲۴ ساعت فاصله باشد. اتصال زودهنگام (مثلاً بعد از ۱ ساعت) یکی از اصلی‌ترین
  دلایل بلاک است. امروز واتساپ را روی گوشی بسازید و پروفایل را کامل کنید؛ فردا این کد را
  اسکن کنید.
- **۲. پروفایل را کامل کنید:** قبل از اسکن، عکس پروفایل، نام و بیو را روی گوشی تنظیم کنید.
  شماره با پروفایل کامل، طبیعی‌تر و کم‌خطرتر است.
- **۳. در ۲۴ ساعت اول از شماره عادی استفاده کنید:** با اکانت شخصی چت کنید، تماس و پیامک
  عادی داشته باشید. این کار شماره را «گرم» و واقعی نشان می‌دهد. (تأییدشده توسط پشتیبانی.)
- **۴. به دستگاه اضافی وصل نکنید:** این شماره را هم‌زمان به وب‌واتساپ یا نسخه دسکتاپ وصل
  نکنید. فقط همین اتصال کافی است — اتصال‌های اضافی خطر بلاک را زیاد می‌کند.
- **۵. سیم‌کارت غیرمتوالی و «پیرشده»:** اگر شماره نو است، ترجیحاً از سیم‌کارتی استفاده کنید
  که چند روز روی گوشی با آن کار کرده‌اید و شماره‌اش پشت‌سرهم/سری با بقیه نباشد. شماره‌های
  کاملاً نو و سری بیشتر بلاک می‌شو
- **۶. یک اتصال در لحظه:** اگر اکانت قبلاً وصل بوده و کارت زرد گرفته، اول ۲۴ ساعت استراحت
  دهید، بعد دوباره وصل کنید.

### 1.3 Styling
- Prominent, readable, RTL. Use a warning/amber accent so it stands out (consistent with
  the app's existing style). Rule ۱ visually emphasized (bold/colored) as the most
  important. The box must not overlap or hide the QR image; place it so both the QR and the
  rules are clearly visible (e.g. rules above the QR, or in a side column). Keep it usable
  on the normal screen size the app runs at.
- A short header line above the list is fine, e.g. «برای اینکه شماره بلاک نشود، لطفاً قبل
  از اسکن این موارد را رعایت کنید:».

### 1.4 Tests
Add a frontend test (matching the project's existing test approach) asserting the QR
screen renders the rules box with rule ۱ (the 24-hour rule) present. Run the full suite.
Commit + push `V22: anti-ban rules on QR screen`.

---

## FINAL REPORT
- Confirm the rules box appears on the QR-scan screen with the 6 rules, rule ۱ emphasized.
- Confirm no backend/mesh/polling/ngrok/webhook changes were made (frontend-only + test).
- Reminder: redeploy the frontend for it to show —
  `docker compose build frontend && docker compose up -d frontend` — then hard-refresh.
- List the pushed commit.

Then STOP.