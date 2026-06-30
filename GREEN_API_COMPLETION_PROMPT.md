# CLAUDE CODE PROMPT — Green API Full Coverage Completion
# Afrakala WhatsApp Sender — Close remaining Green API gaps
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Project path: C:\Users\AFRA\Desktop\bots\claudegreenapi

## AUTONOMOUS EXECUTION MODE

Run every phase below to completion without stopping for confirmation. After each
phase, run the listed verification commands. If a verification fails, debug and fix
it before moving to the next phase. Rebuild and restart any Docker services whose
code changed. Do not pause to ask questions — none of these phases require external
credentials or human input. Only stop if you hit a genuine blocker that cannot be
resolved with the information in this file. At the very end: run the full test
suite, commit, push, and give one final summary.

---

## CONTEXT

The backend already implements most of Green API. This prompt closes five specific
gaps:

1. `sendFileByUpload` (direct binary file upload, not URL-based)
2. HTTP polling fallback (`receiveNotification` / `deleteNotification`) for accounts
   without a reachable webhook
3. `unarchiveChat`
4. Wiring local "mark as read" to actually call Green API's `readChat` so the real
   WhatsApp chat updates, not just the local DB flag
5. Handling edited/deleted message events in the webhook

Current running stack (docker-compose): `db`, `redis`, `backend` (host :8002),
`worker`, `beat`, `frontend` (host :3002). `db`/`redis` have no host ports — internal
only. Backend/worker/beat get `DATABASE_URL`/`SYNC_DATABASE_URL`/`REDIS_URL` from
`environment:` overrides in `docker-compose.yml` (service-name URLs), not from `.env`.

---

## PHASE 0 — Idempotent schema migration

The app creates tables with `Base.metadata.create_all` on startup, which does NOT
add columns to tables that already exist. Since the database is already running
with data, new columns below would otherwise cause `column does not exist` errors.

Edit `backend/app/main.py`: add `from sqlalchemy import text` to the imports, and
inside `lifespan`, immediately after `await conn.run_sync(Base.metadata.create_all)`,
add:

```python
        await conn.execute(text("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS polling_enabled boolean DEFAULT false"))
        await conn.execute(text("ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS is_deleted boolean DEFAULT false"))
        await conn.execute(text("ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS edited_text text"))
        await conn.execute(text("ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS original_message_id varchar(200)"))
```

This runs on every backend startup, is a no-op once the columns exist, and requires
no manual DB access or Alembic migration generation.

---

## PHASE 1 — `sendFileByUpload`

### 1a. `backend/app/services/green_api.py`

Add this method to `GreenAPIClient`, near the other send methods:

```python
    async def send_file_upload(self, phone: str, file_bytes: bytes, filename: str, caption: str = "") -> Optional[str]:
        """Send a file from raw bytes via multipart upload (no public URL needed)."""
        url = f"{self.base_url}/sendFileByUpload/{self.api_token}"
        files = {"file": (filename, file_bytes)}
        data = {"chatId": self._chat_id(phone), "caption": caption}
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(url, data=data, files=files)
            r.raise_for_status()
            return r.json().get("idMessage")
```

### 1b. `backend/app/api/v1/contacts.py`

Add `Form` to the existing `from fastapi import ...` line (alongside `UploadFile`,
`File`). Add a new endpoint:

```python
@router.post("/{contact_id}/send-file")
async def send_file_to_contact(
    contact_id: str,
    file: UploadFile = File(...),
    caption: str = Form(""),
    db: AsyncSession = Depends(get_db)
):
    """Send an arbitrary file directly to a contact via multipart upload (no URL hosting needed)."""
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account available")

    client = GreenAPIClient(account.instance_id, account.api_token)
    content = await file.read()
    msg_id = await client.send_file_upload(contact.phone, content, file.filename, caption)
    return {"sent": bool(msg_id), "message_id": msg_id, "via": account.name}
```

---

## PHASE 2 — HTTP polling fallback

For accounts where a public webhook isn't reachable (e.g. local dev without ngrok),
poll Green API directly instead.

### 2a. `backend/app/models/account.py`

Add one field next to `warmup_enabled`:

```python
    polling_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
```

### 2b. `backend/app/services/polling_service.py` (new file)

```python
"""
HTTP polling fallback for accounts without a reachable webhook.
Reuses the exact same payload-processing logic as the webhook route.
"""
from app.services.green_api import GreenAPIClient
from app.api.v1.webhook import process_webhook


async def poll_account_once(account) -> int:
    """Fetch and process a single pending notification for one account.
    Returns 1 if a notification was processed, 0 if the queue was empty."""
    client = GreenAPIClient(account.instance_id, account.api_token)
    notif = await client.receive_notification()
    if not notif:
        return 0

    receipt_id = notif.get("receiptId")
    body = notif.get("body", {})
    try:
        await process_webhook(account.instance_id, body)
    finally:
        if receipt_id is not None:
            await client.delete_notification(receipt_id)
    return 1
```

### 2c. `backend/app/workers/tasks.py`

Add a new task:

```python
@celery_app.task(name="tasks.poll_accounts")
def task_poll_accounts():
    async def _p():
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from app.services.polling_service import poll_account_once
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Account).where(Account.status == AccountStatus.active, Account.polling_enabled == True)
            )
            accounts = result.scalars().all()
        for account in accounts:
            try:
                await poll_account_once(account)
            except Exception as e:
                print(f"[Polling] account {account.name} error: {e}")
    asyncio.run(_p())
```

### 2d. `backend/app/workers/celery_app.py`

Add to `beat_schedule`:

```python
    "poll-accounts": {"task": "tasks.poll_accounts", "schedule": 10.0},
```

### 2e. `backend/app/api/v1/accounts.py`

Extend the existing `AutoReplyUpdate` model with one more optional field:

```python
    polling_enabled: bool | None = None
```

In the `update_auto_reply` handler, add the matching branch (same pattern as the
existing `warmup_enabled` branch):

```python
    if payload.polling_enabled is not None:
        account.polling_enabled = payload.polling_enabled
```

And include it in the returned dict alongside the other fields.

---

## PHASE 3 — `unarchiveChat`

### 3a. `backend/app/services/green_api.py`

Add next to the existing `archive_chat` method:

```python
    async def unarchive_chat(self, phone: str) -> bool:
        r = await self._post("unarchiveChat", {"chatId": self._chat_id(phone)})
        return r.get("isUnarchived", False)
```

### 3b. `backend/app/api/v1/contacts.py`

Add two endpoints (reuse the same "first active account" lookup pattern already
used in `check_bulk` and `contact_history` in this file):

```python
@router.post("/{contact_id}/archive")
async def archive_contact_chat(contact_id: str, db: AsyncSession = Depends(get_db)):
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account available")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.archive_chat(contact.phone)
    return {"archived": ok}


@router.post("/{contact_id}/unarchive")
async def unarchive_contact_chat(contact_id: str, db: AsyncSession = Depends(get_db)):
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account available")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.unarchive_chat(contact.phone)
    return {"unarchived": ok}
```

---

## PHASE 4 — Wire "mark as read" to the real WhatsApp chat

### 4a. `backend/app/api/v1/inbox.py`

Find the existing `POST /inbox/{id}/read` endpoint. Update it so that, in addition
to setting the local `is_read` flag, it also calls Green API's `readChat` (already
implemented as `GreenAPIClient.mark_as_read`) using the account that matches the
message's `instance_id`. The Green API call must be best-effort: if it fails, the
local DB update must still succeed (wrap in try/except, never let a Green API error
block the local read-state update).

Target behavior:

```python
@router.post("/{message_id}/read")
async def mark_inbox_read(message_id: str, db: AsyncSession = Depends(get_db)):
    msg = await db.get(InboxMessage, uuid.UUID(message_id))
    if not msg:
        raise HTTPException(404, "Message not found")

    msg.is_read = True
    await db.commit()

    # Best-effort: also mark the real WhatsApp chat as read via Green API.
    try:
        acc_result = await db.execute(select(Account).where(Account.instance_id == msg.instance_id))
        account = acc_result.scalar_one_or_none()
        if account:
            from app.services.green_api import GreenAPIClient
            client = GreenAPIClient(account.instance_id, account.api_token)
            await client.mark_as_read(msg.sender_phone, msg.original_payload and __import__("json").loads(msg.original_payload).get("idMessage", "") or "")
    except Exception as e:
        print(f"[Inbox] readChat sync failed (non-fatal): {e}")

    return {"id": message_id, "is_read": True}
```

Adapt this to whatever the existing function signature/imports already look like in
the file — keep the existing route path and response shape, just add the best-effort
Green API call as shown. Import `Account` from `app.models.account` if not already
imported in this file.

---

## PHASE 5 — Edited / deleted message handling in the webhook

### 5a. `backend/app/models/inbox.py`

Add three fields to `InboxMessage`, next to `auto_replied`:

```python
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_text: Mapped[str | None] = mapped_column(Text)
    original_message_id: Mapped[str | None] = mapped_column(String(200))
```

### 5b. `backend/app/api/v1/webhook.py`

In `handle_incoming`, Green API's exact JSON shape for edited/deleted events can
vary by account/version, so extract defensively with `.get()` chains and never let
a parsing miss raise an exception — the raw payload is always preserved in
`original_payload` regardless. Update the function as follows:

After the existing `text = (...)` extraction block, add:

```python
    type_message = data.get("typeMessage", "text")
    is_edited = type_message == "editedMessage"
    is_deleted = type_message in ("deletedMessage", "revokedMessage")

    edited_text = None
    original_message_id = None
    if is_edited:
        edited_block = data.get("editedMessageData", {}) or {}
        edited_text = (
            edited_block.get("textMessageData", {}).get("textMessage")
            or edited_block.get("extendedTextMessageData", {}).get("text")
        )
        original_message_id = edited_block.get("stanzaId") or payload.get("idMessage")
        if edited_text:
            text = edited_text
    elif is_deleted:
        deleted_block = data.get("deletedMessageData", {}) or data.get("protocolMessageData", {}) or {}
        original_message_id = deleted_block.get("stanzaId") or payload.get("idMessage")
```

Then, when constructing the `InboxMessage(...)` object, add the three new fields:

```python
            is_deleted=is_deleted,
            edited_text=edited_text,
            original_message_id=original_message_id,
```

Keep every existing field exactly as-is — only add these three.

---

## PHASE 6 — Tests

### `backend/tests/test_polling.py` (new file)

```python
"""Tests for the polling service's notification-processing contract."""
import pytest
from unittest.mock import AsyncMock, patch
from app.services.polling_service import poll_account_once


class FakeAccount:
    instance_id = "1101234567"
    api_token = "fake-token"
    name = "Test Account"


@pytest.mark.asyncio
async def test_poll_account_once_empty_queue():
    with patch("app.services.polling_service.GreenAPIClient") as MockClient:
        instance = MockClient.return_value
        instance.receive_notification = AsyncMock(return_value=None)
        result = await poll_account_once(FakeAccount())
        assert result == 0


@pytest.mark.asyncio
async def test_poll_account_once_processes_and_deletes():
    fake_notif = {"receiptId": 42, "body": {"typeWebhook": "stateInstanceChanged", "stateInstance": "authorized"}}
    with patch("app.services.polling_service.GreenAPIClient") as MockClient, \
         patch("app.services.polling_service.process_webhook", new_callable=AsyncMock) as mock_process:
        instance = MockClient.return_value
        instance.receive_notification = AsyncMock(return_value=fake_notif)
        instance.delete_notification = AsyncMock(return_value=True)

        result = await poll_account_once(FakeAccount())

        assert result == 1
        mock_process.assert_awaited_once_with("1101234567", fake_notif["body"])
        instance.delete_notification.assert_awaited_once_with(42)
```

Add `pytest-mock` is not required (using `unittest.mock` from stdlib is enough).
Ensure `pytest-asyncio` is already in `requirements.txt` (it is).

### `backend/tests/test_green_api.py`

Add one more parametrized case alongside the existing phone-normalization tests to
confirm `send_file_upload` and `unarchive_chat` exist as callable async methods
(signature smoke test, no live network call):

```python
def test_new_methods_exist():
    import inspect
    from app.services.green_api import GreenAPIClient
    assert inspect.iscoroutinefunction(GreenAPIClient.send_file_upload)
    assert inspect.iscoroutinefunction(GreenAPIClient.unarchive_chat)
```

---

## PHASE 7 — Verify, rebuild, and ship

Run every command below in order from the project root
(`C:\Users\AFRA\Desktop\bots\claudegreenapi`). Fix any failure before continuing.

```bash
cd backend
python -m py_compile app/main.py app/models/*.py app/services/*.py app/api/v1/*.py app/workers/*.py
python -m pytest tests/ -v
cd ..
```

```bash
docker-compose up -d --build backend worker beat
sleep 6
curl -s http://localhost:8002/health
curl -s http://localhost:3002/api/v1/dashboard/stats
docker logs claudegreenapi-backend-1 --tail 30
docker logs claudegreenapi-worker-1 --tail 30
docker logs claudegreenapi-beat-1 --tail 15
```

Confirm in the logs:
- backend started with no import errors
- worker connected to redis with no task registration errors (`tasks.poll_accounts`
  should be listed)
- beat shows `poll-accounts` in its schedule

```bash
git add -A
git commit -m "feat: close remaining Green API gaps

- sendFileByUpload: direct binary file upload + /contacts/{id}/send-file endpoint
- HTTP polling fallback (receiveNotification/deleteNotification) for accounts
  without a reachable webhook, reusing the existing webhook processing logic,
  Celery beat task every 10s, per-account polling_enabled toggle
- unarchiveChat + /contacts/{id}/archive and /unarchive endpoints
- Inbox mark-as-read now also calls Green API readChat on the real chat
  (best-effort, never blocks the local DB update)
- Edited/deleted message webhook handling: is_deleted, edited_text,
  original_message_id fields on InboxMessage, defensive payload parsing
- Idempotent ALTER TABLE IF NOT EXISTS migrations on startup for the new columns
- New tests: polling service contract, new client method smoke tests"
git push origin main
```

---

## FINAL REPORT FORMAT

End with a concise summary covering: which phases completed, the verification
output (health check, dashboard stats, log confirmations), test pass/fail counts,
and the final commit hash that was pushed. If anything could not be fully verified
without a live Green API account connected, say so explicitly rather than assuming
it works.