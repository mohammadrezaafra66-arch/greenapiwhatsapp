"""V67 Phase 7 — Shadow operator auth (D-P7-16).

No app-wide HTTP auth exists. Shadow routes use a settings-backed privileged
operator token + role header. Fail-closed when token unconfigured.
"""
from __future__ import annotations
import hmac
from fastapi import Header, HTTPException, Request

from app.config import settings


def _allowed_roles() -> set[str]:
    raw = getattr(settings, "v67_shadow_allowed_roles", "admin,operator") or ""
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


async def require_shadow_operator(
    request: Request,
    x_fleet_shadow_token: str | None = Header(default=None, alias="X-Fleet-Shadow-Token"),
    x_fleet_shadow_role: str | None = Header(default=None, alias="X-Fleet-Shadow-Role"),
    authorization: str | None = Header(default=None),
) -> dict:
    expected = getattr(settings, "v67_shadow_operator_token", "") or ""
    if not expected:
        raise HTTPException(503, "shadow_operator_token_unconfigured")

    provided = x_fleet_shadow_token
    if not provided and authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided = parts[1].strip()
    if not provided:
        raise HTTPException(401, "shadow_unauthenticated")
    if not hmac.compare_digest(str(provided), str(expected)):
        raise HTTPException(401, "shadow_invalid_token")

    role = (x_fleet_shadow_role or "").strip().lower()
    if not role:
        raise HTTPException(403, "shadow_role_required")
    if role not in _allowed_roles():
        raise HTTPException(403, "shadow_insufficient_role")
    return {"role": role, "authenticated": True}
