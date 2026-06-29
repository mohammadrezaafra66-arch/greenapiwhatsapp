from pydantic import BaseModel, Field
from typing import Optional


class AccountCreate(BaseModel):
    name: str = Field(..., max_length=100)
    instance_id: str = Field(..., max_length=50)
    api_token: str = Field(..., max_length=200)
    phone: Optional[str] = None


class AccountOut(BaseModel):
    id: str
    name: str
    instance_id: str
    phone: Optional[str] = None
    status: str
    sent_today: int
    daily_limit: int
    days_active: int
