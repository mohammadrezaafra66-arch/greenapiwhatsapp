from pydantic import BaseModel
from typing import Optional


class InboxOut(BaseModel):
    id: str
    instance_id: str
    sender_phone: str
    sender_name: Optional[str] = None
    text: Optional[str] = None
    category: Optional[str] = None
    is_group: bool = False
    is_read: bool = False
    auto_replied: bool = False
    received_at: str


class ReplyBody(BaseModel):
    message_id: str
    text: str
