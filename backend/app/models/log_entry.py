import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base, UUIDMixin


class LogEntry(Base, UUIDMixin):
    __tablename__ = "log_entries"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    server_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info", index=True)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    service: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    application: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    log_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization: Mapped["Organization"] = relationship("Organization")
    server: Mapped[Optional["Server"]] = relationship("Server", back_populates="log_entries")


class SavedSearch(Base, UUIDMixin):
    __tablename__ = "saved_searches"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    query_params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_shared: Mapped[bool] = mapped_column(bool, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization: Mapped["Organization"] = relationship("Organization")
    user: Mapped["User"] = relationship("User")


from app.models.organization import Organization  # noqa: E402, F401
from app.models.server import Server  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401
