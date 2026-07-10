import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class GroupJoinLink(Base):
    __tablename__ = "group_join_links"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(String(300))
    invite_link: Mapped[str] = mapped_column(Text, nullable=False)
    link_type: Mapped[str] = mapped_column(String(20), default="group")  # group | community | broadcast
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AccountJoinStatus(Base):
    __tablename__ = "account_join_status"
    __table_args__ = (UniqueConstraint("account_id", "link_id", name="uq_account_link"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"))
    link_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("group_join_links.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending|joined|unsupported|error
    joined_at: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(Text)
