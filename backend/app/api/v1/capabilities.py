"""V14 PART G — capability registry endpoint. The user's single source of truth for
what their Green API plan can do. Seeded by the PHASE 0 probe, updated by every call site.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.utils.shamsi import to_shamsi

router = APIRouter(prefix="/capabilities", tags=["capabilities"])

# Group methods for the settings page.
CATEGORY = {
    "sending": ["sendMessage", "sendFileByUrl", "sendFileByUpload", "sendPoll",
                "sendInteractiveButtons", "sendInteractiveButtonsReply", "sendContact",
                "sendLocation", "forwardMessages", "sendReaction"],
    "message_control": ["editMessage", "deleteMessage", "readChat", "getMessagesCount",
                        "showMessagesQueue", "clearMessagesQueue", "getWebhooksBufferCount"],
    "chat_profile": ["archiveChat", "unarchiveChat", "setDisappearingChat", "setProfilePicture",
                     "getContactInfo", "getAvatar", "checkWhatsapp", "getChatHistory"],
    "statuses": ["sendTextStatus", "sendMediaStatus", "sendVoiceStatus", "deleteStatus",
                 "getOutgoingStatuses", "getIncomingStatuses", "getStatusStatistic"],
    "groups": ["createGroup", "updateGroupName", "getGroupData", "updateGroupSettings",
               "addGroupParticipant", "removeGroupParticipant", "setGroupAdmin", "removeAdmin",
               "setGroupPicture", "leaveGroup"],
    "calls": ["lastIncomingCalls", "lastOutgoingCalls"],
    "service": ["getSettings", "getStateInstance", "getWaSettings", "getContacts", "getChats",
                "lastIncomingMessages", "lastOutgoingMessages"],
    "partner": ["getInstances", "createInstance", "deleteInstanceAccount"],
}
CATEGORY_FA = {
    "sending": "ارسال پیام", "message_control": "کنترل پیام", "chat_profile": "چت و پروفایل",
    "statuses": "استوری‌ها", "groups": "گروه‌ها", "calls": "تماس‌ها",
    "service": "سرویس", "partner": "پارتنر", "other": "سایر",
}


def _category_of(method: str) -> str:
    for cat, methods in CATEGORY.items():
        if method in methods:
            return cat
    return "other"


@router.get("/")
async def capabilities(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text(
        "SELECT method, supported, last_status_code, last_checked, note "
        "FROM method_support ORDER BY method"
    ))).mappings().all()
    grouped: dict[str, list] = {}
    counts = {"supported": 0, "unsupported": 0, "unknown": 0}
    for r in rows:
        item = {
            "method": r["method"],
            "supported": r["supported"],
            "last_status_code": r["last_status_code"],
            "last_checked": to_shamsi(r["last_checked"]),
            "note": r["note"],
        }
        if r["supported"] is True:
            counts["supported"] += 1
        elif r["supported"] is False:
            counts["unsupported"] += 1
        else:
            counts["unknown"] += 1
        grouped.setdefault(_category_of(r["method"]), []).append(item)
    return {
        "counts": counts,
        "category_labels": CATEGORY_FA,
        "groups": grouped,
        "flat": [dict(r) | {"last_checked": to_shamsi(r["last_checked"])} for r in rows],
    }
