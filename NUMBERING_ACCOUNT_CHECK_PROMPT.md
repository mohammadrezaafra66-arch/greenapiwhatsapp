# CLAUDE CODE PROMPT — Contacts Row Numbering + Account State Investigation
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## AUTONOMOUS EXECUTION
Run phases. No confirmation for code changes. Pick safest option, note it. Verify → commit → push.
Use afrakala/whatsapp_sender DB, real service names. Keep additive, preserve existing features.
EXCEPTION: for PHASE 2 (account investigation), do NOT delete or modify any account record —
only investigate and REPORT findings. Deleting an account is the one action that needs the user's OK.

---

## PHASE 1 — Contacts row numbering (continuous across pages)

In the Contacts page (frontend/src/pages/Contacts.jsx), add a leading "#" (ردیف) column that numbers
rows continuously across pagination. Page 1 shows 1..1000, page 2 shows 1001..2000, etc.

The row number = (current skip offset) + (index in current page) + 1.

Since the app loads pages via skip/limit and may append or replace, compute the absolute index:
```jsx
{/* header — first column */}
<th className="py-2 w-12 text-center">ردیف</th>

{/* cell — first column, before the checkbox/name */}
<td className="py-2 text-center text-gray-500 text-xs">
  {(rowAbsoluteIndex).toLocaleString("fa-IR")}
</td>
```

Determine rowAbsoluteIndex correctly based on how Contacts.jsx currently paginates:
- If it REPLACES data per page (shows one page at a time): rowAbsoluteIndex = skip + localIndex + 1
  where skip is the current offset (e.g. page 2 → skip=1000).
- If it APPENDS (infinite scroll, all loaded rows in one array): rowAbsoluteIndex = localIndex + 1
  (since the array already holds everything loaded so far in order).

Inspect the actual pagination implementation and wire whichever matches so the numbering is continuous
and correct. The number should reflect the contact's position in the full ordered list, continuing
from the previous page's last number — NOT resetting to 1 on each page.

If the current ordering is created_at DESC, keep that; the # just reflects display position.

---

## PHASE 2 — Investigate account state mismatch (INVESTIGATE ONLY, NO DELETION)

Problem: In the UI, the account labeled "محمدرضا افرا" (phone 09122270261) shows "در انتظار اتصال"
(pending), while account "98" (instance 7105325764) shows "متصل" (connected). The user believes
09122270261 is actually connected. Investigate the truth.

Run and REPORT all of this (do not change any account):

```bash
# 1. List all accounts with full detail
echo "=== ALL ACCOUNTS IN DB ==="
curl -s "http://localhost:8002/api/v1/accounts/" | python -m json.tool

# 2. Check the DB directly for instance_id, phone, status, is_default, created_at
echo "=== DB ACCOUNTS TABLE ==="
docker exec claudegreenapi-db-1 psql -U afrakala -d whatsapp_sender -c \
  "SELECT id, name, instance_id, phone, status, is_default, days_active, created_at FROM accounts ORDER BY created_at;"

# 3. For EACH account, query its REAL Green API state directly
# (getStateInstance tells the true authorization state)
echo "=== REAL GREEN API STATE PER ACCOUNT ==="
# For each account, using its instance_id + api_token, call:
# https://{apiUrl}/waInstance{instance_id}/getStateInstance/{api_token}
# Report: instance_id → stateInstance (authorized / notAuthorized / blocked / etc.)
```

Write a small script or use the existing GreenAPIClient to call getStateInstance for every account and print:
- account name, instance_id, DB status, REAL Green API stateInstance, phone reported by getSettings/getWaSettings

```python
# Pseudocode to run inside the backend container or as a script:
# for each account in DB:
#     client = GreenAPIClient(account.instance_id, account.api_token)
#     state = await client.get_state_instance()   # returns {"stateInstance": "authorized"} etc.
#     wa = await client.get_wa_settings()          # returns phone/wid
#     print(account.name, account.instance_id, account.status, state, wa.get("phone"/"wid"))
```

Then determine and REPORT:
1. Is "محمدرضا افرا" (09122270261) a SEPARATE Green API instance from "98" (7105325764)?
   - Note: 7105325764 looks like an idInstance, while 09122270261 looks like a phone number.
     Check what instance_id the "محمدرضا افرا" account actually has in the DB — it may be a different
     real instance, or it may be a placeholder/duplicate that was never connected.
2. What is each account's REAL stateInstance from Green API?
3. Is the UI status stale (DB says pending but Green API says authorized)? If so, the fix is to run
   the state-sync so the DB matches reality.

Run the sync task to refresh DB status from Green API (this is safe — it only updates status fields):
```bash
# Trigger sync_account_states (or whatever the app's account-state-sync task/endpoint is)
curl -s -X POST "http://localhost:8002/api/v1/accounts/sync-states" 2>/dev/null || echo "find the real sync trigger"
# then re-list to see if statuses corrected:
curl -s "http://localhost:8002/api/v1/accounts/" | python -m json.tool
```

REPORT the full findings clearly:
- Each account: DB status vs REAL Green API state
- Whether 09122270261 is a real connected instance, a duplicate, or a never-connected placeholder
- Whether syncing fixed the display
- A RECOMMENDATION (but do NOT execute deletion): e.g. "account X is a stale duplicate pointing to
  a non-existent instance — recommend deleting it" OR "account X is a real separate instance that is
  genuinely not authorized — needs QR scan" OR "DB was stale, sync corrected it."

---

## PHASE 3 — If state sync logic is missing or broken, fix it (safe)

If PHASE 2 reveals the DB status is stale because the sync task isn't running or isn't updating
correctly, fix the sync so DB status reflects Green API's real stateInstance. This is a safe,
additive fix (updates status fields only, never deletes). Ensure:
- A periodic task (every few minutes) calls getStateInstance per account and updates status
  (authorized→active/connected, notAuthorized→pending) accordingly.
- The account list endpoint reflects the synced status.

Do NOT auto-delete or auto-merge accounts — only correct the status display.

---

## PHASE 4 — Verify, rebuild, push

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/api/v1/*.py app/services/*.py app/workers/*.py app/main.py
python -m pytest tests/ -v
cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
sleep 8
curl -s "http://localhost:8002/api/v1/accounts/" | python -m json.tool
cd frontend && npm run build && cd ..
docker compose up -d --build --no-deps frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```

Commit (code changes only — numbering + any sync fix):
```bash
git add -A
git commit -m "feat: contacts row numbering (continuous across pages) + account state sync fix

- Contacts.jsx: leading ردیف column, continuous numbering across pagination (page 2 starts at 1001)
- account state sync: DB status now reflects real Green API getStateInstance (fixes stale pending/connected display)
- investigation: reported real vs DB state for all accounts (no accounts deleted/modified)"
git push origin main
```

## NOTES TO RECORD
- The full account investigation findings (DB status vs real Green API state per account).
- Whether 09122270261 is a distinct real instance, a duplicate, or a placeholder.
- Explicit recommendation on the pending account, WITHOUT having deleted anything.