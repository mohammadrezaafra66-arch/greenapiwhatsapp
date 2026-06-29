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
