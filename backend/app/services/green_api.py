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

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        # Query params must go AFTER the token segment, not inside `endpoint`
        # (Green API URL shape: /waInstance{id}/{method}/{token}?query).
        url = f"{self.base_url}/{endpoint}/{self.api_token}"
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(url, params=params)
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

    async def set_webhook(self, webhook_url: str, delay_ms: int = 15000) -> bool:
        return await self.set_settings({
            "webhookUrl": webhook_url,
            "outgoingWebhook": "yes",
            "incomingWebhook": "yes",
            "stateWebhook": "yes",
            "delaySendMessagesMilliseconds": delay_ms
        })

    async def reboot(self) -> bool:
        r = await self._get("reboot")
        return r.get("isReboot", False)

    async def logout(self) -> bool:
        r = await self._get("logout")
        return r.get("isLogout", False)

    async def get_qr(self) -> str:
        """Return the base64 QR PNG, or '' if the instance isn't waiting for a scan.
        Green API only puts base64 in `message` when type == 'qrCode'; for
        'alreadyLogged'/'notAuthorized'/'error' the message is plain text."""
        r = await self._get("qr")
        return r.get("message", "") if r.get("type") == "qrCode" else ""

    async def get_qr_info(self) -> dict:
        """Raw QR state: {'type': ..., 'message': ...}.
        type is 'qrCode' (message=base64 png), 'alreadyLogged', 'notAuthorized', or 'error'."""
        r = await self._get("qr")
        return {"type": r.get("type", ""), "message": r.get("message", "")}

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

    async def send_file_upload(self, phone: str, file_bytes: bytes, filename: str, caption: str = "") -> Optional[str]:
        """Send a file from raw bytes via multipart upload (no public URL needed)."""
        url = f"{self.base_url}/sendFileByUpload/{self.api_token}"
        files = {"file": (filename, file_bytes)}
        data = {"chatId": self._chat_id(phone), "caption": caption}
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(url, data=data, files=files)
            r.raise_for_status()
            return r.json().get("idMessage")

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

    async def unarchive_chat(self, phone: str) -> bool:
        r = await self._post("unarchiveChat", {"chatId": self._chat_id(phone)})
        return r.get("isUnarchived", False)

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

    # ── SENDING — new methods ─────────────────────────────
    async def send_typing(self, phone: str, duration_seconds: int = 3) -> bool:
        """Show 'typing...' indicator before sending a message. Call before sendMessage."""
        r = await self._post("sendTyping", {
            "chatId": self._chat_id(phone),
            "time": duration_seconds
        })
        return r.get("chatId") is not None or r.get("waId") is not None or True

    async def edit_message(self, phone: str, message_id: str, new_text: str) -> bool:
        """Edit a previously sent text message."""
        r = await self._post("editMessage", {
            "chatId": self._chat_id(phone),
            "idMessage": message_id,
            "message": new_text
        })
        return r.get("editedMessage") is not None or "idMessage" in r

    async def delete_message(self, phone: str, message_id: str) -> bool:
        """Delete a sent message."""
        r = await self._post("deleteMessage", {
            "chatId": self._chat_id(phone),
            "idMessage": message_id
        })
        return r.get("deleteMessage", False) or "idMessage" in r

    async def upload_file(self, file_bytes: bytes, filename: str) -> Optional[str]:
        """Upload a file to Green API storage; returns a URL usable in sendFileByUrl."""
        url = f"{self.base_url}/uploadFile/{self.api_token}"
        files = {"file": (filename, file_bytes)}
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(url, files=files)
            r.raise_for_status()
            return r.json().get("urlFile")

    # ── RECEIVING ────────────────────────────────────────
    async def download_file(self, chat_id: str, message_id: str) -> Optional[str]:
        """Get download URL for a file received in an incoming message."""
        r = await self._post("downloadFile", {
            "chatId": chat_id,
            "idMessage": message_id
        })
        return r.get("downloadUrl")

    async def get_webhooks_count(self) -> int:
        """Number of notifications waiting in the incoming webhook queue."""
        r = await self._get("getWebhooksBufferCount")
        return r.get("webhooksBufferCount", 0)

    async def clear_webhooks_queue(self) -> bool:
        """Clear all pending notifications from the incoming webhook queue."""
        r = await self._get("clearWebhooksBuffer")
        return r.get("isCleared", False)

    # ── JOURNALS ─────────────────────────────────────────
    async def get_message(self, chat_id: str, message_id: str) -> dict:
        """Get a single message by ID."""
        return await self._post("getMessage", {
            "chatId": chat_id,
            "idMessage": message_id
        })

    async def last_incoming_messages(self, minutes: int = 1440) -> list[dict]:
        """Get incoming messages from the last N minutes (default 24h)."""
        r = await self._get("lastIncomingMessages", params={"minutes": minutes})
        return r if isinstance(r, list) else []

    async def last_outgoing_messages(self, minutes: int = 1440) -> list[dict]:
        """Get outgoing messages from the last N minutes."""
        r = await self._get("lastOutgoingMessages", params={"minutes": minutes})
        return r if isinstance(r, list) else []

    # ── SERVICE ──────────────────────────────────────────
    async def get_chats(self) -> list[dict]:
        """Get list of all active chats."""
        r = await self._get("getChats")
        return r if isinstance(r, list) else []

    async def set_disappearing_chat(self, phone: str, ephemeral: int = 0) -> bool:
        """Set disappearing messages timer. ephemeral: 0=off, 86400=1day, 604800=1week."""
        r = await self._post("setDisappearingChat", {
            "chatId": self._chat_id(phone),
            "ephemeral": ephemeral
        })
        return r.get("chatId") is not None or True

    # ── QUEUE ────────────────────────────────────────────
    async def get_messages_count(self) -> int:
        """Number of messages currently in the outgoing send queue."""
        r = await self._get("getMessagesCount")
        return r.get("count", 0)

    # ── CONTACTS ─────────────────────────────────────────
    async def add_contact(self, phone: str, first_name: str, last_name: str = "") -> bool:
        """Add a contact to the WhatsApp phone book of this account."""
        r = await self._post("addContact", {
            "phoneContact": int(self._normalize(phone)),
            "firstName": first_name,
            "lastName": last_name,
            "company": "افراکالا"
        })
        return r.get("saveContact", False) or "contactId" in r

    async def delete_contact(self, phone: str) -> bool:
        """Remove a contact from the phone book."""
        r = await self._post("deleteContact", {
            "phoneContact": int(self._normalize(phone))
        })
        return r.get("deleteContact", False)

    # ── GROUPS — new methods ──────────────────────────────
    async def update_group_name(self, group_id: str, name: str) -> bool:
        r = await self._post("updateGroupName", {"groupId": group_id, "groupName": name})
        return r.get("updateGroupName", False)

    async def set_group_admin(self, group_id: str, phone: str) -> bool:
        r = await self._post("setGroupAdmin", {
            "groupId": group_id,
            "participantChatId": self._chat_id(phone)
        })
        return r.get("setGroupAdmin", False)

    async def remove_group_admin(self, group_id: str, phone: str) -> bool:
        r = await self._post("removeGroupAdmin", {
            "groupId": group_id,
            "participantChatId": self._chat_id(phone)
        })
        return r.get("removeGroupAdmin", False)

    async def leave_group(self, group_id: str) -> bool:
        r = await self._post("leaveGroup", {"groupId": group_id})
        return r.get("leaveGroup", False)

    async def set_group_picture(self, group_id: str, image_bytes: bytes) -> bool:
        url = f"{self.base_url}/setGroupPicture/{self.api_token}"
        files = {"file": ("group.jpg", image_bytes)}
        data = {"groupId": group_id}
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(url, data=data, files=files)
            r.raise_for_status()
            return r.json().get("setGroupPicture", False)

    # ── STATUSES — new methods ───────────────────────────
    async def send_voice_status(self, audio_url: str) -> Optional[str]:
        r = await self._post("sendVoiceStatus", {"urlFile": audio_url, "fileName": "voice.ogg"})
        return r.get("idMessage")

    async def delete_status(self, message_id: str) -> bool:
        r = await self._post("deleteStatus", {"idMessage": message_id})
        return r.get("deleteStatus", False)

    async def get_incoming_statuses(self) -> list[dict]:
        r = await self._get("getIncomingStatuses")
        return r if isinstance(r, list) else []

    async def get_outgoing_statuses(self) -> list[dict]:
        r = await self._get("getOutgoingStatuses")
        return r if isinstance(r, list) else []

    # ── ACCOUNT ──────────────────────────────────────────
    async def update_api_token(self) -> Optional[str]:
        """Generate a new API token (old token stays valid for ~1h)."""
        r = await self._get("updateApiToken")
        return r.get("newApiToken")

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
