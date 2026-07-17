"""Green API Partner client. Token NEVER logged, NEVER returned.

⚠️ The partner token lives IN THE URL. Never log the URL, never put it in an
exception message, never echo it in a response. There is a mandatory test asserting
the raised error contains neither the token nor the `gac.` prefix.
"""
import httpx
from app.config import settings


class PartnerNotConfigured(Exception):
    """GREEN_PARTNER_TOKEN missing."""


def is_configured(platform: str = "whatsapp") -> bool:
    from app.services.platforms import partner_credentials
    token, _ = partner_credentials(platform)
    return bool(token)


def _require_creds(platform: str = "whatsapp") -> tuple[str, str]:
    """(token, api_url) for the platform's OWN partner project. TG and WA keys are never
    conflated — this delegates to services.platforms.partner_credentials."""
    from app.services.platforms import partner_credentials
    token, url = partner_credentials(platform)
    if not token:
        label = "تلگرام" if (platform or "").lower() == "telegram" else "واتساپ"
        raise PartnerNotConfigured(f"توکن پارتنر {label} تنظیم نشده است")
    return token, url


def _require_token(platform: str = "whatsapp") -> str:
    """Backward-compatible: return just the token for a platform (WhatsApp by default)."""
    token, _ = _require_creds(platform)
    return token


async def _partner_post(method: str, body: dict | None = None, platform: str = "whatsapp"):
    token, api_url = _require_creds(platform)
    url = f"{api_url.rstrip('/')}/partner/{method}/{token}"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(url, json=body or {})
    if r.status_code >= 400:
        # NEVER include url/token in the error.
        raise RuntimeError(f"Partner method {method} failed: HTTP {r.status_code}")
    return r.json()


async def get_instances(platform: str = "whatsapp") -> list[dict]:
    """List ALL instances on the partner account (incl. ones deleted in the last
    ~3 months, flagged deleted=true). Safe, read-only."""
    return await _partner_post("getInstances", platform=platform)


async def create_instance(payload: dict, platform: str = "whatsapp") -> dict:
    return await _partner_post("createInstance", payload, platform=platform)


async def delete_instance_account(id_instance: int, platform: str = "whatsapp") -> dict:
    return await _partner_post("deleteInstanceAccount", {"idInstance": int(id_instance)},
                               platform=platform)
