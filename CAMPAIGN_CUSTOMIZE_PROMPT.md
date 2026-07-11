# CLAUDE CODE PROMPT — Account Rename + Campaign Message Customization
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## AUTONOMOUS EXECUTION
Run all phases. No confirmation. Pick safest option, note it. Verify → commit → push.
Use afrakala/whatsapp_sender DB, real service names. Keep additive, preserve existing features.

## CONTEXT
Campaign sending + AI message generation now work. A sample AI message looked like:
"گروه عزیز سلام 😊 امروز سه تا پیشنهاد ویژه براتون دارم... 🔹 یونیوا ۱۸۰۰۰ ... برای لغو عدد ۱۱ ارسال کنید"
The user wants control over: (1) the opening line, (2) per-group different products, (3) weighted random
product selection, (4) optional opt-out ("لغو ۱۱") line. Plus an account rename button.

---

## PHASE 1 — Account rename button

In the Accounts page (frontend/src/pages/Accounts.jsx), add an "ویرایش نام" button on each account card
(near the QR / بررسی وضعیت / حذف buttons). Clicking opens a small inline input or modal to edit the
account's display name.

Backend: add endpoint in accounts.py (if not present):
```python
class AccountRename(BaseModel):
    name: str

@router.put("/{account_id}/rename")
async def rename_account(account_id: str, body: AccountRename, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    account.name = body.name.strip()[:200]
    await db.commit()
    return {"id": str(account.id), "name": account.name}
```

Frontend:
```jsx
const [renaming, setRenaming] = useState(null); // account id being renamed
const [newName, setNewName] = useState("");

const startRename = (acc) => { setRenaming(acc.id); setNewName(acc.name); };
const saveRename = async (id) => {
  await http.put(`/accounts/${id}/rename`, { name: newName });
  setRenaming(null);
  await reloadAccounts();
  toast.success("نام حساب تغییر کرد");
};

// button on card:
<button onClick={() => startRename(account)} className="btn-secondary text-xs">✏️ ویرایش نام</button>

// inline edit (when renaming === account.id):
{renaming === account.id && (
  <div className="flex gap-2 mt-2">
    <input value={newName} onChange={e => setNewName(e.target.value)}
           className="input-dark text-sm flex-1" placeholder="نام جدید حساب" />
    <button onClick={() => saveRename(account.id)} className="btn-green text-xs">ذخیره</button>
    <button onClick={() => setRenaming(null)} className="btn-secondary text-xs">لغو</button>
  </div>
)}
```

---

## PHASE 2 — Customizable opening line

Currently the AI generates the opening ("گروه عزیز سلام 😊"). Add a campaign option to control it.

DB (main.py DDL):
```python
"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS opening_line varchar(500)",
"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS opening_mode varchar(20) DEFAULT 'ai'",
```
opening_mode: ai (AI writes it) | fixed (use opening_line verbatim) | none (no greeting) | random (rotate among several)

In campaign create body add:
```python
    opening_line: str | None = None
    opening_mode: str = "ai"          # ai | fixed | none | random
    opening_variants: list[str] | None = None   # for random mode
```

In gpt_service / campaign_runner where the message is built:
- opening_mode == "ai" → current behavior (AI writes greeting)
- opening_mode == "fixed" → prepend opening_line, tell GPT NOT to add its own greeting
- opening_mode == "none" → instruct GPT to skip any greeting, start directly with the offer
- opening_mode == "random" → pick a random line from opening_variants each send (varies per group → looks different to Meta)

Update the GPT system prompt accordingly, e.g. when fixed/none, add: "پیام را بدون سلام و احوال‌پرسی شروع کن" or "پیام را دقیقاً با این عبارت شروع کن: {opening_line}".

Frontend (campaign create modal): a "عبارت آغازین" section:
- radio: هوش مصنوعی بنویسد / متن ثابت / بدون سلام / چند حالت تصادفی
- if fixed → text input
- if random → multi-line textarea (one greeting per line), rotated per send

---

## PHASE 3 — Per-group different products (anti-Meta variation)

Goal: each group gets a DIFFERENT subset of products, so the message looks different across groups
(reduces Meta pattern-detection risk).

Add campaign option:
```python
    product_variation_mode: str = "same"   # same | per_group_random | rotate
    products_per_group: int = 3
```
- same → every group gets the same products (current)
- per_group_random → for each group, randomly pick `products_per_group` from the campaign's product pool
- rotate → cycle through the product pool so consecutive groups get different slices

In campaign_runner, when sending to a group campaign target:
- If per_group_random: for each group, sample a different random subset from the product pool
- If rotate: maintain an index, advance per group
- Pass that group-specific product list into the GPT/message builder

This means the product pool for the campaign should be larger than products_per_group (e.g. pool of 15,
show 3 per group). Reuse the existing product-selection wiring; just make the selection per-group instead
of once per campaign.

Frontend: a "تنوع محصولات بین گروه‌ها" section:
- radio: یکسان برای همه / تصادفی برای هر گروه / چرخشی
- number: تعداد محصول در هر گروه (default 3)
- (when per_group_random/rotate) let user pick the larger product POOL to draw from

---

## PHASE 4 — Weighted random product selection

Goal: when using random selection, let the user assign WEIGHTS to products so important products appear
in MORE groups / more often.

DB — a weights table or a JSON column on the campaign:
```python
"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS product_weights jsonb",
```
product_weights: a JSON map like {"product_name_or_id": weight, ...} where higher weight = more likely.

In the random/weighted selection logic (campaign_runner or a helper), when picking products for a group,
use weighted random sampling:
```python
import random

def weighted_sample(products: list, weights: dict, k: int) -> list:
    """Pick k products using weights (higher weight = more likely). Weights default to 1."""
    pool = list(products)
    chosen = []
    for _ in range(min(k, len(pool))):
        ws = [max(0.01, weights.get(p.get("name") or p.get("id"), 1)) for p in pool]
        pick = random.choices(pool, weights=ws, k=1)[0]
        chosen.append(pick)
        pool.remove(pick)
    return chosen
```

Frontend: in the product selection area, next to each selected product show a weight control
(a number input or a slider 1–10, default 1). Higher weight → appears in more groups. Label it clearly:
"وزن (اهمیت): هرچه بیشتر، در گروه‌های بیشتری تبلیغ می‌شود".

Show a small hint: "محصولات با وزن بالاتر در گروه‌های بیشتری و با تکرار بیشتری تبلیغ می‌شوند."

---

## PHASE 5 — Optional opt-out line ("لغو ۱۱")

Currently every message ends with "برای لغو عدد ۱۱ ارسال کنید". Make it optional and configurable.

DB:
```python
"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS include_opt_out boolean DEFAULT true",
"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS opt_out_text varchar(300)",
```

In campaign create body:
```python
    include_opt_out: bool = True
    opt_out_text: str | None = None   # custom opt-out text; default "برای لغو عدد ۱۱ ارسال کنید"
```

In gpt_service / message builder:
- If include_opt_out is False → instruct GPT to NOT add any opt-out/unsubscribe line, and strip it if present
- If True → append opt_out_text (or the default) — and make sure GPT doesn't duplicate it

Update the GPT prompt: when include_opt_out is False, add "هیچ عبارت لغو یا انصراف در انتهای پیام نگذار".
When True and opt_out_text is set, append that exact text.

Frontend (campaign create modal): a toggle "افزودن عبارت لغو اشتراک" (default on) + when on, an optional
text input to customize it (placeholder: "برای لغو عدد ۱۱ ارسال کنید").

---

## PHASE 6 — Verify, rebuild, push

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/api/v1/*.py app/services/*.py app/workers/*.py app/main.py
python -m pytest tests/ -v
cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
sleep 8
curl -s "http://localhost:8002/api/v1/accounts/" | python -m json.tool | head -20
cd frontend && npm run build && cd ..
docker compose up -d --build --no-deps frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```

Commit:
```bash
git add -A
git commit -m "feat: account rename + campaign message customization

- Account rename button + PUT /accounts/{id}/rename
- Campaign opening line: ai/fixed/none/random modes (opening_line, opening_variants)
- Per-group product variation: same/per_group_random/rotate + products_per_group (anti-Meta variation)
- Weighted random product selection: product_weights, weighted_sample helper (important products appear in more groups)
- Optional opt-out line: include_opt_out toggle + custom opt_out_text
- GPT prompt updated to respect greeting mode, per-group products, and opt-out settings"
git push origin main
```

## NOTES TO RECORD
- Confirm per_group_random actually produces different product sets across groups in a test run.
- Confirm weighted selection makes high-weight products appear more often.
- Confirm include_opt_out=False removes the "لغو ۱۱" line from the generated message.
- Confirm fixed/none opening modes suppress the AI greeting correctly.