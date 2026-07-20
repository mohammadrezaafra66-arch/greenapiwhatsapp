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

# V35 PART 1 — automatic daily WhatsApp Status posting is PERMANENTLY DISABLED.
# The legacy 10:00 Tehran "warm-up status" auto-posted a public status every day (the
# behaviour the user asked us to stop) and carries real ban risk. This flag is a guard so
# the feature cannot silently re-enable itself if `post_daily_status` is ever re-imported
# or re-wired: the function short-circuits before touching the Green API status endpoint.
DAILY_STATUS_POSTING_DISABLED = True

async def post_daily_status(client, message: str = "افراکالا - لوازم خانگی عمده"):
    """DISABLED (V35 PART 1): guarded no-op — never posts a WhatsApp status.

    Kept only so any lingering import/reference stays valid; it must not send a status.
    """
    if DAILY_STATUS_POSTING_DISABLED:
        return None
    # Unreachable while DAILY_STATUS_POSTING_DISABLED is True. Do not remove the guard.
    try:
        await client.send_status_text(message, bg_color="#25D366")
    except Exception as e:
        print(f"[Warmup] Status post failed: {e}")
