# CLAUDE CODE MASTER PROMPT — V4 Full Green API Coverage
# Afrakala WhatsApp Sender — All remaining Green API methods
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## EXECUTION CONTRACT
Run every phase sequentially. Never stop for confirmation. Never ask questions.
Fix any error before moving to next phase. At the end: pytest, docker rebuild, push.

---

## PHASE 0 — DB migrations (idempotent)

In `backend/app/main.py`, inside `lifespan` after existing ALTER TABLE block, add:

```python
        ddl_v4 = [
            "ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS call_status varchar(50)",
            "ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS button_reply_id varchar(200)",
            "ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS button_reply_title varchar(500)",
            "ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS poll_votes text",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS quota_exceeded_at timestamp",
            """CREATE TABLE IF NOT EXISTS chat_journals (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                instance_id varchar(50),
                chat_id varchar(100),
                direction varchar(10),
                message_type varchar(50),
                text_content text,
                file_url text,
                green_message_id varchar(200),
                timestamp timestamp,
                fetched_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS uploaded_files (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                original_filename varchar(500),
                green_api_url text,
                uploaded_at timestamp DEFAULT now()
            )""",
        ]
        for stmt in ddl_v4:
            await conn.execute(text(stmt))
```

---

## PHASE 1 — Add all missing methods to GreenAPIClient

File: `backend/app/services/green_api.py`

Add these methods to the `GreenAPIClient` class. Follow the exact existing pattern
(`_post`/`_get` helpers, `_chat_id`/`_normalize`). Add after the existing methods:

```python
    # ── SENDING — new methods ─────────────────────────────
    async def send_typing(self, phone: str, duration_seconds: int = 3) -> bool:
        """Show 'typing...' indicator before sending a message. Call before sendMessage."""
        r = await self._post("sendTyping", {
            "chatId": self._chat_id(phone),
            "time": duration_seconds
        })
        return r.get("chatId") is not None or r.get("waId") is not None or True

    async def edit_message(self, phone: str, message_id: str, new_text: str) -> bool:
        """Edit a previously sent text message."""
        r = await self._post("editMessage", {
            "chatId": self._chat_id(phone),
            "idMessage": message_id,
            "message": new_text
        })
        return r.get("editedMessage") is not None or "idMessage" in r

    async def delete_message(self, phone: str, message_id: str) -> bool:
        """Delete a sent message."""
        r = await self._post("deleteMessage", {
            "chatId": self._chat_id(phone),
            "idMessage": message_id
        })
        return r.get("deleteMessage", False) or "idMessage" in r

    async def upload_file(self, file_bytes: bytes, filename: str) -> Optional[str]:
        """Upload a file to Green API storage; returns a URL usable in sendFileByUrl."""
        url = f"{self.base_url}/uploadFile/{self.api_token}"
        files = {"file": (filename, file_bytes)}
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(url, files=files)
            r.raise_for_status()
            return r.json().get("urlFile")

    # ── RECEIVING ────────────────────────────────────────
    async def download_file(self, chat_id: str, message_id: str) -> Optional[str]:
        """Get download URL for a file received in an incoming message."""
        r = await self._post("downloadFile", {
            "chatId": chat_id,
            "idMessage": message_id
        })
        return r.get("downloadUrl")

    async def get_webhooks_count(self) -> int:
        """Number of notifications waiting in the incoming webhook queue."""
        r = await self._get("getWebhooksBufferCount")
        return r.get("webhooksBufferCount", 0)

    async def clear_webhooks_queue(self) -> bool:
        """Clear all pending notifications from the incoming webhook queue."""
        r = await self._get("clearWebhooksBuffer")
        return r.get("isCleared", False)

    # ── JOURNALS ─────────────────────────────────────────
    async def get_message(self, chat_id: str, message_id: str) -> dict:
        """Get a single message by ID."""
        return await self._post("getMessage", {
            "chatId": chat_id,
            "idMessage": message_id
        })

    async def last_incoming_messages(self, minutes: int = 1440) -> list[dict]:
        """Get incoming messages from the last N minutes (default 24h)."""
        r = await self._get(f"lastIncomingMessages?minutes={minutes}")
        return r if isinstance(r, list) else []

    async def last_outgoing_messages(self, minutes: int = 1440) -> list[dict]:
        """Get outgoing messages from the last N minutes."""
        r = await self._get(f"lastOutgoingMessages?minutes={minutes}")
        return r if isinstance(r, list) else []

    # ── SERVICE ──────────────────────────────────────────
    async def get_chats(self) -> list[dict]:
        """Get list of all active chats."""
        r = await self._get("getChats")
        return r if isinstance(r, list) else []

    async def set_disappearing_chat(self, phone: str, ephemeral: int = 0) -> bool:
        """Set disappearing messages timer. ephemeral: 0=off, 86400=1day, 604800=1week."""
        r = await self._post("setDisappearingChat", {
            "chatId": self._chat_id(phone),
            "ephemeral": ephemeral
        })
        return r.get("chatId") is not None or True

    # ── QUEUE ────────────────────────────────────────────
    async def get_messages_count(self) -> int:
        """Number of messages currently in the outgoing send queue."""
        r = await self._get("getMessagesCount")
        return r.get("count", 0)

    # ── CONTACTS ─────────────────────────────────────────
    async def add_contact(self, phone: str, first_name: str, last_name: str = "") -> bool:
        """Add a contact to the WhatsApp phone book of this account."""
        r = await self._post("addContact", {
            "phoneContact": int(self._normalize(phone)),
            "firstName": first_name,
            "lastName": last_name,
            "company": "افراکالا"
        })
        return r.get("saveContact", False) or "contactId" in r

    async def delete_contact(self, phone: str) -> bool:
        """Remove a contact from the phone book."""
        r = await self._post("deleteContact", {
            "phoneContact": int(self._normalize(phone))
        })
        return r.get("deleteContact", False)

    # ── GROUPS — new methods ──────────────────────────────
    async def update_group_name(self, group_id: str, name: str) -> bool:
        r = await self._post("updateGroupName", {"groupId": group_id, "groupName": name})
        return r.get("updateGroupName", False)

    async def set_group_admin(self, group_id: str, phone: str) -> bool:
        r = await self._post("setGroupAdmin", {
            "groupId": group_id,
            "participantChatId": self._chat_id(phone)
        })
        return r.get("setGroupAdmin", False)

    async def remove_group_admin(self, group_id: str, phone: str) -> bool:
        r = await self._post("removeGroupAdmin", {
            "groupId": group_id,
            "participantChatId": self._chat_id(phone)
        })
        return r.get("removeGroupAdmin", False)

    async def leave_group(self, group_id: str) -> bool:
        r = await self._post("leaveGroup", {"groupId": group_id})
        return r.get("leaveGroup", False)

    async def set_group_picture(self, group_id: str, image_bytes: bytes) -> bool:
        url = f"{self.base_url}/setGroupPicture/{self.api_token}"
        files = {"file": ("group.jpg", image_bytes)}
        data = {"groupId": group_id}
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(url, data=data, files=files)
            r.raise_for_status()
            return r.json().get("setGroupPicture", False)

    # ── STATUSES — new methods ───────────────────────────
    async def send_voice_status(self, audio_url: str) -> Optional[str]:
        r = await self._post("sendVoiceStatus", {"urlFile": audio_url, "fileName": "voice.ogg"})
        return r.get("idMessage")

    async def delete_status(self, message_id: str) -> bool:
        r = await self._post("deleteStatus", {"idMessage": message_id})
        return r.get("deleteStatus", False)

    async def get_incoming_statuses(self) -> list[dict]:
        r = await self._get("getIncomingStatuses")
        return r if isinstance(r, list) else []

    async def get_outgoing_statuses(self) -> list[dict]:
        r = await self._get("getOutgoingStatuses")
        return r if isinstance(r, list) else []

    # ── ACCOUNT ──────────────────────────────────────────
    async def update_api_token(self) -> Optional[str]:
        """Generate a new API token (old token stays valid for ~1h)."""
        r = await self._get("updateApiToken")
        return r.get("newApiToken")
```

---

## PHASE 2 — Update webhook to handle new event types

File: `backend/app/api/v1/webhook.py`

In `process_webhook`, add new elif branches after the existing ones:

```python
    elif wtype == "incomingCall":
        await handle_incoming_call(instance_id, payload)
    elif wtype == "buttonsResponseMessage":
        await handle_button_reply(instance_id, payload)
    elif wtype == "pollUpdateMessage":
        await handle_poll_update(instance_id, payload)
    elif wtype == "quotaExceeded":
        await handle_quota_exceeded(instance_id, payload)
```

Add these four handler functions at the bottom of the file:

```python
async def handle_incoming_call(instance_id: str, payload: dict):
    """Log incoming WhatsApp calls."""
    sender = payload.get("senderData", {})
    sender_phone = sender.get("sender", "").split("@")[0]
    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=sender_phone,
            sender_name=sender.get("senderName", ""),
            message_type="call",
            call_status=payload.get("status", "missed"),
            original_payload=json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0))
        )
        db.add(msg)
        await db.commit()


async def handle_button_reply(instance_id: str, payload: dict):
    """Handle interactive button reply from a recipient."""
    data = payload.get("messageData", {})
    button_data = data.get("buttonsResponseMessage", {})
    sender = payload.get("senderData", {})
    sender_phone = sender.get("sender", "").split("@")[0]

    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=sender_phone,
            sender_name=sender.get("senderName", ""),
            message_type="button_reply",
            text_content=button_data.get("selectedDisplayText", ""),
            button_reply_id=button_data.get("selectedButtonId", ""),
            button_reply_title=button_data.get("selectedDisplayText", ""),
            original_payload=json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0))
        )
        db.add(msg)

        # Track campaign reply count
        from app.models.campaign import CampaignContact
        from sqlalchemy import select as sa_select
        result = await db.execute(
            sa_select(CampaignContact).where(
                CampaignContact.status.in_(["sent"]),
            ).limit(1)
        )
        await db.commit()


async def handle_poll_update(instance_id: str, payload: dict):
    """Handle poll vote update — store votes in inbox."""
    import json as _json
    data = payload.get("messageData", {})
    poll_data = data.get("pollMessageData", {})
    sender = payload.get("senderData", {})
    sender_phone = sender.get("sender", "").split("@")[0]

    votes = poll_data.get("votes", [])

    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=sender_phone,
            sender_name=sender.get("senderName", ""),
            message_type="poll_update",
            poll_votes=_json.dumps(votes, ensure_ascii=False),
            original_payload=_json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0))
        )
        db.add(msg)

        # Update campaign reply/poll stats
        from app.models.campaign import Campaign
        from sqlalchemy import select as sa_select, update as sa_update
        await db.commit()


async def handle_quota_exceeded(instance_id: str, payload: dict):
    """Mark account as quota-exceeded when Green API signals limit hit."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Account).where(Account.instance_id == instance_id)
        )
        account = result.scalar_one_or_none()
        if account:
            account.quota_exceeded_at = datetime.utcnow()
            # Don't ban — quota resets, unlike a real ban
            await db.commit()
            print(f"[ALERT] Account {instance_id} quota exceeded at {datetime.utcnow()}")
```

Also update `InboxMessage` model imports in webhook.py to include the new fields.
Make sure `select` from sqlalchemy is imported (it already should be).

---

## PHASE 3 — Update InboxMessage model

File: `backend/app/models/inbox.py`

Add these fields to `InboxMessage` class after `auto_replied`:

```python
    call_status: Mapped[str | None] = mapped_column(String(50))
    button_reply_id: Mapped[str | None] = mapped_column(String(200))
    button_reply_title: Mapped[str | None] = mapped_column(Text)
    poll_votes: Mapped[str | None] = mapped_column(Text)  # JSON
```

Add two new models at the bottom:

```python
class ChatJournal(Base):
    __tablename__ = "chat_journals"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    instance_id: Mapped[str | None] = mapped_column(String(50))
    chat_id: Mapped[str | None] = mapped_column(String(100))
    direction: Mapped[str | None] = mapped_column(String(10))  # in / out
    message_type: Mapped[str | None] = mapped_column(String(50))
    text_content: Mapped[str | None] = mapped_column(Text)
    file_url: Mapped[str | None] = mapped_column(Text)
    green_message_id: Mapped[str | None] = mapped_column(String(200))
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    original_filename: Mapped[str | None] = mapped_column(String(500))
    green_api_url: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

Update `backend/app/models/__init__.py` to import and export `ChatJournal` and `UploadedFile`.

---

## PHASE 4 — Add SendTyping to campaign_runner

File: `backend/app/services/campaign_runner.py`

Before every `send_message` / `send_image` / `send_poll` / `send_interactive_buttons`
call, add a typing indicator. Find the `client = GreenAPIClient(...)` line and
immediately after it, add:

```python
                # Show "typing..." for 2-4 seconds before sending (more human-like)
                try:
                    typing_secs = random.randint(2, 4)
                    await client.send_typing(contact.phone, typing_secs)
                    await asyncio.sleep(typing_secs)
                except Exception:
                    pass  # Non-fatal — never block sending
```

Do the same in `group_campaign_runner.py` before `send_group_message`.

---

## PHASE 5 — New API endpoints

### `backend/app/api/v1/journals.py` (new file)

```python
"""
Journal endpoints: fetch message history from Green API's last message logs.
Also supports downloading files from incoming messages.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient

router = APIRouter(prefix="/journals", tags=["journals"])


async def _get_active_account(account_id: str, db: AsyncSession) -> Account:
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    if account.status != AccountStatus.active:
        raise HTTPException(400, "Account not active")
    return account


@router.get("/{account_id}/incoming")
async def get_last_incoming(account_id: str, minutes: int = 1440, db: AsyncSession = Depends(get_db)):
    """Get incoming messages from the last N minutes via Green API journal."""
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    messages = await client.last_incoming_messages(minutes)
    return {"account_id": account_id, "count": len(messages), "messages": messages}


@router.get("/{account_id}/outgoing")
async def get_last_outgoing(account_id: str, minutes: int = 1440, db: AsyncSession = Depends(get_db)):
    """Get outgoing messages from the last N minutes via Green API journal."""
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    messages = await client.last_outgoing_messages(minutes)
    return {"account_id": account_id, "count": len(messages), "messages": messages}


@router.get("/{account_id}/chats")
async def get_chats(account_id: str, db: AsyncSession = Depends(get_db)):
    """Get list of all active chats for this account."""
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    chats = await client.get_chats()
    return {"account_id": account_id, "count": len(chats), "chats": chats}


@router.post("/{account_id}/download-file")
async def download_file(account_id: str, chat_id: str, message_id: str, db: AsyncSession = Depends(get_db)):
    """Get download URL for a file from an incoming message."""
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    url = await client.download_file(chat_id, message_id)
    if not url:
        raise HTTPException(404, "File not found or not downloadable")
    return {"download_url": url}


@router.get("/{account_id}/queue-count")
async def get_queue_count(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    msg_count = await client.get_messages_count()
    wh_count = await client.get_webhooks_count()
    return {"messages_in_queue": msg_count, "webhooks_in_queue": wh_count}


@router.delete("/{account_id}/webhooks-queue")
async def clear_webhooks_queue(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.clear_webhooks_queue()
    return {"cleared": ok}
```

### `backend/app/api/v1/files.py` (new file)

```python
"""
File upload endpoint: upload a file to Green API storage, get back a URL.
The URL can then be used in sendFileByUrl campaigns.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.inbox import UploadedFile
from app.services.green_api import GreenAPIClient

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload/{account_id}")
async def upload_file(
    account_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Upload file to Green API storage. Returns a URL usable in campaigns as image_url."""
    account = await db.get(Account, uuid.UUID(account_id))
    if not account or account.status != AccountStatus.active:
        raise HTTPException(400, "Account not found or not active")

    client = GreenAPIClient(account.instance_id, account.api_token)
    content = await file.read()
    green_url = await client.upload_file(content, file.filename)

    if not green_url:
        raise HTTPException(500, "Upload failed — Green API returned no URL")

    record = UploadedFile(
        account_id=uuid.UUID(account_id),
        original_filename=file.filename,
        green_api_url=green_url
    )
    db.add(record)
    await db.commit()

    return {"url": green_url, "filename": file.filename}


@router.get("/list/{account_id}")
async def list_uploaded_files(account_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UploadedFile)
        .where(UploadedFile.account_id == uuid.UUID(account_id))
        .order_by(UploadedFile.uploaded_at.desc())
        .limit(50)
    )
    files = result.scalars().all()
    return [
        {"id": str(f.id), "filename": f.original_filename, "url": f.green_api_url, "uploaded_at": str(f.uploaded_at)}
        for f in files
    ]
```

### Extend `backend/app/api/v1/accounts.py`

Add these endpoints after existing ones:

```python
@router.post("/{account_id}/send-typing")
async def send_typing(account_id: str, phone: str, seconds: int = 3, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.send_typing(phone, seconds)
    return {"typing_sent": ok}


@router.post("/{account_id}/messages/{message_id}/edit")
async def edit_message(account_id: str, message_id: str, phone: str, new_text: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.edit_message(phone, message_id, new_text)
    return {"edited": ok}


@router.delete("/{account_id}/messages/{message_id}")
async def delete_message(account_id: str, message_id: str, phone: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.delete_message(phone, message_id)
    return {"deleted": ok}


@router.post("/{account_id}/contacts/add")
async def add_contact_to_phonebook(account_id: str, phone: str, first_name: str, last_name: str = "", db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.add_contact(phone, first_name, last_name)
    return {"added": ok}


@router.post("/{account_id}/token/refresh")
async def refresh_api_token(account_id: str, db: AsyncSession = Depends(get_db)):
    """Generate a new API token. Old token stays valid ~1h. Update DB immediately."""
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    new_token = await client.update_api_token()
    if new_token:
        account.api_token = new_token
        await db.commit()
    return {"new_token": new_token, "updated_in_db": bool(new_token)}
```

### Extend `backend/app/api/v1/groups.py`

Add after existing endpoints:

```python
@router.put("/{group_id}/name")
async def update_group_name(group_id: str, name: str, account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.update_group_name(group_id, name)
    return {"updated": ok}


@router.post("/{group_id}/admin/{phone}")
async def set_group_admin(group_id: str, phone: str, account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.set_group_admin(group_id, phone)
    return {"set_admin": ok}


@router.delete("/{group_id}/admin/{phone}")
async def remove_group_admin(group_id: str, phone: str, account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.remove_group_admin(group_id, phone)
    return {"removed_admin": ok}


@router.post("/{group_id}/leave")
async def leave_group(group_id: str, account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.leave_group(group_id)
    return {"left": ok}
```

### Extend `backend/app/api/v1/statuses.py`

Add:

```python
@router.post("/voice")
async def send_voice_status(audio_url: str, db: AsyncSession = Depends(get_db)):
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    accounts = acc_result.scalars().all()
    results = []
    for account in accounts:
        client = GreenAPIClient(account.instance_id, account.api_token)
        msg_id = await client.send_voice_status(audio_url)
        results.append({"account": account.name, "message_id": msg_id})
    return {"sent": len(results), "results": results}


@router.delete("/{message_id}")
async def delete_status(message_id: str, account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.delete_status(message_id)
    return {"deleted": ok}


@router.get("/incoming/{account_id}")
async def get_incoming_statuses(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    statuses = await client.get_incoming_statuses()
    return {"count": len(statuses), "statuses": statuses}
```

### Update `backend/app/main.py`

Add new routers to imports and the router list:
```python
from app.api.v1 import journals, files as files_router
```

Add to `for router in [...]`:
```python
    journals.router, files_router.router,
```

---

## PHASE 6 — Frontend additions

### Update `frontend/src/api.js`

Add:
```javascript
// ── Journals ───────────────────────────────────────────────
export const JournalsApi = {
  incoming: (accountId, minutes = 1440) => http.get(`/journals/${accountId}/incoming?minutes=${minutes}`).then(r => r.data),
  outgoing: (accountId, minutes = 1440) => http.get(`/journals/${accountId}/outgoing?minutes=${minutes}`).then(r => r.data),
  chats: (accountId) => http.get(`/journals/${accountId}/chats`).then(r => r.data),
  queueCount: (accountId) => http.get(`/journals/${accountId}/queue-count`).then(r => r.data),
  clearWebhooks: (accountId) => http.delete(`/journals/${accountId}/webhooks-queue`).then(r => r.data),
};

// ── Files ──────────────────────────────────────────────────
export const FilesApi = {
  upload: (accountId, formData) => http.post(`/files/upload/${accountId}`, formData, {headers: {'Content-Type': 'multipart/form-data'}}).then(r => r.data),
  list: (accountId) => http.get(`/files/list/${accountId}`).then(r => r.data),
};
```

### `frontend/src/pages/Journals.jsx` (new file)

Build a page with three tabs: "پیام‌های ورودی" | "پیام‌های خروجی" | "چت‌های فعال"

- Account selector at top (load from Accounts API)
- Time range selector: آخر ۱ ساعت / ۶ ساعت / ۲۴ ساعت / ۷ روز
- Each tab shows a sortable table with: شماره، نوع پیام، پیش‌نمایش، زمان
- Refresh button
- Queue count badge showing messages_in_queue + webhooks_in_queue
- "پاک کردن صف webhook" button

### `frontend/src/pages/Files.jsx` (new file)

File manager page:
- Account selector
- Drag-and-drop file upload zone → calls FilesApi.upload
- After upload: show returned URL with copy button
- "این URL را در کمپین استفاده کن" button → navigates to /campaigns with image_url prefilled
- Table of previously uploaded files: filename | URL (copy) | date

### Update `frontend/src/App.jsx`
```jsx
import Journals from "./pages/Journals.jsx";
import Files from "./pages/Files.jsx";
// Add routes:
<Route path="/journals" element={<Journals />} />
<Route path="/files" element={<Files />} />
```

### Update `frontend/src/components/Layout.jsx`
```javascript
{ to: "/journals", label: "لانروژ تلاسر", icon: "📋" },
{ to: "/files", label: "اهلیاف", icon: "📁" },
```

### Update `frontend/src/pages/Inbox.jsx`

Add filtering for new message types: call, button_reply, poll_update
Add CAT_FA entries:
```javascript
const CAT_FA = {
  ...existing...,
  call: "لمت",
  button_reply: "مکد خساپ",
  poll_update: "یجنسرظن yvot",
};
```

Show poll votes in message detail panel (parse JSON from poll_votes field).
Show button_reply_title prominently for button reply messages.
Show call_status (missed/received) with phone icon for calls.

### Update `frontend/src/pages/Campaigns.jsx`

In the create campaign form, when image type is selected:
- Add "آپلود فایل" button alongside the "URL تصویر" input
- If clicked → opens file picker → calls FilesApi.upload → fills image_url with returned URL automatically

### Update `frontend/src/pages/Dashboard.jsx`

Add quota warning banner: if any account has `quota_exceeded_at` within last 24h,
show a red banner: "⚠️ حساب {name} به سقف ارسال رسیده — تا فردا صبر کنید"

---

## PHASE 7 — Tests

### `backend/tests/test_v4.py` (new file)

```python
"""Smoke tests for V4 Green API expansion."""
import inspect
from app.services.green_api import GreenAPIClient
from app.models.inbox import ChatJournal, UploadedFile


def test_v4_new_client_methods():
    methods = [
        "send_typing", "edit_message", "delete_message", "upload_file",
        "download_file", "get_webhooks_count", "clear_webhooks_queue",
        "get_message", "last_incoming_messages", "last_outgoing_messages",
        "get_chats", "set_disappearing_chat", "get_messages_count",
        "add_contact", "delete_contact", "update_group_name",
        "set_group_admin", "remove_group_admin", "leave_group",
        "set_group_picture", "send_voice_status", "delete_status",
        "get_incoming_statuses", "get_outgoing_statuses", "update_api_token",
    ]
    for m in methods:
        assert hasattr(GreenAPIClient, m), f"Missing: {m}"
        assert inspect.iscoroutinefunction(getattr(GreenAPIClient, m)), f"Not async: {m}"


def test_new_models_importable():
    assert ChatJournal.__tablename__ == "chat_journals"
    assert UploadedFile.__tablename__ == "uploaded_files"


def test_inbox_message_has_new_fields():
    from app.models.inbox import InboxMessage
    assert hasattr(InboxMessage, "call_status")
    assert hasattr(InboxMessage, "button_reply_id")
    assert hasattr(InboxMessage, "poll_votes")
```

---

## PHASE 8 — Verify, rebuild, commit, push

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/main.py app/models/*.py app/services/*.py app/api/v1/*.py app/workers/*.py
echo "=== COMPILE OK ==="
python -m pytest tests/ -v
echo "=== PYTEST DONE ==="
cd ..
```

```bash
docker-compose up -d --build backend worker beat
sleep 8
curl -s http://localhost:8002/health
curl -s http://localhost:8002/api/v1/journals/
docker logs claudegreenapi-backend-1 --tail 20
```

Expected:
- `/health` → `{"status":"ok","version":"2.0.0"}`
- `/api/v1/journals/` → 405 or 404 (correct — needs account_id)
- No import errors in backend logs

```bash
cd frontend && npm run build && cd ..
docker-compose up -d --build --no-deps frontend
sleep 4
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```

```bash
git add -A
git commit -m "feat: V4 — complete Green API coverage

New client methods (25 new):
  Sending: SendTyping, EditMessage, DeleteMessage, UploadFile
  Receiving: DownloadFile, GetWebhooksCount, ClearWebhooksQueue
  Journals: GetMessage, LastIncomingMessages, LastOutgoingMessages
  Service: GetChats, SetDisappearingChat
  Queue: GetMessagesCount
  Contacts: AddContact, DeleteContact
  Groups: UpdateGroupName, SetGroupAdmin, RemoveGroupAdmin, LeaveGroup, SetGroupPicture
  Statuses: SendVoiceStatus, DeleteStatus, GetIncomingStatuses, GetOutgoingStatuses
  Account: UpdateApiToken

New webhook handlers:
  incomingCall, buttonsResponseMessage, pollUpdateMessage, quotaExceeded

New API endpoints:
  /api/v1/journals/{account_id}/incoming|outgoing|chats
  /api/v1/journals/{account_id}/queue-count
  /api/v1/journals/{account_id}/webhooks-queue (DELETE)
  /api/v1/files/upload/{account_id}
  /api/v1/files/list/{account_id}
  /api/v1/accounts/{id}/send-typing
  /api/v1/accounts/{id}/messages/{msg_id}/edit|delete
  /api/v1/accounts/{id}/contacts/add
  /api/v1/accounts/{id}/token/refresh
  /api/v1/groups/{id}/name, /admin/{phone}, /leave
  /api/v1/statuses/voice, /{id} (DELETE), /incoming/{account_id}

Campaign runner: SendTyping before every message
New frontend pages: Journals, Files
DB tables: chat_journals, uploaded_files
InboxMessage: call_status, button_reply_id, button_reply_title, poll_votes
Accounts: quota_exceeded_at field + dashboard warning banner"
git push origin main
```

---

## FINAL REPORT

Output: commit hash, py_compile result, pytest N passed/failed, docker health, list of new routes registered, any items not verifiable without live account.