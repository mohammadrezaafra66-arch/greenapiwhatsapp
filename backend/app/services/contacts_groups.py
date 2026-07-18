"""TG PART 5 — platform-agnostic contacts & groups helpers.

Green API's Groups methods (GetGroupData, AddGroupParticipant, CreateGroup, GetContacts,
GetChats, CheckAccount) are confirmed identical for WhatsApp and Telegram, so the existing
V19 admin-group / add-participant logic generalizes by branching the CLIENT on platform
(host + existence check) — these pure parsers extract the shared response shapes.

⚠️ Telegram's exact GetGroupData participants/isAdmin shape is "verify live" (flagged in the
report): it was not independently re-confirmed for Telegram, only assumed identical to WA.
"""
from __future__ import annotations


def parse_participants(group_data: dict) -> list[dict]:
    """Normalize the participants[] list from GetGroupData (same field on both platforms)."""
    return list((group_data or {}).get("participants") or [])


def group_size(group_data: dict) -> int:
    """Group member count, preferring an explicit size, else len(participants)."""
    d = group_data or {}
    return int(d.get("size") or len(parse_participants(d)) or 0)


def is_account_admin(group_data: dict, self_id: str) -> bool:
    """True if `self_id` (the instance's own chatId/wid) is an admin/creator of the group,
    per GetGroupData.participants[].isAdmin/isSuperAdmin. Matching is done on the id suffix so
    a bare number matches a '<id>@c.us' form and vice-versa."""
    target = _bare(self_id)
    for p in parse_participants(group_data):
        pid = _bare(p.get("id") or p.get("chatId") or "")
        if pid and pid == target and (p.get("isAdmin") or p.get("isSuperAdmin")):
            return True
    # Some responses expose the owner/creator separately.
    owner = _bare((group_data or {}).get("owner") or "")
    return bool(owner and owner == target)


def _bare(chat_id: str) -> str:
    """Strip a WhatsApp '@c.us'/'@g.us' suffix so ids compare by their numeric core."""
    return str(chat_id or "").split("@")[0].strip()


# ── invite-link vault (data-only; NO auto-join on either platform) ───────────
def is_auto_join_supported(platform: str) -> bool:
    """Neither WhatsApp nor Telegram exposes a documented join-by-invite-link method, so we
    NEVER auto-join. The link vault stores links as data only. Always False."""
    return False
