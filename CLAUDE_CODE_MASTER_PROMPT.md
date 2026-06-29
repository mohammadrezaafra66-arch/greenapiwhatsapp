# CLAUDE CODE MASTER PROMPT
# Afrakala WhatsApp Sender Platform — Full Auto Build
# Run this prompt in Claude Code inside an empty local folder

---

You are building the **Afrakala WhatsApp Sender Platform** — a production-grade WhatsApp bulk messaging system using Green API.

**Repository:** https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp  
**Local folder:** current working directory

Execute ALL phases in order. Do not stop until everything is committed and pushed to GitHub.

---

## PHASE 0 — Git Setup

```bash
git init
git remote add origin https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp.git
git pull origin main --allow-unrelated-histories 2>/dev/null || echo "Fresh repo"
```

---

## PHASE 1 — Project Structure

Create the following folder structure:

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
│   │   │   └── inbox.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── account.py
│   │   │   ├── campaign.py
│   │   │   └── contact.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── accounts.py
│   │   │       ├── campaigns.py
│   │   │       ├── contacts.py
│   │   │       ├── webhook.py
│   │   │       ├── dashboard.py
│   │   │       └── blacklist.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── green_api.py
│   │   │   ├── gpt_service.py
│   │   │   ├── campaign_runner.py
│   │   │   ├── rate_limiter.py
│   │   │   ├── price_service.py
│   │   │   └── excel_service.py
│   │   └── workers/
│   │       ├── __init__.py
│   │       ├── celery_app.py
│   │       └── tasks.py
│   ├── migrations/
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_green_api.py
│   │   └── test_campaign.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic.ini
├── frontend/
│   └── index.html   (minimal monitoring dashboard)
├── docker-compose.yml
├── docker-compose.dev.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## PHASE 2 — Core Configuration Files

### `.gitignore`
```
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.eggs/
.env
.venv/
venv/
env/
*.log
*.sqlite3
.DS_Store
node_modules/
.pytest_cache/
htmlcov/
.coverage
celerybeat-schedule
```

### `.env.example`
```env
# Database
DATABASE_URL=postgresql+asyncpg://afrakala:password@localhost:5432/whatsapp_sender
SYNC_DATABASE_URL=postgresql://afrakala:password@localhost:5432/whatsapp_sender

# Redis
REDIS_URL=redis://localhost:6379/0

# OpenAI
OPENAI_API_KEY=sk-your-openai-key-here

# Internal Pricing API
PRICING_API_URL=http://192.168.170.8:3000/pricing/amin-hozoor-board
PRICING_CACHE_MINUTES=5

# Server
SECRET_KEY=change-this-to-random-secret
BACKEND_URL=http://localhost:8000
WEBHOOK_BASE_URL=http://localhost:8000

# Send Timing (seconds)
DEFAULT_MIN_DELAY=45
DEFAULT_MAX_DELAY=110

# Environment
ENVIRONMENT=development
DEBUG=true
```

### `backend/requirements.txt`
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
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
pydantic==2.7.4
pydantic-settings==2.3.3
APScheduler==3.10.4
pytz==2024.1
jinja2==3.1.4
aiofiles==23.2.1
pytest==8.2.2
pytest-asyncio==0.23.7
httpx==0.27.0
```

---

## PHASE 3 — Database Models

### `backend/app/config.py`
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

### `backend/app/database.py`
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

### `backend/app/models/account.py`
```python
import uuid
from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, Date, DateTime, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
import enum

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
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def computed_daily_limit(self) -> int:
        """Calculate daily limit using the Afrakala formula."""
        base = min(self.days_active, 10)
        incoming = min(self.received_yesterday, 20)
        replies = min(self.quick_replies_yesterday * 5, 50)
        return base + incoming + replies
```

### `backend/app/models/contact.py`
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, Index
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
    has_whatsapp: Mapped[bool | None] = mapped_column(Boolean)
    whatsapp_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)
    blacklist_reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def full_name(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else self.phone

    @property
    def chat_id(self) -> str:
        """Format for Green API: 989123456789@c.us"""
        phone = self.phone.lstrip("+").lstrip("0")
        if not phone.startswith("98"):
            phone = "98" + phone
        return f"{phone}@c.us"
```

### `backend/app/models/campaign.py`
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, Text, ForeignKey, Float, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
import enum

class CampaignStatus(str, enum.Enum):
    draft = "draft"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"

class MessageStatus(str, enum.Enum):
    pending = "pending"
    generating = "generating"
    queued = "queued"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"
    no_whatsapp = "no_whatsapp"

class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(SAEnum(CampaignStatus), default=CampaignStatus.draft)
    message_template: Mapped[str | None] = mapped_column(Text)
    use_gpt: Mapped[bool] = mapped_column(Boolean, default=True)
    gpt_prompt: Mapped[str | None] = mapped_column(Text)
    include_products: Mapped[bool] = mapped_column(Boolean, default=False)
    product_count: Mapped[int] = mapped_column(Integer, default=3)
    send_image: Mapped[bool] = mapped_column(Boolean, default=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    schedule_start: Mapped[datetime | None] = mapped_column(DateTime)
    schedule_end: Mapped[datetime | None] = mapped_column(DateTime)
    total_contacts: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
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
    green_api_message_id: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)

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
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey
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

---

## PHASE 4 — Services

### `backend/app/services/green_api.py`
```python
"""
Green API client for WhatsApp messaging.
Docs: https://green-api.com/en/docs/
"""
import httpx
import asyncio
from typing import Optional
from app.config import settings


class GreenAPIClient:
    def __init__(self, instance_id: str, api_token: str):
        self.instance_id = instance_id
        self.api_token = api_token
        self.base_url = f"https://api.green-api.com/waInstance{instance_id}"

    async def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        url = f"{self.base_url}/{endpoint}/{self.api_token}"
        async with httpx.AsyncClient(timeout=30) as client:
            if method == "GET":
                resp = await client.get(url)
            else:
                resp = await client.post(url, json=data)
            resp.raise_for_status()
            return resp.json()

    async def get_state(self) -> str:
        """Returns: authorized, notAuthorized, blocked, sleepMode, starting"""
        result = await self._request("GET", "getStateInstance")
        return result.get("stateInstance", "unknown")

    async def check_whatsapp(self, phone: str) -> bool:
        """Check if phone number has WhatsApp."""
        phone = self._normalize_phone(phone)
        result = await self._request("GET", f"checkWhatsapp/{phone}")
        return result.get("existsWhatsapp", False)

    async def send_message(self, phone: str, message: str) -> Optional[str]:
        """Send text message. Returns message ID or None."""
        phone = self._normalize_phone(phone)
        chat_id = f"{phone}@c.us"
        result = await self._request("POST", "sendMessage", {
            "chatId": chat_id,
            "message": message
        })
        return result.get("idMessage")

    async def send_image(self, phone: str, image_url: str, caption: str = "") -> Optional[str]:
        """Send image with optional caption."""
        phone = self._normalize_phone(phone)
        chat_id = f"{phone}@c.us"
        result = await self._request("POST", "sendFileByUrl", {
            "chatId": chat_id,
            "urlFile": image_url,
            "fileName": "image.jpg",
            "caption": caption
        })
        return result.get("idMessage")

    async def set_webhook(self, webhook_url: str) -> bool:
        """Configure webhook URL for incoming messages."""
        result = await self._request("POST", "setSettings", {
            "webhookUrl": webhook_url,
            "outgoingWebhook": "yes",
            "incomingWebhook": "yes",
            "stateWebhook": "yes"
        })
        return result.get("saveSettings", False)

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Convert any Iranian phone format to 98xxxxxxxxxx."""
        phone = str(phone).strip().replace("+", "").replace("-", "").replace(" ", "")
        if phone.startswith("0") and len(phone) == 11:
            phone = "98" + phone[1:]
        elif not phone.startswith("98") and len(phone) == 10:
            phone = "98" + phone
        return phone
```

### `backend/app/services/gpt_service.py`
```python
"""
OpenAI GPT service for personalized message generation.
"""
from openai import AsyncOpenAI
from app.config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)


async def generate_message(
    first_name: str,
    last_name: str,
    gpt_prompt: str,
    products: list[dict] = None
) -> str:
    """
    Generate a unique personalized WhatsApp message.
    
    products format: [{"name": "...", "price": 12000000}, ...]
    """
    products_section = ""
    if products:
        products_section = "\n\nمحصولات امروز افراکالا:\n"
        for p in products[:3]:
            price_formatted = f"{p['price']:,} تومان" if p.get('price') else "تماس بگیرید"
            products_section += f"• {p['name']}: {price_formatted}\n"

    system_prompt = """
تو یک دستیار فروش افراکالا هستی. پیام‌های واتس‌اپ کوتاه، صمیمی و حرفه‌ای برای مشتریان می‌نویسی.
قوانین مهم:
- پیام باید کاملاً منحصربه‌فرد و شخصی باشد
- از اسم مشتری استفاده کن
- لحن صمیمی اما حرفه‌ای
- حداکثر ۳ پاراگراف کوتاه
- در پایان گزینه لغو: "برای لغو عدد ۱۱ را ارسال کنید"
"""

    user_content = f"""
اسم مشتری: {first_name} {last_name}
{gpt_prompt}
{products_section}
پیام واتس‌اپ فارسی بنویس:
"""

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        max_tokens=500,
        temperature=0.8  # Higher = more unique messages
    )

    return response.choices[0].message.content.strip()
```

### `backend/app/services/price_service.py`
```python
"""
Product price fetcher from internal Afrakala pricing API.
Caches results in Redis for PRICING_CACHE_MINUTES.
"""
import json
import httpx
import redis.asyncio as aioredis
from app.config import settings

redis_client = aioredis.from_url(settings.redis_url)

CACHE_KEY = "afrakala:products:cache"


async def get_products(count: int = 3) -> list[dict]:
    """Get top N products with prices from internal API."""
    # Try cache first
    cached = await redis_client.get(CACHE_KEY)
    if cached:
        products = json.loads(cached)
        return products[:count]

    # Fetch from API
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(settings.pricing_api_url)
            resp.raise_for_status()
            data = resp.json()

        # Normalize the response (adapt based on actual API format)
        products = []
        if isinstance(data, list):
            for item in data:
                products.append({
                    "name": item.get("name") or item.get("product_name", ""),
                    "price": item.get("price") or item.get("sell_price", 0)
                })
        elif isinstance(data, dict):
            for name, price in data.items():
                products.append({"name": name, "price": price})

        # Cache for configured minutes
        await redis_client.setex(
            CACHE_KEY,
            settings.pricing_cache_minutes * 60,
            json.dumps(products)
        )
        return products[:count]

    except Exception as e:
        print(f"[PriceService] Failed to fetch prices: {e}")
        return []
```

### `backend/app/services/rate_limiter.py`
```python
"""
Time-based rate limiter for message sending.
Controls how many messages can be sent per hour based on configured schedule.
"""
import redis.asyncio as aioredis
from datetime import datetime
import pytz
from app.config import settings

redis_client = aioredis.from_url(settings.redis_url)
TEHRAN_TZ = pytz.timezone("Asia/Tehran")

# Default schedule — can be overridden via API
DEFAULT_SCHEDULE = [
    {"hour_start": 8,  "hour_end": 9,  "max_per_hour": 30},
    {"hour_start": 9,  "hour_end": 10, "max_per_hour": 70},
    {"hour_start": 10, "hour_end": 11, "max_per_hour": 200},
    {"hour_start": 11, "hour_end": 22, "max_per_hour": 500},
    # 22:00 - 08:00 → no sending (not in list = blocked)
]


def get_current_tehran_hour() -> int:
    return datetime.now(TEHRAN_TZ).hour


def get_max_per_hour_for_current_time() -> int:
    """Returns max messages allowed in current hour. 0 = sending blocked."""
    current_hour = get_current_tehran_hour()
    for slot in DEFAULT_SCHEDULE:
        if slot["hour_start"] <= current_hour < slot["hour_end"]:
            return slot["max_per_hour"]
    return 0  # Blocked (night time)


async def can_send_now(account_id: str) -> bool:
    """Check if account can send a message right now."""
    max_per_hour = get_max_per_hour_for_current_time()
    if max_per_hour == 0:
        return False

    # Check hourly window for this account
    hour_key = f"ratelimit:{account_id}:{get_current_tehran_hour()}"
    count = await redis_client.get(hour_key)
    if count and int(count) >= max_per_hour:
        return False
    return True


async def record_send(account_id: str):
    """Record a sent message for rate limiting."""
    hour_key = f"ratelimit:{account_id}:{get_current_tehran_hour()}"
    pipe = redis_client.pipeline()
    pipe.incr(hour_key)
    pipe.expire(hour_key, 3700)  # 1 hour + buffer
    await pipe.execute()


async def get_send_stats(account_id: str) -> dict:
    current_hour = get_current_tehran_hour()
    hour_key = f"ratelimit:{account_id}:{current_hour}"
    sent_this_hour = int(await redis_client.get(hour_key) or 0)
    max_this_hour = get_max_per_hour_for_current_time()
    return {
        "sent_this_hour": sent_this_hour,
        "max_this_hour": max_this_hour,
        "can_send": max_this_hour > 0 and sent_this_hour < max_this_hour,
        "tehran_hour": current_hour
    }
```

### `backend/app/services/excel_service.py`
```python
"""
Excel import/export service for contacts.
"""
import io
import re
from typing import Optional
import openpyxl
from openpyxl.styles import Font, PatternFill

def normalize_phone(phone: str) -> Optional[str]:
    """Normalize Iranian phone numbers to 989xxxxxxxxx format."""
    if not phone:
        return None
    phone = str(phone).strip().replace("+", "").replace("-", "").replace(" ", "")
    # Remove any non-digit characters
    phone = re.sub(r"\D", "", phone)
    if not phone:
        return None
    # Convert formats
    if phone.startswith("0") and len(phone) == 11:
        phone = "98" + phone[1:]
    elif len(phone) == 10 and phone.startswith("9"):
        phone = "98" + phone
    elif phone.startswith("98") and len(phone) == 12:
        pass  # Already correct
    else:
        return None  # Invalid format
    # Validate Iranian mobile
    if not re.match(r"^989[0-9]{9}$", phone):
        return None
    return phone

def parse_contacts_excel(file_bytes: bytes) -> list[dict]:
    """
    Parse Excel file with contacts.
    Expected columns: phone, first_name, last_name, province, city
    Columns can be in any order if headers are correct.
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
    ws = wb.active

    headers = {}
    for col in range(1, ws.max_column + 1):
        cell_value = ws.cell(1, col).value
        if cell_value:
            headers[str(cell_value).lower().strip()] = col

    # Map possible column names
    phone_col = headers.get("phone") or headers.get("شماره") or headers.get("موبایل") or 1
    fname_col = headers.get("first_name") or headers.get("نام") or headers.get("اسم")
    lname_col = headers.get("last_name") or headers.get("فامیلی") or headers.get("نام خانوادگی")
    province_col = headers.get("province") or headers.get("استان")
    city_col = headers.get("city") or headers.get("شهر")

    contacts = []
    seen_phones = set()

    for row in range(2, ws.max_row + 1):
        raw_phone = ws.cell(row, phone_col).value
        if not raw_phone:
            continue

        phone = normalize_phone(str(raw_phone))
        if not phone or phone in seen_phones:
            continue
        seen_phones.add(phone)

        contact = {"phone": phone}
        if fname_col:
            contact["first_name"] = ws.cell(row, fname_col).value
        if lname_col:
            contact["last_name"] = ws.cell(row, lname_col).value
        if province_col:
            contact["province"] = ws.cell(row, province_col).value
        if city_col:
            contact["city"] = ws.cell(row, city_col).value

        contacts.append(contact)

    return contacts


def export_logs_excel(logs: list[dict]) -> bytes:
    """Export send logs as Excel file."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Send Logs"

    headers = ["شماره", "نام", "وضعیت", "زمان ارسال", "حساب", "Message ID", "خطا"]
    for i, h in enumerate(headers, 1):
        cell = ws.cell(1, i, h)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(fill_type="solid", fgColor="1F4E79")
        cell.font = Font(bold=True, color="FFFFFF")

    for row_idx, log in enumerate(logs, 2):
        ws.cell(row_idx, 1, log.get("phone", ""))
        ws.cell(row_idx, 2, log.get("name", ""))
        ws.cell(row_idx, 3, log.get("status", ""))
        ws.cell(row_idx, 4, str(log.get("sent_at", "")))
        ws.cell(row_idx, 5, log.get("account_name", ""))
        ws.cell(row_idx, 6, log.get("message_id", ""))
        ws.cell(row_idx, 7, log.get("error", ""))

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
```

### `backend/app/services/campaign_runner.py`
```python
"""
Campaign runner: manages the lifecycle of a campaign's message sending.
Respects rate limits, daily account limits, and human-like delays.
"""
import asyncio
import random
import json
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.campaign import Campaign, CampaignContact, CampaignStatus, MessageStatus
from app.models.account import Account, AccountStatus
from app.models.contact import Contact
from app.services.green_api import GreenAPIClient
from app.services.gpt_service import generate_message
from app.services.price_service import get_products
from app.services.rate_limiter import can_send_now, record_send
from app.database import AsyncSessionLocal
from app.config import settings


async def run_campaign(campaign_id: str):
    """Main campaign runner — called by Celery task."""
    async with AsyncSessionLocal() as db:
        # Get campaign
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if not campaign or campaign.status != CampaignStatus.running:
            return

        # Get pending messages
        result = await db.execute(
            select(CampaignContact, Contact, Account)
            .join(Contact, CampaignContact.contact_id == Contact.id)
            .outerjoin(Account, CampaignContact.account_id == Account.id)
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status.in_([MessageStatus.pending, MessageStatus.queued])
            )
        )
        pending = result.all()

        if not pending:
            campaign.status = CampaignStatus.completed
            campaign.completed_at = datetime.utcnow()
            await db.commit()
            return

        # Get available accounts
        accounts_result = await db.execute(
            select(Account).where(Account.status == AccountStatus.active)
        )
        accounts = accounts_result.scalars().all()
        if not accounts:
            return

        # Get products if needed
        products = []
        if campaign.include_products:
            products = await get_products(campaign.product_count)

        account_idx = 0
        for cc, contact, _ in pending:
            # Check if campaign is still running
            await db.refresh(campaign)
            if campaign.status != CampaignStatus.running:
                break

            # Pick account round-robin
            account = accounts[account_idx % len(accounts)]
            account_idx += 1

            # Check daily limit
            if account.sent_today >= account.computed_daily_limit:
                continue

            # Check hourly rate limit
            if not await can_send_now(str(account.id)):
                await asyncio.sleep(60)  # Wait 1 minute and try again
                continue

            # Skip blacklisted contacts
            if contact.blacklisted or contact.has_whatsapp is False:
                cc.status = MessageStatus.skipped
                await db.commit()
                continue

            # Generate message
            try:
                cc.status = MessageStatus.generating
                await db.commit()

                if campaign.use_gpt and settings.openai_api_key:
                    message = await generate_message(
                        first_name=contact.first_name or "",
                        last_name=contact.last_name or "",
                        gpt_prompt=campaign.gpt_prompt or "یک پیام تبلیغاتی مختصر بنویس",
                        products=products if campaign.include_products else None
                    )
                else:
                    # Use template with variable substitution
                    template = campaign.message_template or "سلام {{first_name}} جان، از افراکالا پیامی داریم."
                    message = template.replace("{{first_name}}", contact.first_name or "")
                    message = message.replace("{{last_name}}", contact.last_name or "")

                cc.generated_message = message

                # Send via Green API
                client = GreenAPIClient(account.instance_id, account.api_token)
                
                if campaign.send_image and campaign.image_url:
                    msg_id = await client.send_image(contact.phone, campaign.image_url, message)
                else:
                    msg_id = await client.send_message(contact.phone, message)

                if msg_id:
                    cc.status = MessageStatus.sent
                    cc.sent_at = datetime.utcnow()
                    cc.green_api_message_id = msg_id
                    cc.account_id = account.id

                    # Update counters
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

            # Human-like delay
            delay = random.uniform(settings.default_min_delay, settings.default_max_delay)
            await asyncio.sleep(delay)

        # Check if all done
        remaining = await db.execute(
            select(CampaignContact).where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status.in_([MessageStatus.pending, MessageStatus.queued])
            )
        )
        if not remaining.scalars().first():
            campaign.status = CampaignStatus.completed
            campaign.completed_at = datetime.utcnow()
            await db.commit()
```

---

## PHASE 5 — Celery Workers

### `backend/app/workers/celery_app.py`
```python
from celery import Celery
from app.config import settings

celery_app = Celery(
    "whatsapp_sender",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Tehran",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,  # One task at a time
    task_acks_late=True,
)
```

### `backend/app/workers/tasks.py`
```python
import asyncio
from app.workers.celery_app import celery_app
from app.services.campaign_runner import run_campaign


@celery_app.task(bind=True, name="tasks.run_campaign", max_retries=3)
def task_run_campaign(self, campaign_id: str):
    """Run a campaign in the background."""
    try:
        asyncio.run(run_campaign(campaign_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="tasks.reset_daily_counters")
def task_reset_daily_counters():
    """Reset sent_today counters at midnight. Schedule this with celery beat."""
    import asyncio
    from app.database import AsyncSessionLocal
    from app.models.account import Account
    from sqlalchemy import update
    from datetime import date

    async def _reset():
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Account).values(
                    sent_today=0,
                    last_reset_date=date.today()
                )
            )
            await db.commit()

    asyncio.run(_reset())


@celery_app.task(name="tasks.update_daily_limits")
def task_update_daily_limits():
    """Recalculate daily limits based on formula. Run every hour."""
    import asyncio
    from app.database import AsyncSessionLocal
    from app.models.account import Account
    from sqlalchemy import select

    async def _update():
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Account))
            accounts = result.scalars().all()
            for account in accounts:
                account.daily_limit = account.computed_daily_limit
            await db.commit()

    asyncio.run(_update())
```

---

## PHASE 6 — API Routes

### `backend/app/api/v1/accounts.py`
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient
from app.config import settings
import uuid

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/")
async def list_accounts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Account).order_by(Account.created_at.desc()))
    accounts = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "name": a.name,
            "instance_id": a.instance_id,
            "phone": a.phone,
            "status": a.status,
            "sent_today": a.sent_today,
            "daily_limit": a.computed_daily_limit,
            "days_active": a.days_active,
        }
        for a in accounts
    ]


@router.post("/")
async def create_account(
    name: str,
    instance_id: str,
    api_token: str,
    db: AsyncSession = Depends(get_db)
):
    account = Account(name=name, instance_id=instance_id, api_token=api_token)
    db.add(account)
    await db.commit()
    await db.refresh(account)
    
    # Configure webhook automatically
    webhook_url = f"{settings.webhook_base_url}/api/v1/webhook/{instance_id}"
    client = GreenAPIClient(instance_id, api_token)
    try:
        await client.set_webhook(webhook_url)
    except Exception as e:
        print(f"Warning: Could not set webhook: {e}")

    return {"id": str(account.id), "name": account.name, "status": account.status}


@router.get("/{account_id}/status")
async def check_account_status(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    
    client = GreenAPIClient(account.instance_id, account.api_token)
    state = await client.get_state()
    
    # Update status in DB
    if state == "authorized":
        account.status = AccountStatus.active
        account.days_active += 1
    elif state == "blocked":
        account.status = AccountStatus.banned
    else:
        account.status = AccountStatus.disconnected
    
    await db.commit()
    return {"state": state, "status": account.status}


@router.delete("/{account_id}")
async def delete_account(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    await db.delete(account)
    await db.commit()
    return {"success": True}
```

### `backend/app/api/v1/webhook.py`
```python
"""
Green API Webhook receiver.
Green API POSTs all WhatsApp events here.
"""
import json
from datetime import datetime
from fastapi import APIRouter, Request, BackgroundTasks
from app.database import AsyncSessionLocal
from app.models.inbox import InboxMessage

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/{instance_id}")
async def receive_webhook(
    instance_id: str,
    request: Request,
    background_tasks: BackgroundTasks
):
    body = await request.json()
    background_tasks.add_task(process_webhook, instance_id, body)
    return {"status": "received"}


async def process_webhook(instance_id: str, payload: dict):
    """Process incoming webhook payload from Green API."""
    webhook_type = payload.get("typeWebhook", "")
    
    if webhook_type == "incomingMessageReceived":
        await _handle_incoming_message(instance_id, payload)
    elif webhook_type == "stateInstanceChanged":
        await _handle_state_change(instance_id, payload)
    elif webhook_type == "outgoingMessageStatus":
        await _handle_message_status(instance_id, payload)


async def _handle_incoming_message(instance_id: str, payload: dict):
    """Save incoming message to DB."""
    data = payload.get("messageData", {})
    sender_data = payload.get("senderData", {})
    
    msg = InboxMessage(
        instance_id=instance_id,
        sender_phone=sender_data.get("sender", "").replace("@c.us", "").replace("@g.us", ""),
        sender_name=sender_data.get("senderName", ""),
        message_type=data.get("typeMessage", "text"),
        text_content=data.get("textMessageData", {}).get("textMessage", ""),
        is_group="@g.us" in sender_data.get("chatId", ""),
        group_name=sender_data.get("chatName", ""),
        original_payload=json.dumps(payload, ensure_ascii=False),
        timestamp=datetime.fromtimestamp(payload.get("timestamp", 0))
    )
    
    async with AsyncSessionLocal() as db:
        db.add(msg)
        # Update received_today for the account
        from app.models.account import Account
        from sqlalchemy import select
        result = await db.execute(
            select(Account).where(Account.instance_id == instance_id)
        )
        account = result.scalar_one_or_none()
        if account:
            account.received_today += 1
        await db.commit()


async def _handle_state_change(instance_id: str, payload: dict):
    """Handle account state changes (banned, disconnected, etc.)."""
    state = payload.get("stateInstance", "")
    if state in ("blocked", "sleepMode"):
        from app.models.account import Account, AccountStatus
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Account).where(Account.instance_id == instance_id)
            )
            account = result.scalar_one_or_none()
            if account:
                account.status = AccountStatus.banned if state == "blocked" else AccountStatus.disconnected
                account.banned_at = datetime.utcnow()
                account.ban_reason = f"State changed to: {state}"
                await db.commit()
                print(f"[ALERT] Account {instance_id} status: {state}")


async def _handle_message_status(instance_id: str, payload: dict):
    """Update message delivery status."""
    msg_id = payload.get("idMessage", "")
    status = payload.get("status", "")
    if not msg_id:
        return
    
    from app.models.campaign import CampaignContact
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CampaignContact).where(
                CampaignContact.green_api_message_id == msg_id
            )
        )
        cc = result.scalar_one_or_none()
        if cc:
            # Update tick status
            cc.error_message = f"delivery: {status}"
            await db.commit()
```

### `backend/app/api/v1/campaigns.py`
```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.campaign import Campaign, CampaignContact, CampaignStatus, MessageStatus
from app.models.contact import Contact
from app.workers.tasks import task_run_campaign
import uuid

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("/")
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))
    campaigns = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "status": c.status,
            "total_contacts": c.total_contacts,
            "sent_count": c.sent_count,
            "failed_count": c.failed_count,
            "created_at": str(c.created_at),
        }
        for c in campaigns
    ]


@router.post("/")
async def create_campaign(
    name: str,
    use_gpt: bool = True,
    gpt_prompt: str = None,
    message_template: str = None,
    include_products: bool = False,
    product_count: int = 3,
    send_image: bool = False,
    image_url: str = None,
    db: AsyncSession = Depends(get_db)
):
    campaign = Campaign(
        name=name,
        use_gpt=use_gpt,
        gpt_prompt=gpt_prompt,
        message_template=message_template,
        include_products=include_products,
        product_count=product_count,
        send_image=send_image,
        image_url=image_url
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return {"id": str(campaign.id), "name": campaign.name}


@router.post("/{campaign_id}/contacts")
async def add_contacts_to_campaign(
    campaign_id: str,
    contact_ids: list[str],
    db: AsyncSession = Depends(get_db)
):
    """Add contacts to a campaign."""
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    count = 0
    for cid in contact_ids:
        cc = CampaignContact(
            campaign_id=campaign.id,
            contact_id=uuid.UUID(cid),
            status=MessageStatus.pending
        )
        db.add(cc)
        count += 1

    campaign.total_contacts += count
    await db.commit()
    return {"added": count}


@router.post("/{campaign_id}/start")
async def start_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if campaign.status == CampaignStatus.running:
        raise HTTPException(400, "Campaign already running")

    campaign.status = CampaignStatus.running
    await db.commit()

    # Launch Celery task
    task_run_campaign.delay(campaign_id)
    return {"status": "started", "campaign_id": campaign_id}


@router.post("/{campaign_id}/pause")
async def pause_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    campaign.status = CampaignStatus.paused
    await db.commit()
    return {"status": "paused"}


@router.post("/{campaign_id}/resume")
async def resume_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    campaign.status = CampaignStatus.running
    await db.commit()
    task_run_campaign.delay(campaign_id)
    return {"status": "resumed"}


@router.get("/{campaign_id}/progress")
async def campaign_progress(campaign_id: str, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    
    stats = await db.execute(
        select(CampaignContact.status, func.count())
        .where(CampaignContact.campaign_id == campaign.id)
        .group_by(CampaignContact.status)
    )
    status_counts = {row[0]: row[1] for row in stats.all()}
    
    return {
        "campaign_id": campaign_id,
        "name": campaign.name,
        "status": campaign.status,
        "total": campaign.total_contacts,
        "sent": campaign.sent_count,
        "failed": campaign.failed_count,
        "pending": status_counts.get(MessageStatus.pending, 0),
        "progress_pct": round(
            (campaign.sent_count / campaign.total_contacts * 100)
            if campaign.total_contacts > 0 else 0, 1
        )
    }
```

### `backend/app/api/v1/contacts.py`
```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.database import get_db
from app.models.contact import Contact
from app.services.excel_service import parse_contacts_excel
from app.services.green_api import GreenAPIClient
from app.models.inbox import Blacklist
from datetime import datetime

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("/")
async def list_contacts(
    search: str = None,
    has_whatsapp: bool = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Contact).where(Contact.blacklisted == False)
    if search:
        query = query.where(
            or_(
                Contact.phone.contains(search),
                Contact.first_name.ilike(f"%{search}%"),
                Contact.last_name.ilike(f"%{search}%")
            )
        )
    if has_whatsapp is not None:
        query = query.where(Contact.has_whatsapp == has_whatsapp)
    
    result = await db.execute(query.limit(200))
    contacts = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "phone": c.phone,
            "name": c.full_name,
            "has_whatsapp": c.has_whatsapp,
            "province": c.province,
        }
        for c in contacts
    ]


@router.post("/import")
async def import_from_excel(
    file: UploadFile = File(...),
    source: str = "excel_import",
    db: AsyncSession = Depends(get_db)
):
    """Import contacts from Excel file."""
    content = await file.read()
    contacts_data = parse_contacts_excel(content)

    added = 0
    skipped = 0
    for data in contacts_data:
        # Check if exists
        existing = await db.execute(
            select(Contact).where(Contact.phone == data["phone"])
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue
        
        contact = Contact(**data, source=source)
        db.add(contact)
        added += 1

    await db.commit()
    return {"added": added, "skipped": skipped, "total_in_file": len(contacts_data)}


@router.post("/{contact_id}/check-whatsapp")
async def check_whatsapp(
    contact_id: str,
    instance_id: str,
    api_token: str,
    db: AsyncSession = Depends(get_db)
):
    """Check if a contact has WhatsApp using a given account."""
    import uuid
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    
    client = GreenAPIClient(instance_id, api_token)
    has_wa = await client.check_whatsapp(contact.phone)
    
    contact.has_whatsapp = has_wa
    contact.whatsapp_checked_at = datetime.utcnow()
    await db.commit()
    
    return {"phone": contact.phone, "has_whatsapp": has_wa}


@router.post("/blacklist")
async def add_to_blacklist(phone: str, reason: str = None, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Blacklist).where(Blacklist.phone == phone))
    if existing.scalar_one_or_none():
        return {"status": "already_blacklisted"}
    
    bl = Blacklist(phone=phone, reason=reason)
    db.add(bl)
    
    # Also mark contact as blacklisted
    contact = await db.execute(select(Contact).where(Contact.phone == phone))
    c = contact.scalar_one_or_none()
    if c:
        c.blacklisted = True
        c.blacklist_reason = reason
    
    await db.commit()
    return {"status": "blacklisted", "phone": phone}
```

### `backend/app/api/v1/dashboard.py`
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.campaign import Campaign, CampaignContact, MessageStatus
from app.models.inbox import InboxMessage
from app.services.rate_limiter import get_current_tehran_hour, get_max_per_hour_for_current_time

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Real-time dashboard statistics."""
    
    # Account stats
    acc_result = await db.execute(select(Account))
    accounts = acc_result.scalars().all()
    
    # Campaign stats
    camp_result = await db.execute(
        select(func.count()).where(Campaign.status == "running")
    )
    active_campaigns = camp_result.scalar()
    
    # Messages sent today (sum across all accounts)
    sent_today = sum(a.sent_today for a in accounts)
    
    # Current rate limit
    current_hour = get_current_tehran_hour()
    max_per_hour = get_max_per_hour_for_current_time()
    
    # Inbox count (last 24h)
    from datetime import datetime, timedelta
    inbox_result = await db.execute(
        select(func.count()).where(
            InboxMessage.received_at >= datetime.utcnow() - timedelta(hours=24)
        )
    )
    inbox_count = inbox_result.scalar()
    
    return {
        "accounts": {
            "total": len(accounts),
            "active": sum(1 for a in accounts if a.status == AccountStatus.active),
            "banned": sum(1 for a in accounts if a.status == AccountStatus.banned),
            "detail": [
                {
                    "name": a.name,
                    "phone": a.phone,
                    "status": a.status,
                    "sent_today": a.sent_today,
                    "daily_limit": a.computed_daily_limit,
                }
                for a in accounts
            ]
        },
        "campaigns": {
            "active": active_campaigns,
        },
        "messages": {
            "sent_today": sent_today,
            "inbox_24h": inbox_count,
        },
        "rate_limiter": {
            "tehran_hour": current_hour,
            "max_per_hour": max_per_hour,
            "is_sending_allowed": max_per_hour > 0,
        }
    }
```

---

## PHASE 7 — Main FastAPI App

### `backend/app/main.py`
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.api.v1 import accounts, campaigns, contacts, webhook, dashboard

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title="Afrakala WhatsApp Sender",
    description="واتس‌اپ سندر حرفه‌ای افراکالا با Green API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(accounts.router, prefix="/api/v1")
app.include_router(campaigns.router, prefix="/api/v1")
app.include_router(contacts.router, prefix="/api/v1")
app.include_router(webhook.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "Afrakala WhatsApp Sender"}
```

---

## PHASE 8 — Docker Setup

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
    command: celery -A app.workers.celery_app beat --loglevel=info --schedule=/tmp/celerybeat-schedule

volumes:
  postgres_data:
```

### `backend/Dockerfile`
```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## PHASE 9 — Frontend Dashboard (Minimal HTML)

### `frontend/index.html`
Create a single-file Persian monitoring dashboard with:
- Real-time account status cards
- Campaign progress bars
- Today's send count per account
- Rate limiter status (current hour, max/hour)
- Inbox latest messages
- Simple campaign start/pause buttons

Use vanilla JavaScript with fetch() to poll `/api/v1/dashboard/stats` every 10 seconds.
Use RTL (right-to-left) layout for Persian text.
Use Tailwind CDN for styling.
Color scheme: green for active, red for banned, yellow for paused.

---

## PHASE 10 — README

### `README.md`
Write a comprehensive README in Persian that covers:
1. معرفی پروژه
2. پیش‌نیازها (Docker, Python 3.11, Green API account)
3. نصب و راه‌اندازی (clone → copy .env → docker-compose up)
4. راهنمای استفاده
5. نقاط API
6. مراحل اتصال Green API
7. ساختار پروژه

---

## PHASE 11 — Final Git Commit

After all files are created and verified:

```bash
# Install dependencies to verify no errors
cd backend
pip install -r requirements.txt --quiet

# Run a quick syntax check on all Python files
python -m py_compile app/main.py app/config.py app/database.py
python -m py_compile app/models/account.py app/models/contact.py
python -m py_compile app/models/campaign.py app/models/inbox.py
python -m py_compile app/services/green_api.py app/services/gpt_service.py
python -m py_compile app/api/v1/accounts.py app/api/v1/campaigns.py
cd ..

# Git operations
git add -A
git commit -m "feat: complete Afrakala WhatsApp Sender Platform v1.0

- Multi-account WhatsApp management via Green API
- Campaign management with AI-powered message generation  
- Time-based rate limiting (Iranian business hours)
- Excel contact import with normalization
- Webhook receiver for incoming messages + ban detection
- Real-time monitoring dashboard
- Celery background workers with Redis
- PostgreSQL database with SQLAlchemy 2.0
- Docker Compose for easy deployment
- Daily limit formula based on account activity

Stack: FastAPI + PostgreSQL + Redis + Celery + Green API + OpenAI"

git push origin main
```

---

## IMPORTANT NOTES

1. After building, the user needs to:
   - Sign up at green-api.com and create instances (one per WhatsApp number)
   - Copy each instance_id and api_token to the app via the accounts API
   - Scan QR code in Green API dashboard to connect each number
   - Set OPENAI_API_KEY in .env
   - Run: `docker-compose up -d`
   - Access dashboard at: http://localhost:8000 (API) and frontend/index.html

2. For local folder save: all files should be in the current directory which maps to the user's local computer folder.

3. The webhook URL needs to be publicly accessible for Green API to call. Use ngrok for development: `ngrok http 8000`

4. Green API free tier: 200 messages/day. Paid plans for production.