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
