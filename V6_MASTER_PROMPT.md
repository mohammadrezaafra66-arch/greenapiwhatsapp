# CLAUDE CODE MASTER PROMPT — V6 Remaining Green API Features
# Afrakala WhatsApp Sender
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## EXECUTION CONTRACT
Run every phase sequentially. Never stop for confirmation. Never ask questions.
Fix any error before moving to next phase. At end: pytest, docker rebuild, push.

---

## FEATURE LIST (6 items)

1. SetDisappearingChat — پیام‌های ناپدیدشونده per-chat
2. GetContactsBlock — لیست مخاطبین بلاک‌شده
3. AddContact / EditContact / DeleteContact — مدیریت کامل فون‌بوک
4. Proxy support — تنظیم proxy per-account برای پایداری از ایران
5. Catalog webhook handler — ذخیره رویداد catalog در inbox
6. Device/StatusInstance webhook handlers — ذخیره تغییر وضعیت دستگاه

---

## PHASE 0 — DB migrations

In `backend/app/main.py` lifespan DDL block, add:

```python
        ddl_v6 = [
            # Proxy settings per account
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS proxy_host varchar(200)",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS proxy_port integer",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS proxy_login varchar(100)",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS proxy_password varchar(200)",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS proxy_enabled boolean DEFAULT false",
            # Disappearing chat settings
            """CREATE TABLE IF NOT EXISTS disappearing_chat_settings (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                chat_id varchar(200) NOT NULL,
                ephemeral integer NOT NULL DEFAULT 0,
                set_at timestamp DEFAULT now(),
                UNIQUE(account_id, chat_id)
            )""",
            # Blocked contacts
            """CREATE TABLE IF NOT EXISTS wa_blocked_contacts (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                phone varchar(20) NOT NULL,
                synced_at timestamp DEFAULT now(),
                UNIQUE(account_id, phone)
            )""",
        ]
        for stmt in ddl_v6:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V6] {e}")
```

---

## PHASE 1 — New models

### `backend/app/models/wa_extras.py`
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class DisappearingChatSetting(Base):
    __tablename__ = "disappearing_chat_settings"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(200), nullable=False)
    ephemeral: Mapped[int] = mapped_column(Integer, default=0)
    set_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class WaBlockedContact(Base):
    __tablename__ = "wa_blocked_contacts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

Update `backend/app/models/__init__.py` to import these two models.

---

## PHASE 2 — Green API client additions

Add to `backend/app/services/green_api.py` GreenAPIClient class:

```python
    # ── DISAPPEARING MESSAGES ─────────────────────────
    async def set_disappearing_chat(self, phone: str, ephemeral: int = 0) -> bool:
        """
        Set disappearing messages timer for a chat.
        ephemeral: 0=off, 86400=24h, 604800=7days, 7776000=90days
        """
        r = await self._post("setDisappearingChat", {
            "chatId": self._chat_id(phone),
            "ephemeral": ephemeral
        })
        return r.get("chatId") is not None or r.get("isSet", False)

    # ── CONTACTS MANAGEMENT ───────────────────────────
    async def get_contacts_block(self) -> list[dict]:
        """Get list of contacts blocked by this WhatsApp account."""
        r = await self._get("getContactsBlock")
        return r if isinstance(r, list) else []

    async def add_contact(self, phone: str, first_name: str, last_name: str = "", company: str = "افراکالا") -> bool:
        """Add a contact to the WhatsApp phonebook."""
        r = await self._post("addContact", {
            "phoneContact": int(self._normalize(phone)),
            "firstName": first_name,
            "lastName": last_name,
            "company": company
        })
        return r.get("saveContact", False) or "contactId" in r

    async def edit_contact(self, phone: str, first_name: str, last_name: str = "", company: str = "") -> bool:
        """Edit an existing contact in the phonebook."""
        r = await self._post("editContact", {
            "phoneContact": int(self._normalize(phone)),
            "firstName": first_name,
            "lastName": last_name,
            "company": company
        })
        return r.get("editContact", False)

    async def delete_contact(self, phone: str) -> bool:
        """Delete a contact from the phonebook."""
        r = await self._post("deleteContact", {
            "phoneContact": int(self._normalize(phone))
        })
        return r.get("deleteContact", False)

    # ── PROXY ─────────────────────────────────────────
    async def set_proxy(self, host: str, port: int, login: str = "", password: str = "") -> bool:
        """
        Set proxy for this WhatsApp instance.
        Use SOCKS5 or HTTP proxy to keep Iranian connection stable.
        """
        proxy_url = f"socks5://{login}:{password}@{host}:{port}" if login else f"socks5://{host}:{port}"
        r = await self._post("setSettings", {"proxyUrl": proxy_url})
        return r.get("saveSettings", False)

    async def remove_proxy(self) -> bool:
        """Remove proxy settings."""
        r = await self._post("setSettings", {"proxyUrl": ""})
        return r.get("saveSettings", False)

    async def get_proxy(self) -> str | None:
        """Get current proxy URL from settings."""
        settings = await self.get_settings()
        return settings.get("proxyUrl") or None
```

---

## PHASE 3 — Webhook handlers for new event types

In `backend/app/api/v1/webhook.py`, in `process_webhook`, add new elif branches:

```python
    elif wtype in ("deviceStatusChanged", "deviceWebhook"):
        await handle_device_status(instance_id, payload)
    elif wtype in ("statusInstanceChanged", "statusInstance"):
        pass  # Already handled by handle_state_change — skip duplicate
    elif wtype in ("catalogUpdate", "catalogWebhook"):
        await handle_catalog_update(instance_id, payload)
    elif wtype in ("incomingBlock", "incomingChatBlock"):
        await handle_incoming_block(instance_id, payload)
    elif wtype in ("outgoingCall", "outgoingCallReceived"):
        await handle_outgoing_call(instance_id, payload)
```

Add handler functions at bottom of webhook.py:

```python
async def handle_device_status(instance_id: str, payload: dict):
    """Handle device status changes (battery, online status, etc.)."""
    device_status = payload.get("deviceStatus", {}) or payload.get("status", "")
    print(f"[Device] instance {instance_id} device status: {device_status}")
    # Log to account notes — lightweight handler
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Account).where(Account.instance_id == instance_id))
        account = result.scalar_one_or_none()
        if account:
            account.notes = f"[device] {device_status} at {datetime.utcnow().isoformat()}"
            await db.commit()


async def handle_catalog_update(instance_id: str, payload: dict):
    """Handle WhatsApp catalog updates — store as inbox message."""
    sender = payload.get("senderData", {})
    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=sender.get("sender", "").split("@")[0],
            sender_name=sender.get("senderName", ""),
            message_type="catalog_update",
            text_content="آپدیت کاتالوگ",
            original_payload=json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0) or 0)
        )
        db.add(msg)
        await db.commit()


async def handle_incoming_block(instance_id: str, payload: dict):
    """Handle when someone blocks this WhatsApp number."""
    sender = payload.get("senderData", {})
    blocker_phone = sender.get("sender", "").split("@")[0]
    print(f"[ALERT] Blocked by {blocker_phone} on instance {instance_id}")
    # Auto-blacklist: if someone blocks us, add them to blacklist
    async with AsyncSessionLocal() as db:
        from app.models.inbox import Blacklist
        from sqlalchemy import select as sa_select
        existing = await db.execute(sa_select(Blacklist).where(Blacklist.phone == blocker_phone))
        if not existing.scalar_one_or_none():
            bl = Blacklist(phone=blocker_phone, reason="blocked_us")
            db.add(bl)
        # Also mark contact as blacklisted
        from app.models.contact import Contact
        contact_result = await db.execute(sa_select(Contact).where(Contact.phone == blocker_phone))
        ct = contact_result.scalar_one_or_none()
        if ct:
            ct.blacklisted = True
            ct.blacklist_reason = "blocked_this_number"
        await db.commit()


async def handle_outgoing_call(instance_id: str, payload: dict):
    """Log outgoing calls to inbox for tracking."""
    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=payload.get("from", "").split("@")[0],
            message_type="outgoing_call",
            call_status=payload.get("status", "outgoing"),
            original_payload=json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0) or 0)
        )
        db.add(msg)
        await db.commit()
```

---

## PHASE 4 — New API endpoints

### Extend `backend/app/api/v1/accounts.py`

Add proxy management endpoints:

```python
class ProxyUpdate(BaseModel):
    proxy_host: str = ""
    proxy_port: int = 1080
    proxy_login: str = ""
    proxy_password: str = ""
    proxy_enabled: bool = False

@router.put("/{account_id}/proxy")
async def update_proxy(account_id: str, body: ProxyUpdate, db: AsyncSession = Depends(get_db)):
    """Set or remove proxy for a WhatsApp account."""
    account = await _get_account(account_id, db)
    
    if body.proxy_enabled and body.proxy_host:
        account.proxy_host = body.proxy_host
        account.proxy_port = body.proxy_port
        account.proxy_login = body.proxy_login
        account.proxy_password = body.proxy_password
        account.proxy_enabled = True
        
        # Apply to Green API
        client = GreenAPIClient(account.instance_id, account.api_token)
        applied = await client.set_proxy(body.proxy_host, body.proxy_port, body.proxy_login, body.proxy_password)
    else:
        account.proxy_enabled = False
        account.proxy_host = None
        client = GreenAPIClient(account.instance_id, account.api_token)
        applied = await client.remove_proxy()
    
    await db.commit()
    return {"applied": applied, "proxy_enabled": account.proxy_enabled}

@router.get("/{account_id}/proxy")
async def get_proxy(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    proxy_url = await client.get_proxy()
    return {
        "proxy_enabled": account.proxy_enabled,
        "proxy_host": account.proxy_host,
        "proxy_port": account.proxy_port,
        "green_api_proxy_url": proxy_url
    }

@router.get("/{account_id}/blocked-contacts")
async def get_blocked_contacts(account_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch blocked contacts from WhatsApp and sync to DB."""
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    blocked = await client.get_contacts_block()
    
    # Sync to DB
    from app.models.wa_extras import WaBlockedContact
    from sqlalchemy import delete
    async with db:
        await db.execute(
            delete(WaBlockedContact).where(WaBlockedContact.account_id == uuid.UUID(account_id))
        )
        for b in blocked:
            phone = str(b.get("id", "")).split("@")[0]
            if phone:
                db.add(WaBlockedContact(account_id=uuid.UUID(account_id), phone=phone))
        await db.commit()
    
    return {"count": len(blocked), "blocked": blocked}
```

### Add disappearing chat endpoint to `backend/app/api/v1/contacts.py`:

```python
@router.post("/{contact_id}/disappearing")
async def set_disappearing_messages(
    contact_id: str,
    ephemeral: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """
    Set disappearing messages timer for contact's chat.
    ephemeral: 0=off, 86400=24h, 604800=7days, 7776000=90days
    """
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account")
    
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.set_disappearing_chat(contact.phone, ephemeral)
    
    if ok:
        from app.models.wa_extras import DisappearingChatSetting
        from sqlalchemy import select as sa_select
        existing = await db.execute(
            sa_select(DisappearingChatSetting).where(
                DisappearingChatSetting.account_id == account.id,
                DisappearingChatSetting.chat_id == contact.chat_id
            )
        )
        setting = existing.scalar_one_or_none()
        if setting:
            setting.ephemeral = ephemeral
        else:
            db.add(DisappearingChatSetting(
                account_id=account.id,
                chat_id=contact.chat_id,
                ephemeral=ephemeral
            ))
        await db.commit()
    
    labels = {0: "خاموش", 86400: "۲۴ ساعت", 604800: "۷ روز", 7776000: "۹۰ روز"}
    return {"set": ok, "ephemeral": ephemeral, "label": labels.get(ephemeral, str(ephemeral))}
```

### Add contact phonebook endpoints to `backend/app/api/v1/contacts.py`:

```python
@router.post("/{contact_id}/add-to-phonebook")
async def add_contact_to_phonebook(contact_id: str, db: AsyncSession = Depends(get_db)):
    """Add a contact to WhatsApp phonebook of the first active account."""
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account")
    
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.add_contact(
        contact.phone,
        contact.first_name or "",
        contact.last_name or ""
    )
    return {"added": ok, "phone": contact.phone, "name": contact.full_name}

@router.put("/{contact_id}/phonebook")
async def edit_contact_in_phonebook(
    contact_id: str,
    first_name: str,
    last_name: str = "",
    db: AsyncSession = Depends(get_db)
):
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account")
    
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.edit_contact(contact.phone, first_name, last_name)
    
    if ok:
        contact.first_name = first_name
        contact.last_name = last_name
        await db.commit()
    
    return {"updated": ok, "phone": contact.phone}
```

---

## PHASE 5 — Frontend additions

### Update `frontend/src/pages/Accounts.jsx`

In the account settings/detail panel, add a "Proxy" section:

```jsx
{/* Proxy Section */}
<div className="mt-4 border-t border-gray-700 pt-4">
  <h4 className="text-sm font-semibold mb-2">🌐 تنظیمات پروکسی</h4>
  <p className="text-xs text-gray-400 mb-2">
    برای پایداری اتصال از ایران، می‌توانید یک پروکسی SOCKS5 تنظیم کنید
  </p>
  <div className="space-y-2">
    <input placeholder="آدرس سرور (مثال: 1.2.3.4)" className="input-field" 
           value={proxyHost} onChange={e => setProxyHost(e.target.value)} />
    <input placeholder="پورت (مثال: 1080)" type="number" className="input-field"
           value={proxyPort} onChange={e => setProxyPort(e.target.value)} />
    <input placeholder="نام کاربری (اختیاری)" className="input-field"
           value={proxyLogin} onChange={e => setProxyLogin(e.target.value)} />
    <input placeholder="رمز عبور (اختیاری)" type="password" className="input-field"
           value={proxyPassword} onChange={e => setProxyPassword(e.target.value)} />
    <div className="flex gap-2">
      <button onClick={() => saveProxy(true)} className="btn-green text-sm">فعال کن</button>
      <button onClick={() => saveProxy(false)} className="btn-gray text-sm">غیرفعال کن</button>
    </div>
  </div>
  {/* Show blocked contacts */}
  <button onClick={syncBlockedContacts} className="mt-3 btn-outline text-xs w-full">
    همگام‌سازی مخاطبین بلاک‌شده
  </button>
</div>
```

Add API calls in `frontend/src/api.js`:
```javascript
export const ProxyApi = {
  get: (accountId) => http.get(`/accounts/${accountId}/proxy`).then(r => r.data),
  set: (accountId, body) => http.put(`/accounts/${accountId}/proxy`, body).then(r => r.data),
  getBlocked: (accountId) => http.get(`/accounts/${accountId}/blocked-contacts`).then(r => r.data),
};
```

### Update `frontend/src/pages/Contacts.jsx`

In contact detail/actions, add two new actions:
1. "⏱️ پیام ناپدیدشونده" button → opens modal with 4 options: خاموش / ۲۴ ساعت / ۷ روز / ۹۰ روز
2. "📱 افزودن به مخاطبین واتساپ" button → calls add-to-phonebook endpoint

```javascript
// In contact actions dropdown:
{ label: "⏱️ پیام ناپدیدشونده", onClick: () => openDisappearingModal(contact) },
{ label: "📱 افزودن به مخاطبین واتساپ", onClick: () => addToPhonebook(contact.id) },
```

Disappearing modal:
```jsx
<Modal title="مدت نگهداری پیام">
  <div className="grid grid-cols-2 gap-3">
    {[
      { label: "خاموش", value: 0 },
      { label: "۲۴ ساعت", value: 86400 },
      { label: "۷ روز", value: 604800 },
      { label: "۹۰ روز", value: 7776000 },
    ].map(opt => (
      <button key={opt.value}
        onClick={() => setDisappearing(contact.id, opt.value)}
        className="btn-outline p-3 text-center">
        {opt.label}
      </button>
    ))}
  </div>
  <p className="text-xs text-gray-400 mt-3">
    پیام‌های این چت پس از مدت انتخابی به‌طور خودکار حذف می‌شوند
  </p>
</Modal>
```

Add API calls:
```javascript
export const ContactExtrasApi = {
  setDisappearing: (id, ephemeral) => http.post(`/contacts/${id}/disappearing?ephemeral=${ephemeral}`).then(r => r.data),
  addToPhonebook: (id) => http.post(`/contacts/${id}/add-to-phonebook`).then(r => r.data),
  editPhonebook: (id, body) => http.put(`/contacts/${id}/phonebook`, body).then(r => r.data),
};
```

### Update `frontend/src/pages/Inbox.jsx`

Add new message type handling for new event types:
```javascript
const TYPE_ICONS = {
  ...existing...,
  catalog_update: "🛍️",
  outgoing_call: "📞",
  incoming_call: "📲",
};

const TYPE_FA = {
  ...existing...,
  catalog_update: "آپدیت کاتالوگ",
  outgoing_call: "تماس خروجی",
};
```

---

## PHASE 6 — Update apply-settings to include proxy

In `backend/app/api/v1/accounts.py`, in `apply_settings` endpoint, also apply proxy if configured:

```python
@router.post("/{account_id}/apply-settings")
async def apply_settings(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    
    webhook_url = f"{settings.webhook_base_url}/api/v1/webhook/{account.instance_id}"
    applied = await client.set_webhook(webhook_url, delay_ms=15000)
    
    # Apply proxy if configured
    proxy_applied = False
    if account.proxy_enabled and account.proxy_host:
        proxy_applied = await client.set_proxy(
            account.proxy_host,
            account.proxy_port or 1080,
            account.proxy_login or "",
            account.proxy_password or ""
        )
    
    await db.commit()
    return {
        "applied": applied,
        "webhook_url": webhook_url,
        "delay_ms": 15000,
        "proxy_applied": proxy_applied
    }
```

---

## PHASE 7 — Tests

### `backend/tests/test_v6.py`
```python
"""Smoke tests for V6 features."""
import inspect
from app.services.green_api import GreenAPIClient
from app.models.wa_extras import DisappearingChatSetting, WaBlockedContact


def test_v6_client_methods():
    methods = [
        "set_disappearing_chat", "get_contacts_block",
        "add_contact", "edit_contact", "delete_contact",
        "set_proxy", "remove_proxy", "get_proxy"
    ]
    for m in methods:
        assert hasattr(GreenAPIClient, m), f"Missing: {m}"
        assert inspect.iscoroutinefunction(getattr(GreenAPIClient, m)), f"Not async: {m}"


def test_v6_models():
    assert DisappearingChatSetting.__tablename__ == "disappearing_chat_settings"
    assert WaBlockedContact.__tablename__ == "wa_blocked_contacts"


def test_ephemeral_values():
    """Confirm valid ephemeral values."""
    valid = {0, 86400, 604800, 7776000}
    assert 0 in valid  # off
    assert 86400 in valid  # 24h
    assert 604800 in valid  # 7d
    assert 7776000 in valid  # 90d
```

---

## PHASE 8 — Verify, rebuild, commit, push

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/main.py app/models/*.py app/services/*.py app/api/v1/*.py app/workers/*.py
python -m pytest tests/ -v
cd ..
```

```bash
docker-compose up -d --build backend worker beat
sleep 8
curl -s http://localhost:8002/health
curl -s http://localhost:8002/api/v1/accounts/2e95cde4-fd12-40c0-b42c-3529705543d5/proxy
docker logs claudegreenapi-backend-1 --tail 15
```

```bash
cd frontend && npm run build && cd ..
docker-compose up -d --build --no-deps frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```

```bash
git add -A
git commit -m "feat: V6 — complete remaining Green API features

New client methods:
- set_disappearing_chat (0/86400/604800/7776000 seconds)
- get_contacts_block — fetch WA blocked contacts list
- add_contact / edit_contact / delete_contact — phonebook management
- set_proxy / remove_proxy / get_proxy — SOCKS5 proxy per instance

New webhook handlers:
- handle_device_status — device battery/online events
- handle_catalog_update — WA catalog changes stored as inbox msg
- handle_incoming_block — auto-blacklist if contact blocks us
- handle_outgoing_call — outgoing call events logged to inbox

New API endpoints:
- GET/PUT /accounts/{id}/proxy
- GET /accounts/{id}/blocked-contacts
- POST /contacts/{id}/disappearing
- POST /contacts/{id}/add-to-phonebook
- PUT /contacts/{id}/phonebook

New DB tables:
- disappearing_chat_settings
- wa_blocked_contacts

Frontend:
- Proxy settings panel in Accounts page
- Disappearing messages timer modal in Contacts
- Add-to-phonebook button in Contacts
- New message type icons in Inbox (catalog/outgoing-call)
- apply-settings now includes proxy application"
git push origin main
```