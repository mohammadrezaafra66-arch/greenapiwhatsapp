# CLAUDE CODE MASTER PROMPT V2 — Full Feature Build
# Afrakala WhatsApp Sender Platform
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp

Execute ALL phases sequentially. No stopping.

---

## CONTEXT

B2B WhatsApp bulk messaging platform for Afrakala (Iranian home appliances wholesale).
Uses Green API (REST-based, works with Iranian +98 numbers).
Backend: FastAPI + PostgreSQL + Redis + Celery
All Green API features must be implemented.

---

## PHASE 1 — Project Structure

Create full directory tree:

```
greenapiwhatsapp/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── account.py
│   │   │   ├── campaign.py
│   │   │   ├── contact.py
│   │   │   ├── inbox.py
│   │   │   ├── group.py
│   │   │   ├── template.py
│   │   │   └── status_send.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── account.py
│   │   │   ├── campaign.py
│   │   │   ├── contact.py
│   │   │   └── inbox.py
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── accounts.py
│   │   │       ├── campaigns.py
│   │   │       ├── contacts.py
│   │   │       ├── webhook.py
│   │   │       ├── dashboard.py
│   │   │       ├── inbox.py
│   │   │       ├── groups.py
│   │   │       ├── statuses.py
│   │   │       ├── templates.py
│   │   │       ├── queue.py
│   │   │       └── blacklist.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── green_api.py
│   │   │   ├── gpt_service.py
│   │   │   ├── campaign_runner.py
│   │   │   ├── rate_limiter.py
│   │   │   ├── price_service.py
│   │   │   ├── excel_service.py
│   │   │   ├── warmup_service.py
│   │   │   └── auto_reply.py
│   │   └── workers/
│   │       ├── __init__.py
│   │       ├── celery_app.py
│   │       └── tasks.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic.ini
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## PHASE 2 — .gitignore and .env.example

### `.gitignore`
```
__pycache__/
*.py[cod]
.env
.venv/
venv/
*.log
.DS_Store
node_modules/
.pytest_cache/
celerybeat-schedule
*.sqlite3
htmlcov/
.coverage
```

### `.env.example`
```env
DATABASE_URL=postgresql+asyncpg://afrakala:password@localhost:5432/whatsapp_sender
SYNC_DATABASE_URL=postgresql://afrakala:password@localhost:5432/whatsapp_sender
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk-your-key
PRICING_API_URL=http://192.168.170.8:3000/pricing/amin-hozoor-board
PRICING_CACHE_MINUTES=5
SECRET_KEY=change-this-random-string
BACKEND_URL=http://localhost:8000
WEBHOOK_BASE_URL=http://localhost:8000
DEFAULT_MIN_DELAY=45
DEFAULT_MAX_DELAY=110
DEBUG=true
```

---

## PHASE 3 — requirements.txt

```
fastapi==0.111.0
uvicorn[standard]==0.30.1
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
alembic==1.13.1
psycopg2-binary==2.9.9
celery[redis]==5.4.0
redis==5.0.6
httpx==0.27.0
openai==1.35.0
openpyxl==3.1.4
pandas==2.2.2
python-multipart==0.0.9
pydantic==2.7.4
pydantic-settings==2.3.3
APScheduler==3.10.4
pytz==2024.1
aiofiles==23.2.1
websockets==12.0
```

---

## PHASE 4 — config.py

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://afrakala:password@localhost:5432/whatsapp_sender"
    sync_database_url: str = "postgresql://afrakala:password@localhost:5432/whatsapp_sender"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    pricing_api_url: str = "http://192.168.170.8:3000/pricing/amin-hozoor-board"
    pricing_cache_minutes: int = 5
    secret_key: str = "change-this"
    backend_url: str = "http://localhost:8000"
    webhook_base_url: str = "http://localhost:8000"
    default_min_delay: int = 45
    default_max_delay: int = 110
    debug: bool = True

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
```

---

## PHASE 5 — database.py

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
```

---

## PHASE 6 — ALL Models

### `backend/app/models/account.py`
```python
import uuid, enum
from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, Date, DateTime, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class AccountStatus(str, enum.Enum):
    active = "active"
    banned = "banned"
    disconnected = "disconnected"
    pending = "pending"

class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    instance_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    api_token: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[AccountStatus] = mapped_column(SAEnum(AccountStatus), default=AccountStatus.pending)
    daily_limit: Mapped[int] = mapped_column(Integer, default=50)
    sent_today: Mapped[int] = mapped_column(Integer, default=0)
    received_today: Mapped[int] = mapped_column(Integer, default=0)
    received_yesterday: Mapped[int] = mapped_column(Integer, default=0)
    quick_replies_yesterday: Mapped[int] = mapped_column(Integer, default=0)
    days_active: Mapped[int] = mapped_column(Integer, default=0)
    last_reset_date: Mapped[date | None] = mapped_column(Date)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime)
    ban_reason: Mapped[str | None] = mapped_column(Text)
    warmup_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_reply_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_reply_message: Mapped[str | None] = mapped_column(Text)
    auto_reply_outside_hours: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def computed_daily_limit(self) -> int:
        base = min(self.days_active, 10)
        incoming = min(self.received_yesterday, 20)
        replies = min(self.quick_replies_yesterday * 5, 50)
        return base + incoming + replies
```

### `backend/app/models/contact.py`
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    province: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    segment: Mapped[str | None] = mapped_column(String(50))
    has_whatsapp: Mapped[bool | None] = mapped_column(Boolean)
    whatsapp_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)
    blacklist_reason: Mapped[str | None] = mapped_column(Text)
    last_replied_at: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def full_name(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else self.phone

    @staticmethod
    def normalize_phone(phone: str) -> str | None:
        import re
        phone = re.sub(r"\D", "", str(phone).strip())
        if phone.startswith("0") and len(phone) == 11:
            phone = "98" + phone[1:]
        elif len(phone) == 10 and phone.startswith("9"):
            phone = "98" + phone
        if not re.match(r"^989[0-9]{9}$", phone):
            return None
        return phone

    @property
    def chat_id(self) -> str:
        return f"{self.phone}@c.us"
```

### `backend/app/models/campaign.py`
```python
import uuid, enum
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class CampaignStatus(str, enum.Enum):
    draft = "draft"
    running = "running"
    paused = "paused"
    completed = "completed"

class CampaignType(str, enum.Enum):
    text = "text"
    image = "image"
    poll = "poll"
    interactive_buttons = "interactive_buttons"
    status = "status"

class MessageStatus(str, enum.Enum):
    pending = "pending"
    generating = "generating"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"
    no_whatsapp = "no_whatsapp"

class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(SAEnum(CampaignStatus), default=CampaignStatus.draft)
    campaign_type: Mapped[CampaignType] = mapped_column(SAEnum(CampaignType), default=CampaignType.text)
    message_template: Mapped[str | None] = mapped_column(Text)
    use_gpt: Mapped[bool] = mapped_column(Boolean, default=True)
    gpt_prompt: Mapped[str | None] = mapped_column(Text)
    include_products: Mapped[bool] = mapped_column(Boolean, default=False)
    product_count: Mapped[int] = mapped_column(Integer, default=3)
    # Image campaign
    image_url: Mapped[str | None] = mapped_column(Text)
    # Poll campaign
    poll_question: Mapped[str | None] = mapped_column(String(500))
    poll_options: Mapped[str | None] = mapped_column(Text)  # JSON array
    # Interactive buttons
    button1_text: Mapped[str | None] = mapped_column(String(50))
    button2_text: Mapped[str | None] = mapped_column(String(50))
    button3_text: Mapped[str | None] = mapped_column(String(50))
    footer_text: Mapped[str | None] = mapped_column(String(200))
    schedule_start: Mapped[datetime | None] = mapped_column(DateTime)
    schedule_end: Mapped[datetime | None] = mapped_column(DateTime)
    total_contacts: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    delivered_count: Mapped[int] = mapped_column(Integer, default=0)
    read_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

class CampaignContact(Base):
    __tablename__ = "campaign_contacts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id"), index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    status: Mapped[MessageStatus] = mapped_column(SAEnum(MessageStatus), default=MessageStatus.pending, index=True)
    generated_message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    green_api_message_id: Mapped[str | None] = mapped_column(String(200))
    delivery_status: Mapped[str | None] = mapped_column(String(50))  # sent/delivered/read/failed
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

class HourRateLimit(Base):
    __tablename__ = "hour_rate_limits"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hour_start: Mapped[int] = mapped_column(Integer)
    hour_end: Mapped[int] = mapped_column(Integer)
    max_per_hour: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

### `backend/app/models/inbox.py`
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class InboxMessage(Base):
    __tablename__ = "inbox_messages"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id: Mapped[str] = mapped_column(String(50), index=True)
    sender_phone: Mapped[str] = mapped_column(String(20), index=True)
    sender_name: Mapped[str | None] = mapped_column(String(200))
    message_type: Mapped[str] = mapped_column(String(50), default="text")
    text_content: Mapped[str | None] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(Text)
    is_group: Mapped[bool] = mapped_column(Boolean, default=False)
    group_name: Mapped[str | None] = mapped_column(String(200))
    is_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str | None] = mapped_column(String(50))  # price_inquiry/complaint/order/unsubscribe
    auto_replied: Mapped[bool] = mapped_column(Boolean, default=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    original_payload: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Blacklist(Base):
    __tablename__ = "blacklist"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

### `backend/app/models/template.py`
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class MessageTemplate(Base):
    __tablename__ = "message_templates"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))  # seasonal/product/general
    content: Mapped[str] = mapped_column(Text, nullable=False)
    campaign_type: Mapped[str] = mapped_column(String(50), default="text")
    use_count: Mapped[int] = mapped_column(Integer if False else String, default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# Fix: use Integer properly
from sqlalchemy import Integer
MessageTemplate.use_count = mapped_column(Integer, default=0)
```

### `backend/app/models/group.py`
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class WhatsAppGroup(Base):
    __tablename__ = "whatsapp_groups"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    green_group_id: Mapped[str | None] = mapped_column(String(100))  # groupId@g.us
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

---

## PHASE 7 — Green API Service (Complete)

### `backend/app/services/green_api.py`
```python
"""
Full Green API client — ALL endpoints implemented.
Docs: https://green-api.com/en/docs/api/
"""
import httpx
from typing import Optional
from app.config import settings


class GreenAPIClient:
    def __init__(self, instance_id: str, api_token: str):
        self.instance_id = instance_id
        self.api_token = api_token
        self.base_url = f"https://api.green-api.com/waInstance{instance_id}"

    async def _get(self, endpoint: str) -> dict:
        url = f"{self.base_url}/{endpoint}/{self.api_token}"
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(url)
            r.raise_for_status()
            return r.json()

    async def _post(self, endpoint: str, data: dict = None) -> dict:
        url = f"{self.base_url}/{endpoint}/{self.api_token}"
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(url, json=data or {})
            r.raise_for_status()
            return r.json()

    # ── ACCOUNT ──────────────────────────────────────────
    async def get_state(self) -> str:
        r = await self._get("getStateInstance")
        return r.get("stateInstance", "unknown")

    async def get_settings(self) -> dict:
        return await self._get("getSettings")

    async def set_settings(self, settings_dict: dict) -> bool:
        r = await self._post("setSettings", settings_dict)
        return r.get("saveSettings", False)

    async def set_webhook(self, webhook_url: str) -> bool:
        return await self.set_settings({
            "webhookUrl": webhook_url,
            "outgoingWebhook": "yes",
            "incomingWebhook": "yes",
            "stateWebhook": "yes",
            "delaySendMessagesMilliseconds": 3000
        })

    async def reboot(self) -> bool:
        r = await self._get("reboot")
        return r.get("isReboot", False)

    async def logout(self) -> bool:
        r = await self._get("logout")
        return r.get("isLogout", False)

    async def get_qr(self) -> str:
        """Returns base64 QR image."""
        r = await self._get("qr")
        return r.get("message", "")

    async def get_auth_code(self, phone: str) -> dict:
        """Login by phone number without QR scan."""
        phone = self._normalize(phone)
        return await self._post("getAuthorizationCode", {"phoneNumber": int(phone)})

    async def get_wa_settings(self) -> dict:
        """Get WhatsApp account info (name, phone, etc)."""
        return await self._get("getWaSettings")

    async def set_profile_picture(self, image_path: str) -> bool:
        r = await self._post("setProfilePicture", {"imagePath": image_path})
        return r.get("setProfilePicture", False)

    # ── SENDING ──────────────────────────────────────────
    async def send_message(self, phone: str, message: str) -> Optional[str]:
        r = await self._post("sendMessage", {
            "chatId": self._chat_id(phone),
            "message": message
        })
        return r.get("idMessage")

    async def send_image(self, phone: str, image_url: str, caption: str = "") -> Optional[str]:
        r = await self._post("sendFileByUrl", {
            "chatId": self._chat_id(phone),
            "urlFile": image_url,
            "fileName": "image.jpg",
            "caption": caption
        })
        return r.get("idMessage")

    async def send_file_url(self, phone: str, url: str, filename: str, caption: str = "") -> Optional[str]:
        r = await self._post("sendFileByUrl", {
            "chatId": self._chat_id(phone),
            "urlFile": url,
            "fileName": filename,
            "caption": caption
        })
        return r.get("idMessage")

    async def send_poll(self, phone: str, question: str, options: list[str], multiple: bool = False) -> Optional[str]:
        r = await self._post("sendPoll", {
            "chatId": self._chat_id(phone),
            "message": question,
            "options": [{"optionName": o} for o in options],
            "multipleAnswers": multiple
        })
        return r.get("idMessage")

    async def send_location(self, phone: str, lat: float, lon: float, name: str = "") -> Optional[str]:
        r = await self._post("sendLocation", {
            "chatId": self._chat_id(phone),
            "latitude": lat,
            "longitude": lon,
            "nameLocation": name
        })
        return r.get("idMessage")

    async def send_contact(self, phone: str, contact_phone: str, contact_name: str) -> Optional[str]:
        r = await self._post("sendContact", {
            "chatId": self._chat_id(phone),
            "contact": {"phoneContact": int(contact_phone), "firstName": contact_name}
        })
        return r.get("idMessage")

    async def send_interactive_buttons(self, phone: str, body: str, buttons: list[str], footer: str = "") -> Optional[str]:
        """Send message with up to 3 clickable buttons."""
        btn_list = [{"type": "replyButton", "reply": {"id": str(i+1), "title": b}} for i, b in enumerate(buttons[:3])]
        r = await self._post("sendInteractiveButtons", {
            "chatId": self._chat_id(phone),
            "contentText": body,
            "footer": footer,
            "buttons": btn_list
        })
        return r.get("idMessage")

    async def forward_messages(self, phone: str, chat_id_from: str, message_ids: list[str]) -> Optional[str]:
        r = await self._post("forwardMessages", {
            "chatId": self._chat_id(phone),
            "chatIdFrom": chat_id_from,
            "messages": message_ids
        })
        return r.get("idMessage")

    # ── STATUSES ─────────────────────────────────────────
    async def send_status_text(self, text: str, bg_color: str = "#FFFFFF") -> Optional[str]:
        r = await self._post("sendTextStatus", {"message": text, "backgroundColor": bg_color, "font": "SANS_SERIF"})
        return r.get("idMessage")

    async def send_status_image(self, image_url: str, caption: str = "") -> Optional[str]:
        r = await self._post("sendMediaStatus", {"urlFile": image_url, "fileName": "status.jpg", "caption": caption})
        return r.get("idMessage")

    async def get_status_statistics(self, message_id: str) -> dict:
        return await self._post("getStatusStatistic", {"idMessage": message_id})

    # ── RECEIVING ────────────────────────────────────────
    async def receive_notification(self) -> Optional[dict]:
        """HTTP polling mode: get one pending notification."""
        try:
            r = await self._get("receiveNotification")
            return r if r else None
        except Exception:
            return None

    async def delete_notification(self, receipt_id: int) -> bool:
        url = f"{self.base_url}/deleteNotification/{self.api_token}/{receipt_id}"
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.delete(url)
            return r.json().get("result", False)

    # ── SERVICE ──────────────────────────────────────────
    async def check_whatsapp(self, phone: str) -> bool:
        phone = self._normalize(phone)
        r = await self._post("checkWhatsapp", {"phoneNumber": int(phone)})
        return r.get("existsWhatsapp", False)

    async def get_avatar(self, phone: str) -> Optional[str]:
        r = await self._post("getAvatar", {"chatId": self._chat_id(phone)})
        return r.get("urlAvatar")

    async def get_contacts(self) -> list[dict]:
        return await self._get("getContacts")

    async def get_contact_info(self, phone: str) -> dict:
        return await self._post("getContactInfo", {"chatId": self._chat_id(phone)})

    async def get_chat_history(self, phone: str, count: int = 50) -> list[dict]:
        return await self._post("getChatHistory", {"chatId": self._chat_id(phone), "count": count})

    async def mark_as_read(self, phone: str, message_id: str) -> bool:
        r = await self._post("readChat", {"chatId": self._chat_id(phone), "idMessage": message_id})
        return r.get("setRead", False)

    async def archive_chat(self, phone: str) -> bool:
        r = await self._post("archiveChat", {"chatId": self._chat_id(phone)})
        return r.get("isArchived", False)

    # ── QUEUE ────────────────────────────────────────────
    async def show_messages_queue(self) -> list[dict]:
        return await self._get("showMessagesQueue")

    async def clear_messages_queue(self) -> bool:
        r = await self._get("clearMessagesQueue")
        return r.get("isCleared", False)

    # ── GROUPS ───────────────────────────────────────────
    async def create_group(self, name: str, phones: list[str]) -> dict:
        return await self._post("createGroup", {
            "groupName": name,
            "chatIds": [self._chat_id(p) for p in phones]
        })

    async def add_group_participant(self, group_id: str, phone: str) -> dict:
        return await self._post("addGroupParticipant", {"groupId": group_id, "participantChatId": self._chat_id(phone)})

    async def remove_group_participant(self, group_id: str, phone: str) -> dict:
        return await self._post("removeGroupParticipant", {"groupId": group_id, "participantChatId": self._chat_id(phone)})

    async def get_group_data(self, group_id: str) -> dict:
        return await self._post("getGroupData", {"groupId": group_id})

    async def send_group_message(self, group_id: str, message: str) -> Optional[str]:
        r = await self._post("sendMessage", {"chatId": group_id, "message": message})
        return r.get("idMessage")

    # ── HELPERS ──────────────────────────────────────────
    @staticmethod
    def _normalize(phone: str) -> str:
        import re
        phone = re.sub(r"\D", "", str(phone).strip())
        if phone.startswith("0") and len(phone) == 11:
            phone = "98" + phone[1:]
        elif len(phone) == 10 and phone.startswith("9"):
            phone = "98" + phone
        return phone

    def _chat_id(self, phone: str) -> str:
        return f"{self._normalize(phone)}@c.us"
```

---

## PHASE 8 — GPT Service

### `backend/app/services/gpt_service.py`
```python
from openai import AsyncOpenAI
from app.config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """
تو یک دستیار فروش افراکالا هستی که پیام‌های واتس‌اپ کوتاه، صمیمی و حرفه‌ای فارسی می‌نویسی.
قوانین:
- پیام منحصربه‌فرد، شخصی، و با اسم مشتری
- لحن صمیمی اما حرفه‌ای
- حداکثر ۳ پاراگراف کوتاه
- بدون کلمات اضافه مثل "خلاصه" یا "در نتیجه"
- در پایان: "برای لغو عدد ۱۱ ارسال کنید"
"""

async def generate_message(first_name: str, last_name: str, gpt_prompt: str, products: list[dict] = None) -> str:
    products_text = ""
    if products:
        products_text = "\n\nمحصولات امروز افراکالا:\n"
        for p in products[:3]:
            price = f"{p['price']:,} تومان" if p.get("price") else "تماس بگیرید"
            products_text += f"• {p['name']}: {price}\n"

    user_msg = f"اسم مشتری: {first_name} {last_name}\n{gpt_prompt}{products_text}\nپیام واتس‌اپ فارسی بنویس:"

    r = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_msg}],
        max_tokens=500, temperature=0.85
    )
    return r.choices[0].message.content.strip()


async def categorize_message(text: str) -> str:
    """Auto-categorize incoming message: price_inquiry / complaint / order / unsubscribe / other"""
    r = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Categorize the Persian WhatsApp message into exactly one: price_inquiry, complaint, order, unsubscribe, other. Reply with only the category word."},
            {"role": "user", "content": text or ""}
        ],
        max_tokens=10
    )
    return r.choices[0].message.content.strip().lower()
```

---

## PHASE 9 — Rate Limiter + Warm-up

### `backend/app/services/rate_limiter.py`
```python
import redis.asyncio as aioredis
from datetime import datetime
import pytz
from app.config import settings

redis_client = aioredis.from_url(settings.redis_url)
TEHRAN_TZ = pytz.timezone("Asia/Tehran")

DEFAULT_SCHEDULE = [
    {"hour_start": 8,  "hour_end": 9,  "max_per_hour": 30},
    {"hour_start": 9,  "hour_end": 10, "max_per_hour": 70},
    {"hour_start": 10, "hour_end": 11, "max_per_hour": 200},
    {"hour_start": 11, "hour_end": 22, "max_per_hour": 500},
]

def get_tehran_hour() -> int:
    return datetime.now(TEHRAN_TZ).hour

def get_max_per_hour() -> int:
    h = get_tehran_hour()
    for slot in DEFAULT_SCHEDULE:
        if slot["hour_start"] <= h < slot["hour_end"]:
            return slot["max_per_hour"]
    return 0

async def can_send(account_id: str) -> bool:
    max_h = get_max_per_hour()
    if max_h == 0:
        return False
    h = get_tehran_hour()
    count = await redis_client.get(f"rate:{account_id}:{h}")
    return not count or int(count) < max_h

async def record_send(account_id: str):
    h = get_tehran_hour()
    key = f"rate:{account_id}:{h}"
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, 3700)
    await pipe.execute()

async def get_stats(account_id: str) -> dict:
    h = get_tehran_hour()
    sent = int(await redis_client.get(f"rate:{account_id}:{h}") or 0)
    max_h = get_max_per_hour()
    return {"sent_this_hour": sent, "max_this_hour": max_h, "can_send": max_h > 0 and sent < max_h, "tehran_hour": h}
```

### `backend/app/services/warmup_service.py`
```python
"""
Automatic account warm-up: gradually increase daily send limit.
Day 1: 1 msg, Day 2: 2 msgs, ..., Day 7: 7 msgs, break 2 days, resume.
"""
from datetime import datetime, timedelta
import pytz

TEHRAN_TZ = pytz.timezone("Asia/Tehran")

def get_warmup_limit(days_active: int) -> int:
    if days_active <= 7:
        return days_active
    elif days_active <= 9:
        return max(days_active - 7 - 2, 5)
    else:
        return min(days_active - 2, 80)

async def post_daily_status(client, message: str = "افراکالا - لوازم خانگی عمده"):
    """Post a status update to warm up the account."""
    try:
        await client.send_status_text(message, bg_color="#25D366")
    except Exception as e:
        print(f"[Warmup] Status post failed: {e}")
```

---

## PHASE 10 — Auto Reply + Campaign Runner

### `backend/app/services/auto_reply.py`
```python
from datetime import datetime
import pytz
from app.services.gpt_service import categorize_message

TEHRAN_TZ = pytz.timezone("Asia/Tehran")

OUTSIDE_HOURS_MESSAGE = """سلام! پیامتون دریافت شد 🙏
ساعات کاری افراکالا: ۸ صبح تا ۱۰ شب
به زودی پاسخ می‌دیم.
برای لغو عدد ۱۱ ارسال کنید."""

UNSUBSCRIBE_MESSAGE = """شما از لیست ارسال پیام‌های افراکالا حذف شدید.
موفق باشید 🌟"""

def is_business_hours() -> bool:
    now = datetime.now(TEHRAN_TZ)
    return 8 <= now.hour < 22

async def process_auto_reply(account, sender_phone: str, message_text: str, client) -> tuple[bool, str]:
    """
    Returns (should_reply, reply_message).
    Handles: unsubscribe, outside hours, price inquiry.
    """
    # Unsubscribe
    if message_text and message_text.strip() in ["11", "۱۱", "لغو", "حذف"]:
        return True, UNSUBSCRIBE_MESSAGE

    # Outside hours
    if account.auto_reply_outside_hours and not is_business_hours():
        return True, OUTSIDE_HOURS_MESSAGE

    # Custom auto-reply if enabled
    if account.auto_reply_enabled and account.auto_reply_message:
        return True, account.auto_reply_message

    return False, ""
```

### `backend/app/services/campaign_runner.py`
```python
import asyncio, random, uuid, json
from datetime import datetime
from sqlalchemy import select, update
from app.models.campaign import Campaign, CampaignContact, CampaignStatus, MessageStatus, CampaignType
from app.models.account import Account, AccountStatus
from app.models.contact import Contact
from app.services.green_api import GreenAPIClient
from app.services.gpt_service import generate_message
from app.services.price_service import get_products
from app.services.rate_limiter import can_send, record_send
from app.database import AsyncSessionLocal
from app.config import settings


async def run_campaign(campaign_id: str):
    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if not campaign or campaign.status != CampaignStatus.running:
            return

        result = await db.execute(
            select(CampaignContact, Contact)
            .join(Contact, CampaignContact.contact_id == Contact.id)
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status.in_([MessageStatus.pending])
            )
        )
        pending = result.all()
        if not pending:
            campaign.status = CampaignStatus.completed
            campaign.completed_at = datetime.utcnow()
            await db.commit()
            return

        accounts_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
        accounts = accounts_result.scalars().all()
        if not accounts:
            return

        products = []
        if campaign.include_products:
            products = await get_products(campaign.product_count)

        poll_options = []
        if campaign.poll_options:
            try:
                poll_options = json.loads(campaign.poll_options)
            except Exception:
                poll_options = []

        buttons = [b for b in [campaign.button1_text, campaign.button2_text, campaign.button3_text] if b]

        acc_idx = 0
        for cc, contact in pending:
            await db.refresh(campaign)
            if campaign.status != CampaignStatus.running:
                break
            if contact.blacklisted or contact.has_whatsapp is False:
                cc.status = MessageStatus.skipped
                await db.commit()
                continue

            account = accounts[acc_idx % len(accounts)]
            acc_idx += 1

            if account.sent_today >= account.computed_daily_limit:
                continue
            if not await can_send(str(account.id)):
                await asyncio.sleep(60)
                continue

            try:
                cc.status = MessageStatus.generating
                await db.commit()

                # Generate message text
                if campaign.use_gpt and settings.openai_api_key:
                    message = await generate_message(
                        first_name=contact.first_name or "",
                        last_name=contact.last_name or "",
                        gpt_prompt=campaign.gpt_prompt or "یک پیام تبلیغاتی مختصر بنویس",
                        products=products if campaign.include_products else None
                    )
                else:
                    message = (campaign.message_template or "سلام {{first_name}} جان!")
                    message = message.replace("{{first_name}}", contact.first_name or "")
                    message = message.replace("{{last_name}}", contact.last_name or "")

                cc.generated_message = message
                client = GreenAPIClient(account.instance_id, account.api_token)
                msg_id = None

                # Send based on campaign type
                if campaign.campaign_type == CampaignType.text:
                    msg_id = await client.send_message(contact.phone, message)
                elif campaign.campaign_type == CampaignType.image and campaign.image_url:
                    msg_id = await client.send_image(contact.phone, campaign.image_url, message)
                elif campaign.campaign_type == CampaignType.poll and campaign.poll_question:
                    msg_id = await client.send_poll(contact.phone, campaign.poll_question, poll_options)
                elif campaign.campaign_type == CampaignType.interactive_buttons and buttons:
                    msg_id = await client.send_interactive_buttons(contact.phone, message, buttons, campaign.footer_text or "")
                else:
                    msg_id = await client.send_message(contact.phone, message)

                if msg_id:
                    cc.status = MessageStatus.sent
                    cc.sent_at = datetime.utcnow()
                    cc.green_api_message_id = msg_id
                    cc.account_id = account.id
                    account.sent_today += 1
                    campaign.sent_count += 1
                    await record_send(str(account.id))
                else:
                    cc.status = MessageStatus.failed
                    cc.error_message = "No message ID returned"
                    campaign.failed_count += 1

            except Exception as e:
                cc.status = MessageStatus.failed
                cc.error_message = str(e)
                cc.retry_count += 1
                campaign.failed_count += 1
            finally:
                await db.commit()

            delay = random.uniform(settings.default_min_delay, settings.default_max_delay)
            await asyncio.sleep(delay)

        remaining = await db.execute(
            select(CampaignContact).where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status == MessageStatus.pending
            )
        )
        if not remaining.scalars().first():
            campaign.status = CampaignStatus.completed
            campaign.completed_at = datetime.utcnow()
            await db.commit()
```

---

## PHASE 11 — Webhook (Complete)

### `backend/app/api/v1/webhook.py`
```python
import json
from datetime import datetime
from fastapi import APIRouter, Request, BackgroundTasks
from app.database import AsyncSessionLocal
from app.models.inbox import InboxMessage
from app.models.account import Account, AccountStatus
from app.models.campaign import CampaignContact
from sqlalchemy import select

router = APIRouter(prefix="/webhook", tags=["webhook"])

@router.post("/{instance_id}")
async def receive_webhook(instance_id: str, request: Request, bg: BackgroundTasks):
    body = await request.json()
    bg.add_task(process_webhook, instance_id, body)
    return {"status": "ok"}

async def process_webhook(instance_id: str, payload: dict):
    wtype = payload.get("typeWebhook", "")
    if wtype == "incomingMessageReceived":
        await handle_incoming(instance_id, payload)
    elif wtype == "stateInstanceChanged":
        await handle_state_change(instance_id, payload)
    elif wtype == "outgoingMessageStatus":
        await handle_outgoing_status(instance_id, payload)

async def handle_incoming(instance_id: str, payload: dict):
    data = payload.get("messageData", {})
    sender = payload.get("senderData", {})
    text = (
        data.get("textMessageData", {}).get("textMessage") or
        data.get("extendedTextMessageData", {}).get("text") or
        data.get("pollMessageData", {}).get("name") or ""
    )

    from app.services.gpt_service import categorize_message
    from app.services.auto_reply import process_auto_reply
    from app.services.green_api import GreenAPIClient

    category = await categorize_message(text) if text else "other"
    sender_phone = sender.get("sender", "").split("@")[0]

    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=sender_phone,
            sender_name=sender.get("senderName", ""),
            message_type=data.get("typeMessage", "text"),
            text_content=text,
            is_group="@g.us" in sender.get("chatId", ""),
            group_name=sender.get("chatName", ""),
            category=category,
            original_payload=json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0))
        )
        db.add(msg)

        # Update account received count
        acc_result = await db.execute(select(Account).where(Account.instance_id == instance_id))
        account = acc_result.scalar_one_or_none()
        if account:
            account.received_today += 1

            # Check if auto-reply needed
            client = GreenAPIClient(account.instance_id, account.api_token)
            should_reply, reply_msg = await process_auto_reply(account, sender_phone, text, client)
            if should_reply and reply_msg and not msg.is_group:
                try:
                    await client.send_message(sender_phone, reply_msg)
                    msg.auto_replied = True
                except Exception:
                    pass

            # If unsubscribe → blacklist
            if text and text.strip() in ["11", "۱۱", "لغو"]:
                from app.models.inbox import Blacklist
                from app.models.contact import Contact
                bl_check = await db.execute(select(Blacklist).where(Blacklist.phone == sender_phone))
                if not bl_check.scalar_one_or_none():
                    bl = Blacklist(phone=sender_phone, reason="self_unsubscribed")
                    db.add(bl)
                contact_check = await db.execute(select(Contact).where(Contact.phone == sender_phone))
                ct = contact_check.scalar_one_or_none()
                if ct:
                    ct.blacklisted = True

        await db.commit()

async def handle_state_change(instance_id: str, payload: dict):
    state = payload.get("stateInstance", "")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Account).where(Account.instance_id == instance_id))
        account = result.scalar_one_or_none()
        if account:
            if state == "blocked":
                account.status = AccountStatus.banned
                account.banned_at = datetime.utcnow()
                account.ban_reason = "blocked by WhatsApp"
            elif state == "notAuthorized":
                account.status = AccountStatus.disconnected
            elif state == "authorized":
                account.status = AccountStatus.active
            await db.commit()

async def handle_outgoing_status(instance_id: str, payload: dict):
    msg_id = payload.get("idMessage", "")
    status = payload.get("status", "")
    if not msg_id or not status:
        return
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CampaignContact).where(CampaignContact.green_api_message_id == msg_id)
        )
        cc = result.scalar_one_or_none()
        if cc:
            cc.delivery_status = status
            from app.models.campaign import Campaign
            campaign = await db.get(Campaign, cc.campaign_id)
            if campaign:
                if status == "delivered":
                    campaign.delivered_count += 1
                elif status == "read":
                    campaign.read_count += 1
            await db.commit()
```

---

## PHASE 12 — All API Routers

Create these routers with full CRUD:

### `backend/app/api/v1/accounts.py`
Full CRUD + check status + get QR + reboot + logout + warmup toggle + auto-reply settings.
GET /accounts/, POST /accounts/, DELETE /accounts/{id}
GET /accounts/{id}/status — calls getStateInstance
GET /accounts/{id}/qr — returns base64 QR
POST /accounts/{id}/reboot
POST /accounts/{id}/logout
POST /accounts/{id}/check-whatsapp-bulk — batch check contacts
PUT /accounts/{id}/auto-reply — enable/disable auto-reply + set message
GET /accounts/{id}/queue — show messages queue
DELETE /accounts/{id}/queue — clear queue

### `backend/app/api/v1/campaigns.py`
GET /campaigns/
POST /campaigns/ (name, type, template, gpt_prompt, poll_question, poll_options, buttons, image_url, include_products)
GET /campaigns/{id}/progress
POST /campaigns/{id}/contacts — add contacts list
POST /campaigns/{id}/start
POST /campaigns/{id}/pause
POST /campaigns/{id}/resume
POST /campaigns/{id}/test — send test to one phone number
DELETE /campaigns/{id}

### `backend/app/api/v1/contacts.py`
GET /contacts/ (with search, has_whatsapp filter, province filter)
POST /contacts/import — Excel upload
POST /contacts/check-bulk — batch checkWhatsapp (uses first active account)
DELETE /contacts/{id}
POST /contacts/{id}/blacklist
GET /contacts/{id}/history — chat history from Green API

### `backend/app/api/v1/inbox.py`
GET /inbox/ (with filter: unread, category, account)
POST /inbox/{id}/read
POST /inbox/reply — send reply to a message
GET /inbox/stats — count by category

### `backend/app/api/v1/groups.py`
GET /groups/
POST /groups/ — create group with member phones
POST /groups/{id}/members — add members
DELETE /groups/{id}/members/{phone}
POST /groups/{id}/send — send message to group
GET /groups/{id}/info — getGroupData

### `backend/app/api/v1/statuses.py`
POST /statuses/text — sendTextStatus to all accounts
POST /statuses/image — sendMediaStatus
GET /statuses/{message_id}/stats — getStatusStatistic

### `backend/app/api/v1/templates.py`
GET /templates/
POST /templates/
DELETE /templates/{id}
POST /templates/{id}/use — increment use_count, return content

### `backend/app/api/v1/dashboard.py`
GET /dashboard/stats — full real-time stats
GET /dashboard/rate-limits — current hour limits
PUT /dashboard/rate-limits — update schedule

### `backend/app/api/v1/blacklist.py`
GET /blacklist/
POST /blacklist/
DELETE /blacklist/{phone}

---

## PHASE 13 — main.py

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.api.v1 import accounts, campaigns, contacts, webhook, dashboard, inbox, groups, statuses, templates, blacklist

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Seed default rate schedule
    yield

app = FastAPI(title="Afrakala WhatsApp Sender", version="2.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for router in [accounts.router, campaigns.router, contacts.router, webhook.router, dashboard.router, inbox.router, groups.router, statuses.router, templates.router, blacklist.router]:
    app.include_router(router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
```

---

## PHASE 14 — Celery Workers

### `backend/app/workers/celery_app.py`
```python
from celery import Celery
from app.config import settings

celery_app = Celery("whatsapp_sender", broker=settings.redis_url, backend=settings.redis_url, include=["app.workers.tasks"])
celery_app.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"],
    timezone="Asia/Tehran", enable_utc=True, worker_prefetch_multiplier=1, task_acks_late=True)

celery_app.conf.beat_schedule = {
    "reset-daily-counters": {"task": "tasks.reset_daily_counters", "schedule": 86400.0},
    "warmup-accounts": {"task": "tasks.warmup_accounts", "schedule": 3600.0},
    "sync-account-states": {"task": "tasks.sync_account_states", "schedule": 300.0},
}
```

### `backend/app/workers/tasks.py`
```python
import asyncio
from app.workers.celery_app import celery_app
from app.services.campaign_runner import run_campaign

@celery_app.task(bind=True, name="tasks.run_campaign", max_retries=3)
def task_run_campaign(self, campaign_id: str):
    try:
        asyncio.run(run_campaign(campaign_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

@celery_app.task(name="tasks.reset_daily_counters")
def task_reset_daily_counters():
    async def _r():
        from app.database import AsyncSessionLocal
        from app.models.account import Account
        from sqlalchemy import update
        from datetime import date
        async with AsyncSessionLocal() as db:
            await db.execute(update(Account).values(sent_today=0, received_today=0, last_reset_date=date.today()))
            # Move received_today to received_yesterday
            await db.commit()
    asyncio.run(_r())

@celery_app.task(name="tasks.warmup_accounts")
def task_warmup_accounts():
    async def _w():
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from app.services.green_api import GreenAPIClient
        from app.services.warmup_service import post_daily_status
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Account).where(Account.status == AccountStatus.active, Account.warmup_enabled == True))
            for account in result.scalars().all():
                client = GreenAPIClient(account.instance_id, account.api_token)
                await post_daily_status(client)
                account.days_active += 1
            await db.commit()
    asyncio.run(_w())

@celery_app.task(name="tasks.sync_account_states")
def task_sync_account_states():
    async def _s():
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from app.services.green_api import GreenAPIClient
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Account))
            for account in result.scalars().all():
                try:
                    client = GreenAPIClient(account.instance_id, account.api_token)
                    state = await client.get_state()
                    if state == "authorized":
                        account.status = AccountStatus.active
                    elif state == "blocked":
                        account.status = AccountStatus.banned
                    elif state == "notAuthorized":
                        account.status = AccountStatus.disconnected
                except Exception:
                    pass
            await db.commit()
    asyncio.run(_s())
```

---

## PHASE 15 — Docker Compose

### `docker-compose.yml`
```yaml
version: "3.9"
services:
  db:
    image: postgres:15-alpine
    restart: always
    environment:
      POSTGRES_USER: afrakala
      POSTGRES_PASSWORD: password
      POSTGRES_DB: whatsapp_sender
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    restart: always
    ports:
      - "6379:6379"

  backend:
    build: ./backend
    restart: always
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    volumes:
      - ./backend:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  worker:
    build: ./backend
    restart: always
    env_file: .env
    depends_on:
      - db
      - redis
    volumes:
      - ./backend:/app
    command: celery -A app.workers.celery_app worker --loglevel=info --concurrency=2

  beat:
    build: ./backend
    restart: always
    env_file: .env
    depends_on:
      - redis
    volumes:
      - ./backend:/app
    command: celery -A app.workers.celery_app beat --loglevel=info

volumes:
  postgres_data:
```

### `backend/Dockerfile`
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## PHASE 16 — Git Commit and Push

```bash
cd C:\Users\AFRA\Desktop\bots\claudegreenapi
git add -A
git commit -m "feat: Afrakala WhatsApp Sender v2.0 — full Green API implementation

Features:
- All Green API endpoints: send text/image/poll/buttons/location/contact/status
- Multi-account management with QR + phone-number auth
- Campaign runner: text, image, poll, interactive buttons types
- Auto warm-up service with daily status posting
- Smart inbox with GPT auto-categorization
- Auto-reply with outside-hours and unsubscribe handling
- Group management: create, add/remove members, send messages
- WhatsApp Status sending + view statistics
- Message template library
- Queue management per account
- Time-based rate limiting (Tehran timezone)
- Daily limit formula: base + incoming_bonus + reply_bonus
- Excel contact import with Iranian number normalization
- Delivery tracking: sent/delivered/read via webhook
- Celery beat: daily reset, warmup, state sync
- Docker Compose: FastAPI + PostgreSQL + Redis + Celery"

git push origin main
```

---

## DONE. All phases complete.