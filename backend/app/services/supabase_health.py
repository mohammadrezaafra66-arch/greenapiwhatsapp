"""V16 PART 1 — Supabase connectivity diagnostic.

Reusable check used by both the CLI script (scripts/check_supabase.py) and the
/reporting/supabase-status endpoint, so the products UI can tell apart:
  - reachable + data      → "connected"
  - reachable + no rows   → "empty"      (show «محصولی یافت نشد»)
  - not reachable / 401   → "disconnected" (show a banner, NOT an empty list)
"""
import asyncio
import socket
from urllib.parse import urlparse
import httpx
from app.config import settings


def _host_port() -> tuple[str, int]:
    u = urlparse(settings.supabase_url)
    return u.hostname or "192.168.170.10", (u.port or (443 if u.scheme == "https" else 80))


async def _tcp_ok(timeout: float = 3.0) -> bool:
    host, port = _host_port()
    try:
        fut = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except (asyncio.TimeoutError, OSError, socket.gaierror):
        return False


def _headers() -> dict:
    return {"apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {settings.supabase_anon_key}"}


async def check_supabase(products_table: str = "products") -> dict:
    """Run TCP → /auth/v1/health → authenticated REST probe, returning a structured result.
    `status` ∈ {connected, empty, disconnected}."""
    host, port = _host_port()
    result = {
        "url": settings.supabase_url,
        "tcp": {"ok": False, "detail": ""},
        "auth_health": {"http": None, "ok": False, "detail": ""},
        "rest_products": {"http": None, "ok": False, "count": None, "detail": ""},
        "reachable": False,
        "status": "disconnected",
    }

    result["tcp"]["ok"] = await _tcp_ok()
    result["tcp"]["detail"] = (
        f"TCP {host}:{port} قابل دسترسی است" if result["tcp"]["ok"]
        else f"TCP {host}:{port} پاسخ نداد — لپ‌تاپ Supabase خاموش است یا IP عوض شده")
    if not result["tcp"]["ok"]:
        return result

    # /auth/v1/health — gateway liveness
    try:
        async with httpx.AsyncClient(timeout=4) as c:
            r = await c.get(f"{settings.supabase_url}/auth/v1/health")
        result["auth_health"]["http"] = r.status_code
        result["auth_health"]["ok"] = r.status_code == 200
        result["auth_health"]["detail"] = "درگاه فعال است" if r.status_code == 200 else f"HTTP {r.status_code}"
    except Exception as e:
        result["auth_health"]["detail"] = f"خطا: {str(e)[:80]}"

    # authenticated REST probe
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get(f"{settings.supabase_url}/rest/v1/{products_table}",
                            params={"select": "id", "limit": "1"}, headers=_headers())
        rp = result["rest_products"]
        rp["http"] = r.status_code
        if r.status_code == 200:
            rows = r.json() if isinstance(r.json(), list) else []
            rp["ok"] = True
            rp["count"] = len(rows)
            rp["detail"] = "ok"
            result["reachable"] = True
            result["status"] = "connected" if rows else "empty"
        elif r.status_code in (401, 403):
            rp["detail"] = "کلید anon نامعتبر است یا دسترسی ندارد (۴۰۱/۴۰۳)"
        else:
            rp["detail"] = f"HTTP {r.status_code}"
    except Exception as e:
        result["rest_products"]["detail"] = f"خطا: {str(e)[:80]}"

    return result
