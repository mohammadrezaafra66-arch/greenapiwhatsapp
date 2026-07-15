"""V19 PART 1 — read a warm account's ADMIN-owned groups.

Only groups where the warm instance's own number is admin/superadmin can accept new
members, so the UI must show exactly those. Flow (Green API, webhook-only):
  1. getContacts?group=true → groups have type=="group" and id ending "@g.us".
     (Documented behavior: if the array is empty, retry.)
  2. getGroupData per group → owner/subject/size/participants[] (each id/isAdmin/isSuperAdmin).
     THROTTLED + CACHED: hammering getGroupData makes WhatsApp return an empty
     groupInviteLink and is a mild risk signal.
  3. Keep only groups where our own number is isAdmin or isSuperAdmin.

Green API access goes through the injected client, and the cache is best-effort Redis
(absent/erroring Redis just means no caching) — so this unit-tests with a mock client and
no Redis.
"""
import json
import logging
import re

logger = logging.getLogger("afrakala.warmup.groups")

GROUP_DATA_TTL = 6 * 3600      # cache getGroupData per group (throttle protection)
ADMIN_GROUPS_TTL = 1800        # cache the per-instance admin-groups sweep (UI throttle)
GET_CONTACTS_RETRIES = 3       # documented empty-array retry


def _digits(s: str) -> str:
    return re.sub(r"\D", "", str(s or ""))


def is_group_contact(c: dict) -> bool:
    return (isinstance(c, dict) and c.get("type") == "group"
            and str(c.get("id", "")).endswith("@g.us"))


def participant_is_admin(participants, own_number: str) -> bool:
    """True if `own_number` is in `participants` as isAdmin or isSuperAdmin."""
    own = _digits(own_number)
    if not own:
        return False
    for p in participants or []:
        pid = _digits(str(p.get("id", "")).split("@")[0])
        if pid and pid == own and (p.get("isAdmin") or p.get("isSuperAdmin")):
            return True
    return False


# ── best-effort Redis cache (absent Redis → no caching, never raises) ────────
async def _cache_get(key: str):
    try:
        from app.services import redis_rate_limiter
        r = await redis_rate_limiter.get_redis()
        v = await r.get(key)
        return json.loads(v) if v else None
    except Exception:
        return None


async def _cache_set(key: str, value, ttl: int):
    try:
        from app.services import redis_rate_limiter
        r = await redis_rate_limiter.get_redis()
        await r.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception:
        pass


async def get_group_contacts_with_retry(client, retries: int = GET_CONTACTS_RETRIES) -> list[dict]:
    """getContacts?group=true, retrying while the array is empty (documented behavior)."""
    contacts = []
    for _ in range(max(1, retries)):
        contacts = await client.get_group_contacts() or []
        if contacts:
            break
    return [c for c in contacts if is_group_contact(c)]


async def cached_group_data(client, group_id: str, use_cache: bool = True) -> dict:
    """getGroupData for one group, cached per group to throttle the call."""
    key = f"warmup:groupdata:{group_id}"
    if use_cache:
        cached = await _cache_get(key)
        if cached is not None:
            return cached
    try:
        data = await client.get_group_data(group_id)
    except Exception as e:
        logger.warning("getGroupData failed for %s: %s", group_id, e)
        return {}
    if use_cache and isinstance(data, dict) and data:
        await _cache_set(key, data, GROUP_DATA_TTL)
    return data if isinstance(data, dict) else {}


async def _own_number(client, own_number: str | None) -> str:
    if own_number:
        return own_number
    try:
        wa = await client.get_wa_settings()
        return str(wa.get("phone") or wa.get("wid") or "").split("@")[0]
    except Exception:
        return ""


async def list_admin_groups(client, own_number: str | None = None,
                            use_cache: bool = True) -> list[dict]:
    """Return the groups where this warm instance is admin/superadmin — the only groups it
    can add cold numbers to. Each item: {group_id, subject, size, is_admin}."""
    instance_id = getattr(client, "instance_id", "?")
    sweep_key = f"warmup:admingroups:{instance_id}"
    if use_cache:
        cached = await _cache_get(sweep_key)
        if cached is not None:
            return cached

    own = await _own_number(client, own_number)
    groups = await get_group_contacts_with_retry(client)
    admin_groups = []
    for g in groups:
        gid = g.get("id")
        if not gid:
            continue
        data = await cached_group_data(client, gid, use_cache=use_cache)
        participants = data.get("participants", []) if isinstance(data, dict) else []
        if participant_is_admin(participants, own):
            admin_groups.append({
                "group_id": gid,
                "subject": (data.get("subject") or g.get("name") or "").strip(),
                "size": int(data.get("size") or len(participants) or 0),
                "is_admin": True,
            })
    if use_cache:
        await _cache_set(sweep_key, admin_groups, ADMIN_GROUPS_TTL)
    return admin_groups
