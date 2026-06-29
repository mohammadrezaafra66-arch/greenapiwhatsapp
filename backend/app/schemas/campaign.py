from pydantic import BaseModel, Field
from typing import Optional


class CampaignCreate(BaseModel):
    name: str = Field(..., max_length=200)
    use_gpt: bool = True
    gpt_prompt: Optional[str] = None
    message_template: Optional[str] = None
    include_products: bool = False
    product_count: int = 3
    send_image: bool = False
    image_url: Optional[str] = None


class CampaignOut(BaseModel):
    id: str
    name: str
    status: str
    total_contacts: int
    sent_count: int
    failed_count: int
    created_at: str


class CampaignProgress(BaseModel):
    campaign_id: str
    name: str
    status: str
    total: int
    sent: int
    failed: int
    pending: int
    progress_pct: float
