from pydantic import BaseModel, Field
from typing import Optional


class ContactCreate(BaseModel):
    phone: str = Field(..., max_length=20)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    source: Optional[str] = None


class ContactOut(BaseModel):
    id: str
    phone: str
    name: str
    has_whatsapp: Optional[bool] = None
    province: Optional[str] = None


class BlacklistCreate(BaseModel):
    phone: str = Field(..., max_length=20)
    reason: Optional[str] = None
