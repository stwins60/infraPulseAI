import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base, TimestampMixin, UUIDMixin


class AIAnalysis(Base, UUIDMixin):
    __tablename__ = "ai_analyses"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True, index=True)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True)
    server_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("servers.id", ondelete="SET NULL"), nullable=True)
    analysis_type: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_used: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(50), default="completed")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="ai_analyses")
    alert: Mapped[Optional["Alert"]] = relationship("Alert", back_populates="ai_analyses")
    incident: Mapped[Optional["Incident"]] = relationship("Incident", back_populates="ai_analyses")
    server: Mapped[Optional["Server"]] = relationship("Server")
    requested_by: Mapped[Optional["User"]] = relationship("User")


from app.models.organization import Organization  # noqa: E402, F401
from app.models.alert import Alert  # noqa: E402, F401
from app.models.incident import Incident  # noqa: E402, F401
from app.models.server import Server  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401
