"""
Green API client for WhatsApp messaging.
Docs: https://green-api.com/en/docs/
"""
import httpx
import asyncio
from typing import Optional
from app.config import settings


class GreenAPIClient:
    def __init__(self, instance_id: str, api_token: str):
        self.instance_id = instance_id
        self.api_token = api_token
        self.base_url = f"https://api.green-api.com/waInstance{instance_id}"

    async def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        url = f"{self.base_url}/{endpoint}/{self.api_token}"
        async with httpx.AsyncClient(timeout=30) as client:
            if method == "GET":
                resp = await client.get(url)
            else:
                resp = await client.post(url, json=data)
            resp.raise_for_status()
            return resp.json()

    async def get_state(self) -> str:
        """Returns: authorized, notAuthorized, blocked, sleepMode, starting"""
        result = await self._request("GET", "getStateInstance")
        return result.get("stateInstance", "unknown")

    async def check_whatsapp(self, phone: str) -> bool:
        """Check if phone number has WhatsApp."""
        phone = self._normalize_phone(phone)
        result = await self._request("POST", "checkWhatsapp", {"phoneNumber": int(phone)})
        return result.get("existsWhatsapp", False)

    async def send_message(self, phone: str, message: str) -> Optional[str]:
        """Send text message. Returns message ID or None."""
        phone = self._normalize_phone(phone)
        chat_id = f"{phone}@c.us"
        result = await self._request("POST", "sendMessage", {
            "chatId": chat_id,
            "message": message
        })
        return result.get("idMessage")

    async def send_image(self, phone: str, image_url: str, caption: str = "") -> Optional[str]:
        """Send image with optional caption."""
        phone = self._normalize_phone(phone)
        chat_id = f"{phone}@c.us"
        result = await self._request("POST", "sendFileByUrl", {
            "chatId": chat_id,
            "urlFile": image_url,
            "fileName": "image.jpg",
            "caption": caption
        })
        return result.get("idMessage")

    async def set_webhook(self, webhook_url: str) -> bool:
        """Configure webhook URL for incoming messages."""
        result = await self._request("POST", "setSettings", {
            "webhookUrl": webhook_url,
            "outgoingWebhook": "yes",
            "incomingWebhook": "yes",
            "stateWebhook": "yes"
        })
        return result.get("saveSettings", False)

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Convert any Iranian phone format to 98xxxxxxxxxx."""
        phone = str(phone).strip().replace("+", "").replace("-", "").replace(" ", "")
        if phone.startswith("0") and len(phone) == 11:
            phone = "98" + phone[1:]
        elif not phone.startswith("98") and len(phone) == 10:
            phone = "98" + phone
        return phone
