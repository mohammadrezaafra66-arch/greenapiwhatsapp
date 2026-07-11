# CLAUDE CODE PROMPT — Contact Info Column + Recent Sellers Modal
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## AUTONOMOUS EXECUTION
Run all phases. No confirmation. Pick safest option at each decision, note it. Verify → commit → push.
Use afrakala/whatsapp_sender DB, real service names. Keep additive, preserve existing features.

## GOAL (two related features)
FEATURE A: In "رصد محصولات در گروه‌ها" table (raw product-mention feed), add column "اطلاعات تماس"
  showing the sender's phone + any phone numbers found inside the message text.
FEATURE B: In "جدول محصولات پر تکرار" table (top-products aggregate), add column "مشاهده فروشندگان اخیر".
  Clicking it opens a modal listing every seller who advertised THAT product: contact info, time/date (Shamsi),
  and the group name where they advertised it.

---

## PHASE 0 — Ensure product_mention_logs stores what we need

Check the product_mention_logs model/table. It needs these columns (add via main.py DDL if missing):
```python
        ddl_contact = [
            "ALTER TABLE product_mention_logs ADD COLUMN IF NOT EXISTS message_text text",
            "ALTER TABLE product_mention_logs ADD COLUMN IF NOT EXISTS sender_phone varchar(20)",
            "ALTER TABLE product_mention_logs ADD COLUMN IF NOT EXISTS sender_name varchar(200)",
            "ALTER TABLE product_mention_logs ADD COLUMN IF NOT EXISTS group_name varchar(300)",
        ]
        for stmt in ddl_contact:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL contact] {e}")
```

In the detection path (webhook.py where a mention is logged), populate these fields going forward:
- message_text = the full incoming message text
- sender_phone = the sender's number (from the webhook senderData / chatId)
- sender_name = senderData.senderName if available
- group_name = the group's name (from stored whatsapp_groups by chat_id, or senderData.chatName)

Existing rows will have these NULL — that's fine, they just show "—".

---

## PHASE 1 — Backend: phone extraction utility

Create `backend/app/services/phone_extract.py`:
```python
"""Extract phone numbers from free text (Persian/English digits)."""
import re

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def normalize_digits(text: str) -> str:
    return text.translate(PERSIAN_DIGITS).translate(ARABIC_DIGITS)

def normalize_iranian_mobile(digits: str) -> str | None:
    """Normalize to 09xxxxxxxxx if it's a valid Iranian mobile, else None."""
    d = re.sub(r'\D', '', digits)
    if d.startswith('98'):
        d = '0' + d[2:]
    elif d.startswith('9') and len(d) == 10:
        d = '0' + d
    if len(d) == 11 and d.startswith('09'):
        return d
    return None

def extract_phones_from_text(text: str) -> list[str]:
    """Find phone-like sequences in message text. Returns deduped normalized list."""
    if not text:
        return []
    t = normalize_digits(text)
    found = []
    seen = set()

    # Iranian mobile
    for m in re.findall(r'(?:\+?98|0)?9\d{9}', t):
        norm = normalize_iranian_mobile(m)
        if norm and norm not in seen:
            seen.add(norm)
            found.append(norm)

    # Landlines: 0xx(x) + 7-8 digits, optional separators
    for m in re.findall(r'0\d{2,3}[-\s]?\d{7,8}', t):
        d = re.sub(r'\D', '', m)
        if 10 <= len(d) <= 11 and not d.startswith('09') and d not in seen:
            seen.add(d)
            found.append(d)

    return found

def normalize_sender_phone(raw: str) -> str:
    """Normalize a stored sender phone (98xxxxxxxxxx or with @c.us) to 09xxxxxxxxx display."""
    if not raw:
        return ""
    d = re.sub(r'\D', '', raw.split("@")[0])
    norm = normalize_iranian_mobile(d)
    return norm or d
```

Add unit tests in tests/test_phone_extract.py: Persian digits ۰۹۱۲۳۴۵۶۷۸۹, +989123456789, 09123456789, 021-88776655 landline, "سلام بدون شماره" → [].

---

## PHASE 2 — FEATURE A: contact column in the raw mention feed

Find the endpoint serving "رصد محصولات در گروه‌ها" (the raw feed with محصول/فرستنده/گروه/پیام/زمان columns — likely /reporting/product-mentions or a daily-report endpoint). For each row add:
```python
from app.services.phone_extract import extract_phones_from_text, normalize_sender_phone

sender_display = normalize_sender_phone(m.sender_phone or "")
phones_in_msg = extract_phones_from_text(m.message_text or "")
all_contacts = []
for p in ([sender_display] + phones_in_msg):
    if p and p not in all_contacts:
        all_contacts.append(p)

# add to row dict:
"sender_phone": sender_display,
"phones_in_message": phones_in_msg,
"all_contacts": all_contacts,
```

Frontend — in the raw mention table (the one in the screenshot with محصول/فرستنده/گروه/پیام/زمان), add header "اطلاعات تماس" and cell:
```jsx
<th className="py-2 text-right">اطلاعات تماس</th>
...
<td className="py-2">
  {row.all_contacts?.length > 0 ? (
    <div className="flex flex-col gap-1">
      {row.all_contacts.map((phone, i) => (
        <div key={i} className="flex items-center gap-1">
          <span className="font-mono text-xs text-green-400" dir="ltr">{phone}</span>
          <button onClick={() => navigator.clipboard.writeText(phone)}
                  className="text-gray-500 hover:text-gray-300 text-xs" title="کپی">📋</button>
          {i === 0 && row.sender_phone === phone && (
            <span className="text-[10px] text-blue-400">فرستنده</span>
          )}
        </div>
      ))}
    </div>
  ) : <span className="text-gray-600 text-xs">—</span>}
</td>
```

---

## PHASE 3 — FEATURE B: recent-sellers endpoint for a product

Add endpoint in reporting.py:
```python
@router.get("/product-sellers")
async def product_sellers(product_name: str, days: int = 30, limit: int = 100, db: AsyncSession = Depends(get_db)):
    """
    All sellers who advertised a given product: contact, time (Shamsi), group.
    Powers the 'مشاهده فروشندگان اخیر' modal in the top-products table.
    """
    from app.models.reporting import ProductMentionLog
    from app.services.phone_extract import extract_phones_from_text, normalize_sender_phone
    from app.utils.shamsi import to_shamsi
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(ProductMentionLog)
        .where(ProductMentionLog.product_name == product_name)
        .where(ProductMentionLog.mentioned_at >= cutoff)
        .order_by(ProductMentionLog.mentioned_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()

    sellers = []
    for m in rows:
        sender_display = normalize_sender_phone(m.sender_phone or "")
        phones_in_msg = extract_phones_from_text(m.message_text or "")
        all_contacts = []
        for p in ([sender_display] + phones_in_msg):
            if p and p not in all_contacts:
                all_contacts.append(p)
        sellers.append({
            "sender_name": m.sender_name or "",
            "sender_phone": sender_display,
            "all_contacts": all_contacts,
            "group_name": m.group_name or "",
            "message_preview": (m.message_text or "")[:120],
            "time_shamsi": to_shamsi(m.mentioned_at),
        })

    return {
        "product_name": product_name,
        "total_sellers": len(sellers),
        "sellers": sellers,
    }
```

---

## PHASE 4 — FEATURE B: frontend modal in top-products table

In the top-products table (Reporting "جدول محصولات پر تکرار" — the one with رتبه/نام محصول/تعداد تکرار/تعداد گروه/تعداد فرستنده/آخرین ذکر), add a new column "مشاهده فروشندگان اخیر":

```jsx
{/* header */}
<th className="py-2 text-center">مشاهده فروشندگان اخیر</th>

{/* cell */}
<td className="py-2 text-center">
  <button
    onClick={() => openSellersModal(row.product_name)}
    className="text-xs bg-green-700 hover:bg-green-600 text-white px-3 py-1 rounded">
    👁 مشاهده ({row.sender_count})
  </button>
</td>
```

Modal component:
```jsx
const [sellersModal, setSellersModal] = useState(null); // {product_name, sellers, loading}

const openSellersModal = async (productName) => {
  setSellersModal({ product_name: productName, sellers: [], loading: true });
  try {
    const res = await http.get("/reporting/product-sellers", {
      params: { product_name: productName, days: 30, limit: 100 }
    });
    setSellersModal({ product_name: productName, sellers: res.data.sellers, loading: false });
  } catch {
    setSellersModal({ product_name: productName, sellers: [], loading: false });
  }
};

// Modal JSX (rtl):
{sellersModal && (
  <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
       onClick={() => setSellersModal(null)}>
    <div className="bg-gray-900 rounded-xl max-w-3xl w-full max-h-[80vh] overflow-hidden flex flex-col"
         onClick={e => e.stopPropagation()}>
      {/* Header */}
      <div className="p-4 border-b border-gray-700 flex justify-between items-center">
        <div>
          <h3 className="font-bold text-white">فروشندگان اخیر</h3>
          <p className="text-sm text-gray-400">{sellersModal.product_name}</p>
        </div>
        <button onClick={() => setSellersModal(null)} className="text-gray-400 hover:text-white text-xl">✕</button>
      </div>
      {/* Body */}
      <div className="overflow-y-auto p-4">
        {sellersModal.loading ? (
          <div className="text-center py-8 text-gray-400">در حال بارگذاری...</div>
        ) : sellersModal.sellers.length === 0 ? (
          <div className="text-center py-8 text-gray-500">فروشنده‌ای یافت نشد</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-gray-700">
                <th className="py-2 text-right">فرستنده</th>
                <th className="py-2 text-right">اطلاعات تماس</th>
                <th className="py-2 text-right">گروه</th>
                <th className="py-2 text-right">زمان</th>
              </tr>
            </thead>
            <tbody>
              {sellersModal.sellers.map((s, i) => (
                <tr key={i} className="border-b border-gray-800">
                  <td className="py-2">{s.sender_name || "—"}</td>
                  <td className="py-2">
                    {s.all_contacts.length > 0 ? (
                      <div className="flex flex-col gap-1">
                        {s.all_contacts.map((p, j) => (
                          <div key={j} className="flex items-center gap-1">
                            <span className="font-mono text-xs text-green-400" dir="ltr">{p}</span>
                            <button onClick={() => navigator.clipboard.writeText(p)}
                                    className="text-gray-500 hover:text-gray-300 text-xs">📋</button>
                          </div>
                        ))}
                      </div>
                    ) : <span className="text-gray-600 text-xs">—</span>}
                  </td>
                  <td className="py-2 text-gray-300 text-xs">{s.group_name || "—"}</td>
                  <td className="py-2 text-gray-400 text-xs" dir="ltr">{s.time_shamsi}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {/* Footer */}
      <div className="p-3 border-t border-gray-700 text-center text-xs text-gray-500">
        {sellersModal.sellers.length} فروشنده در ۳۰ روز اخیر
      </div>
    </div>
  </div>
)}
```

Add a "خروجی اکسل" button in the modal footer that exports the sellers list (optional, if easy — use existing export util or a simple CSV blob).

---

## PHASE 5 — Verify, rebuild, push

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/services/phone_extract.py app/api/v1/*.py app/main.py app/services/*.py
python -m pytest tests/ -v
cd ..
docker compose up -d --build backend worker-general worker-webhooks
sleep 8
# test contact fields on the raw feed and the sellers endpoint:
curl -s "http://localhost:8002/api/v1/reporting/product-mentions?limit=3" 2>/dev/null | python -m json.tool | head -40 || echo "check the real raw-feed endpoint path"
curl -s "http://localhost:8002/api/v1/reporting/product-sellers?product_name=%D8%B3%D8%A7%DB%8C%D8%AF%20%D8%A7%D9%84%D8%AC%DB%8C&days=30" | python -m json.tool | head -30
cd frontend && npm run build && cd ..
docker compose up -d --build --no-deps frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```

Commit:
```bash
git add -A
git commit -m "feat: contact-info column + recent-sellers modal in product monitoring

- product_mention_logs: store message_text, sender_phone, sender_name, group_name at detection
- phone_extract.py: extract Iranian mobile + landline from text (Persian/Arabic/English digits) + tests
- Feature A: 'اطلاعات تماس' column in raw mention feed (sender phone + numbers found in message, copy buttons)
- Feature B: GET /reporting/product-sellers — all sellers of a product with contact/group/time (Shamsi)
- Feature B: 'مشاهده فروشندگان اخیر' column + modal in top-products table (per-product seller list)
- historical rows show '—' for fields not captured before this change"
git push origin main
```

## NOTES TO RECORD
- Confirm the exact endpoint path for the raw "رصد محصولات در گروه‌ها" feed and the top-products table, and wire both correctly.
- Note that message_text/sender_phone/group_name populate only for NEW mentions after this deploy; historical rows show "—".
- Confirm Persian-digit phone extraction works on a real message sample.