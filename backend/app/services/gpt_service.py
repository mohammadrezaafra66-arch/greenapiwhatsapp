from openai import AsyncOpenAI
from app.config import settings

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Lazily build the OpenAI client so the app can start without a key."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key or "missing")
    return _client


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

    r = await get_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_msg}],
        max_tokens=500, temperature=0.85
    )
    return r.choices[0].message.content.strip()


async def categorize_message(text: str) -> str:
    """Auto-categorize incoming message: price_inquiry / complaint / order / unsubscribe / other"""
    r = await get_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Categorize the Persian WhatsApp message into exactly one: price_inquiry, complaint, order, unsubscribe, other. Reply with only the category word."},
            {"role": "user", "content": text or ""}
        ],
        max_tokens=10
    )
    return r.choices[0].message.content.strip().lower()
