"""V67 Phase 7.1 — Shadow-scoped temporary operator auth (D-P7-16).

NOT application-wide authentication.

Security rules:
- Token from Backend settings only (empty → 503 fail-closed)
- Privileged role is Backend-configured (`v67_shadow_operator_role`), NEVER client-assigned
- Client `X-Fleet-Shadow-Role` is ignored for privilege; if supplied and mismatches, 403
- Constant-time token compare via SHA-256 digests
- Token never logged / never returned
"""
from __future__ import annotations
import hashlib
import hmac
import logging
from fastapi import Header, HTTPException, Request

from app.config import settings

logger = logging.getLogger("afrakala.shadow_auth")


def _secure_equals(provided: str, expected: str) -> bool:
    """Length-safe constant-time compare."""
    a = hashlib.sha256(provided.encode("utf-8")).digest()
    b = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(a, b)


def _configured_role() -> str:
    role = (getattr(settings, "v67_shadow_operator_role", None) or "operator").strip().lower()
    allowed_raw = getattr(settings, "v67_shadow_allowed_roles", "admin,operator") or ""
    allowed = {x.strip().lower() for x in allowed_raw.split(",") if x.strip()}
    if role not in allowed:
        # Misconfiguration — fail closed
        return ""
    return role


async def require_shadow_operator(
    request: Request,
    x_fleet_shadow_token: str | None = Header(default=None, alias="X-Fleet-Shadow-Token"),
    x_fleet_shadow_role: str | None = Header(default=None, alias="X-Fleet-Shadow-Role"),
    authorization: str | None = Header(default=None),
) -> dict:
    expected = getattr(settings, "v67_shadow_operator_token", "") or ""
    if not expected:
        raise HTTPException(503, "shadow_operator_token_unconfigured")

    configured_role = _configured_role()
    if not configured_role:
        raise HTTPException(503, "shadow_operator_role_misconfigured")

    provided = x_fleet_shadow_token
    if not provided and authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided = parts[1].strip()
    if not provided:
        raise HTTPException(401, "shadow_unauthenticated")
    if not _secure_equals(str(provided), str(expected)):
        raise HTTPException(401, "shadow_invalid_token")

    # Client role header cannot grant privilege. Optional: reject spoof attempts.
    if x_fleet_shadow_role is not None and str(x_fleet_shadow_role).strip() != "":
        claimed = str(x_fleet_shadow_role).strip().lower()
        if claimed != configured_role:
            raise HTTPException(403, "shadow_role_spoof_rejected")

    # Do not log token. Identity is backend-configured role only.
    logger.info("shadow_operator_auth_ok role=%s path=%s", configured_role, request.url.path)
    return {
        "role": configured_role,
        "authenticated": True,
        "auth_mode": "shadow_scoped_temporary_token",
        "client_role_trusted": False,
    }
