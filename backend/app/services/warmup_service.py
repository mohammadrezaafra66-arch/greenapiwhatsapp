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
