"""
Full Green API client — ALL endpoints implemented.
Docs: https://green-api.com/en/docs/api/
"""
import httpx
import asyncio
import time
from typing import Optional
from app.config import settings

# ── A6: Green API concurrency safety ───────────────────────────────────────
# Each account is one Green API instance with its own rate limits. For 80
# accounts we cap concurrent requests per instance, back off on 429, and trip a
# circuit breaker after repeated failures so a dead/banned instance is skipped
# for a cooldown instead of hammering the API.
MAX_CONCURRENT_PER_INSTANCE = 5
CB_ERROR_THRESHOLD = 5      # consecutive errors before opening the breaker
CB_COOLDOWN_SECONDS = 300   # skip the instance for 5 minutes when open
MAX_429_RETRIES = 3

_semaphores: dict = {}   # (instance_id, loop_id) -> asyncio.Semaphore
_cb_errors: dict = {}    # instance_id -> consecutive error count
_cb_until: dict = {}     # instance_id -> monotonic time until which it is skipped


def _get_semaphore(instance_id: str) -> asyncio.Semaphore:
    # Key by (instance, loop) so each event loop (Celery runs one per task) gets
    # its own semaphore — an asyncio primitive can't be shared across loops.
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = 0
    key = (instance_id, loop_id)
    sem = _semaphores.get(key)
    if sem is None:
        sem = asyncio.Semaphore(MAX_CONCURRENT_PER_INSTANCE)
        _semaphores[key] = sem
    return sem


def _register_error(instance_id: str):
    _cb_errors[instance_id] = _cb_errors.get(instance_id, 0) + 1
    if _cb_errors[instance_id] >= CB_ERROR_THRESHOLD:
        _cb_until[instance_id] = time.monotonic() + CB_COOLDOWN_SECONDS


class GreenAPIClient:
    def __init__(self, instance_id: str, api_token: str):
        self.instance_id = instance_id
        self.api_token = api_token
        self.base_url = f"https://api.green-api.com/waInstance{instance_id}"

    async def _guarded(self, call):
        """Run an httpx call under the per-instance semaphore, with 429 backoff
        and circuit-breaker accounting. `call` is a coroutine factory returning
        an httpx.Response."""
        if _cb_until.get(self.instance_id, 0) > time.monotonic():
            raise RuntimeError(f"Green API instance {self.instance_id} temporarily degraded (circuit open)")
        async with _get_semaphore(self.instance_id):
            for attempt in range(MAX_429_RETRIES + 1):
                try:
                    r = await call()
                except Exception:
                    _register_error(self.instance_id)
                    raise
                if r.status_code == 429 and attempt < MAX_429_RETRIES:
                    await asyncio.sleep(2 ** attempt)  # 1, 2, 4s
                    continue
                try:
                    r.raise_for_status()
                except Exception:
                    _register_error(self.instance_id)
                    raise
                _cb_errors[self.instance_id] = 0  # success resets the breaker
                return r.json()

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        # Query params must go AFTER the token segment, not inside `endpoint`
        # (Green API URL shape: /waInstance{id}/{method}/{token}?query).
        url = f"{self.base_url}/{endpoint}/{self.api_token}"
        async def _call():
            async with httpx.AsyncClient(timeout=30) as c:
                return await c.get(url, params=params)
        return await self._guarded(_call)

    async def _post(self, endpoint: str, data: dict = None, timeout: int = 30) -> dict:
        url = f"{self.base_url}/{endpoint}/{self.api_token}"
        async def _call():
            async with httpx.AsyncClient(timeout=timeout) as c:
                return await c.post(url, json=data or {})
        return await self._guarded(_call)

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
        # Enable EVERY Green API notification type so all webhooks reach the backend.
        return await self.set_settings({
            "webhookUrl": webhook_url,
            "delaySendMessagesMilliseconds": delay_ms,
            "incomingWebhook": "yes",
            "outgoingWebhook": "yes",
            "outgoingMessageWebhook": "yes",
            "outgoingAPIMessageWebhook": "yes",
            "stateWebhook": "yes",
            "deviceWebhook": "yes",
            "statusInstanceWebhook": "yes",
            "pollMessageWebhook": "yes",
            "incomingBlockWebhook": "yes",
            "incomingCallWebhook": "yes",
            "outgoingCallWebhook": "yes",
            "editedMessageWebhook": "yes",
            "deletedMessageWebhook": "yes",
            "catalogWebhook": "yes",
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

    # ── V14 PART B — rich messaging (raw chatId; accepts @c.us / @g.us) ────────
    def _as_chat_id(self, chat: str) -> str:
        """Pass through a full chatId (…@c.us / …@g.us); normalize a bare phone."""
        return chat if "@" in str(chat) else self._chat_id(chat)

    async def send_interactive_buttons_rich(self, chat: str, header: str, body: str,
                                            footer: str, buttons: list[dict]) -> Optional[str]:
        """FEATURE 7 — correct Green API shape: buttons carry type/buttonId/buttonText
        (+ copyCode/phoneNumber/url per type). Rate limit 1/sec (enforce upstream)."""
        r = await self._post("sendInteractiveButtons", {
            "chatId": self._as_chat_id(chat),
            "header": header or "",
            "body": body,
            "footer": footer or "",
            "buttons": buttons,
        })
        return r.get("idMessage")

    async def send_contact_card(self, chat: str, contact: dict) -> Optional[str]:
        """FEATURE 12 — sendContact. `contact` must include phoneContact (int)."""
        r = await self._post("sendContact", {
            "chatId": self._as_chat_id(chat),
            "contact": contact,
        })
        return r.get("idMessage")

    async def send_location_full(self, chat: str, name: str, address: str,
                                 latitude: float, longitude: float) -> Optional[str]:
        """FEATURE 13 — sendLocation with name + address."""
        r = await self._post("sendLocation", {
            "chatId": self._as_chat_id(chat),
            "nameLocation": name or "",
            "address": address or "",
            "latitude": latitude,
            "longitude": longitude,
        })
        return r.get("idMessage")

    async def forward_to(self, chat: str, chat_id_from: str, message_ids: list[str]) -> Optional[str]:
        """FEATURE 14 — forwardMessages to a raw destination chatId."""
        r = await self._post("forwardMessages", {
            "chatId": self._as_chat_id(chat),
            "chatIdFrom": chat_id_from,
            "messages": message_ids,
        })
        return r.get("idMessage")

    # ── V14 PART C — message control (raw chatId) ──────────────────────────────
    async def edit_message_raw(self, chat: str, message_id: str, new_text: str) -> dict:
        """FEATURE 9 — editMessage. ⚠️ Green API returns HTTP 200 even when the edit
        silently fails (>15 min / not API-sent); confirm via the editedMessage /
        outgoingMessageStatus webhooks. Returns the raw response."""
        return await self._post("editMessage", {
            "chatId": self._as_chat_id(chat),
            "idMessage": message_id,
            "message": new_text,
        })

    async def delete_message_raw(self, chat: str, message_id: str, only_sender: bool = False) -> dict:
        """FEATURE 10 — deleteMessage. only_sender=True deletes on our side only.
        ⚠️ HTTP 200 does not guarantee success; confirm via the deletedMessage webhook."""
        body = {"chatId": self._as_chat_id(chat), "idMessage": message_id}
        if only_sender:
            body["onlySenderDelete"] = True
        return await self._post("deleteMessage", body)

    async def read_chat(self, chat: str, message_id: str | None = None) -> dict:
        """FEATURE 21 — readChat (idMessage optional)."""
        body = {"chatId": self._as_chat_id(chat)}
        if message_id:
            body["idMessage"] = message_id
        return await self._post("readChat", body)

    # ── V14 PART D — chat & profile (raw chatId) ──────────────────────────────
    async def archive_chat_raw(self, chat: str) -> dict:
        """FEATURE 15 — archiveChat."""
        return await self._post("archiveChat", {"chatId": self._as_chat_id(chat)})

    async def unarchive_chat_raw(self, chat: str) -> dict:
        """FEATURE 15 — unarchiveChat."""
        return await self._post("unarchiveChat", {"chatId": self._as_chat_id(chat)})

    async def set_disappearing_raw(self, chat: str, ephemeral_expiration: int) -> dict:
        """FEATURE 16 — setDisappearingChat. ephemeralExpiration ∈ {0, 86400, 604800, 7776000}."""
        return await self._post("setDisappearingChat", {
            "chatId": self._as_chat_id(chat),
            "ephemeralExpiration": int(ephemeral_expiration),
        })

    async def set_profile_picture_upload(self, image_bytes: bytes, filename: str = "avatar.jpg") -> dict:
        """FEATURE 17 — setProfilePicture (multipart/form-data, field `file`).
        ⚠️ 0.1/sec (one call per 10 seconds). Returns {reason, urlAvatar, setProfilePicture}."""
        url = f"{self.base_url}/setProfilePicture/{self.api_token}"
        files = {"file": (filename, image_bytes)}
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(url, files=files)
            r.raise_for_status()
            return r.json()

    async def get_contact_info_raw(self, chat: str) -> dict:
        """FEATURE 18 — getContactInfo for a raw chatId or bare phone."""
        return await self._post("getContactInfo", {"chatId": self._as_chat_id(chat)})

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
        """Set disappearing messages timer for a chat.
        ephemeral: 0=off, 86400=24h, 604800=7days, 7776000=90days"""
        r = await self._post("setDisappearingChat", {
            "chatId": self._chat_id(phone),
            "ephemeral": ephemeral
        })
        return r.get("chatId") is not None or r.get("isSet", False)

    # ── QUEUE ────────────────────────────────────────────
    async def get_messages_count(self) -> int:
        """Number of messages currently in the outgoing send queue."""
        r = await self._get("getMessagesCount")
        return r.get("count", 0)

    # ── CONTACTS ─────────────────────────────────────────
    async def get_contacts_block(self) -> list[dict]:
        """Get list of contacts blocked by this WhatsApp account."""
        r = await self._get("getContactsBlock")
        return r if isinstance(r, list) else []

    async def add_contact(self, phone: str, first_name: str, last_name: str = "", company: str = "افراکالا") -> bool:
        """Add a contact to the WhatsApp phone book of this account.
        addContact can be slow on Green API, so use a longer 60s timeout."""
        r = await self._post("addContact", {
            "phoneContact": int(self._normalize(phone)),
            "firstName": first_name,
            "lastName": last_name,
            "company": company
        }, timeout=60)
        return r.get("saveContact", False) or "contactId" in r

    async def edit_contact(self, phone: str, first_name: str, last_name: str = "", company: str = "") -> bool:
        """Edit an existing contact in the phonebook."""
        r = await self._post("editContact", {
            "phoneContact": int(self._normalize(phone)),
            "firstName": first_name,
            "lastName": last_name,
            "company": company
        })
        return r.get("editContact", False)

    # ── PROXY ─────────────────────────────────────────────
    async def set_proxy(self, host: str, port: int, login: str = "", password: str = "") -> bool:
        """Set a SOCKS5 proxy for this WhatsApp instance (helps stability from Iran)."""
        proxy_url = f"socks5://{login}:{password}@{host}:{port}" if login else f"socks5://{host}:{port}"
        r = await self._post("setSettings", {"proxyUrl": proxy_url})
        return r.get("saveSettings", False)

    async def remove_proxy(self) -> bool:
        """Remove proxy settings."""
        r = await self._post("setSettings", {"proxyUrl": ""})
        return r.get("saveSettings", False)

    async def get_proxy(self) -> str | None:
        """Get current proxy URL from settings."""
        s = await self.get_settings()
        return s.get("proxyUrl") or None

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

    async def get_outgoing_statuses(self, minutes: int = 10080) -> list[dict]:
        """Statuses we posted (default: last 7 days). minutes goes AFTER the token."""
        r = await self._get("getOutgoingStatuses", params={"minutes": minutes})
        return r if isinstance(r, list) else []

    async def get_status_statistic(self, status_id: str) -> dict:
        """Who viewed a posted status."""
        r = await self._get("getStatusStatistic", params={"idMessage": status_id})
        return r if isinstance(r, dict) else {}

    async def join_group_via_link(self, invite_link: str) -> dict:
        """Best-effort join a group via invite link. Green API support for this is
        version/plan dependent (often unsupported → 404/403). Never raises."""
        try:
            r = await self._post("joinGroupViaLink", {"inviteLink": invite_link})
            return {"success": True, "response": r}
        except Exception as e:
            unsupported = any(c in str(e) for c in ("404", "403", "not found", "Not Found"))
            return {"success": False, "unsupported": unsupported, "error": str(e)[:200]}

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
