"""
Full Green API client — ALL endpoints implemented.
Docs: https://green-api.com/en/docs/api/
"""
import httpx
from typing import Optional
from app.config import settings


class GreenAPIClient:
    def __init__(self, instance_id: str, api_token: str):
        self.instance_id = instance_id
        self.api_token = api_token
        self.base_url = f"https://api.green-api.com/waInstance{instance_id}"

    async def _get(self, endpoint: str) -> dict:
        url = f"{self.base_url}/{endpoint}/{self.api_token}"
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(url)
            r.raise_for_status()
            return r.json()

    async def _post(self, endpoint: str, data: dict = None) -> dict:
        url = f"{self.base_url}/{endpoint}/{self.api_token}"
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(url, json=data or {})
            r.raise_for_status()
            return r.json()

    # ── ACCOUNT ──────────────────────────────────────────
    async def get_state(self) -> str:
        r = await self._get("getStateInstance")
        return r.get("stateInstance", "unknown")

    async def get_settings(self) -> dict:
        return await self._get("getSettings")

    async def set_settings(self, settings_dict: dict) -> bool:
        r = await self._post("setSettings", settings_dict)
        return r.get("saveSettings", False)

    async def set_webhook(self, webhook_url: str) -> bool:
        return await self.set_settings({
            "webhookUrl": webhook_url,
            "outgoingWebhook": "yes",
            "incomingWebhook": "yes",
            "stateWebhook": "yes",
            "delaySendMessagesMilliseconds": 3000
        })

    async def reboot(self) -> bool:
        r = await self._get("reboot")
        return r.get("isReboot", False)

    async def logout(self) -> bool:
        r = await self._get("logout")
        return r.get("isLogout", False)

    async def get_qr(self) -> str:
        """Returns base64 QR image."""
        r = await self._get("qr")
        return r.get("message", "")

    async def get_auth_code(self, phone: str) -> dict:
        """Login by phone number without QR scan."""
        phone = self._normalize(phone)
        return await self._post("getAuthorizationCode", {"phoneNumber": int(phone)})

    async def get_wa_settings(self) -> dict:
        """Get WhatsApp account info (name, phone, etc)."""
        return await self._get("getWaSettings")

    async def set_profile_picture(self, image_path: str) -> bool:
        r = await self._post("setProfilePicture", {"imagePath": image_path})
        return r.get("setProfilePicture", False)

    # ── SENDING ──────────────────────────────────────────
    async def send_message(self, phone: str, message: str) -> Optional[str]:
        r = await self._post("sendMessage", {
            "chatId": self._chat_id(phone),
            "message": message
        })
        return r.get("idMessage")

    async def send_image(self, phone: str, image_url: str, caption: str = "") -> Optional[str]:
        r = await self._post("sendFileByUrl", {
            "chatId": self._chat_id(phone),
            "urlFile": image_url,
            "fileName": "image.jpg",
            "caption": caption
        })
        return r.get("idMessage")

    async def send_file_url(self, phone: str, url: str, filename: str, caption: str = "") -> Optional[str]:
        r = await self._post("sendFileByUrl", {
            "chatId": self._chat_id(phone),
            "urlFile": url,
            "fileName": filename,
            "caption": caption
        })
        return r.get("idMessage")

    async def send_poll(self, phone: str, question: str, options: list[str], multiple: bool = False) -> Optional[str]:
        r = await self._post("sendPoll", {
            "chatId": self._chat_id(phone),
            "message": question,
            "options": [{"optionName": o} for o in options],
            "multipleAnswers": multiple
        })
        return r.get("idMessage")

    async def send_location(self, phone: str, lat: float, lon: float, name: str = "") -> Optional[str]:
        r = await self._post("sendLocation", {
            "chatId": self._chat_id(phone),
            "latitude": lat,
            "longitude": lon,
            "nameLocation": name
        })
        return r.get("idMessage")

    async def send_contact(self, phone: str, contact_phone: str, contact_name: str) -> Optional[str]:
        r = await self._post("sendContact", {
            "chatId": self._chat_id(phone),
            "contact": {"phoneContact": int(contact_phone), "firstName": contact_name}
        })
        return r.get("idMessage")

    async def send_interactive_buttons(self, phone: str, body: str, buttons: list[str], footer: str = "") -> Optional[str]:
        """Send message with up to 3 clickable buttons."""
        btn_list = [{"type": "replyButton", "reply": {"id": str(i+1), "title": b}} for i, b in enumerate(buttons[:3])]
        r = await self._post("sendInteractiveButtons", {
            "chatId": self._chat_id(phone),
            "contentText": body,
            "footer": footer,
            "buttons": btn_list
        })
        return r.get("idMessage")

    async def forward_messages(self, phone: str, chat_id_from: str, message_ids: list[str]) -> Optional[str]:
        r = await self._post("forwardMessages", {
            "chatId": self._chat_id(phone),
            "chatIdFrom": chat_id_from,
            "messages": message_ids
        })
        return r.get("idMessage")

    # ── STATUSES ─────────────────────────────────────────
    async def send_status_text(self, text: str, bg_color: str = "#FFFFFF") -> Optional[str]:
        r = await self._post("sendTextStatus", {"message": text, "backgroundColor": bg_color, "font": "SANS_SERIF"})
        return r.get("idMessage")

    async def send_status_image(self, image_url: str, caption: str = "") -> Optional[str]:
        r = await self._post("sendMediaStatus", {"urlFile": image_url, "fileName": "status.jpg", "caption": caption})
        return r.get("idMessage")

    async def get_status_statistics(self, message_id: str) -> dict:
        return await self._post("getStatusStatistic", {"idMessage": message_id})

    # ── RECEIVING ────────────────────────────────────────
    async def receive_notification(self) -> Optional[dict]:
        """HTTP polling mode: get one pending notification."""
        try:
            r = await self._get("receiveNotification")
            return r if r else None
        except Exception:
            return None

    async def delete_notification(self, receipt_id: int) -> bool:
        url = f"{self.base_url}/deleteNotification/{self.api_token}/{receipt_id}"
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.delete(url)
            return r.json().get("result", False)

    # ── SERVICE ──────────────────────────────────────────
    async def check_whatsapp(self, phone: str) -> bool:
        phone = self._normalize(phone)
        r = await self._post("checkWhatsapp", {"phoneNumber": int(phone)})
        return r.get("existsWhatsapp", False)

    async def get_avatar(self, phone: str) -> Optional[str]:
        r = await self._post("getAvatar", {"chatId": self._chat_id(phone)})
        return r.get("urlAvatar")

    async def get_contacts(self) -> list[dict]:
        return await self._get("getContacts")

    async def get_contact_info(self, phone: str) -> dict:
        return await self._post("getContactInfo", {"chatId": self._chat_id(phone)})

    async def get_chat_history(self, phone: str, count: int = 50) -> list[dict]:
        return await self._post("getChatHistory", {"chatId": self._chat_id(phone), "count": count})

    async def mark_as_read(self, phone: str, message_id: str) -> bool:
        r = await self._post("readChat", {"chatId": self._chat_id(phone), "idMessage": message_id})
        return r.get("setRead", False)

    async def archive_chat(self, phone: str) -> bool:
        r = await self._post("archiveChat", {"chatId": self._chat_id(phone)})
        return r.get("isArchived", False)

    # ── QUEUE ────────────────────────────────────────────
    async def show_messages_queue(self) -> list[dict]:
        return await self._get("showMessagesQueue")

    async def clear_messages_queue(self) -> bool:
        r = await self._get("clearMessagesQueue")
        return r.get("isCleared", False)

    # ── GROUPS ───────────────────────────────────────────
    async def create_group(self, name: str, phones: list[str]) -> dict:
        return await self._post("createGroup", {
            "groupName": name,
            "chatIds": [self._chat_id(p) for p in phones]
        })

    async def add_group_participant(self, group_id: str, phone: str) -> dict:
        return await self._post("addGroupParticipant", {"groupId": group_id, "participantChatId": self._chat_id(phone)})

    async def remove_group_participant(self, group_id: str, phone: str) -> dict:
        return await self._post("removeGroupParticipant", {"groupId": group_id, "participantChatId": self._chat_id(phone)})

    async def get_group_data(self, group_id: str) -> dict:
        return await self._post("getGroupData", {"groupId": group_id})

    async def send_group_message(self, group_id: str, message: str) -> Optional[str]:
        r = await self._post("sendMessage", {"chatId": group_id, "message": message})
        return r.get("idMessage")

    # ── HELPERS ──────────────────────────────────────────
    @staticmethod
    def _normalize(phone: str) -> str:
        import re
        phone = re.sub(r"\D", "", str(phone).strip())
        if phone.startswith("0") and len(phone) == 11:
            phone = "98" + phone[1:]
        elif len(phone) == 10 and phone.startswith("9"):
            phone = "98" + phone
        return phone

    def _chat_id(self, phone: str) -> str:
        return f"{self._normalize(phone)}@c.us"

    # Backward-compatible alias (v1 used _normalize_phone)
    _normalize_phone = _normalize
