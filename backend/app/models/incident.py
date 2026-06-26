import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, func, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from app.models.base import Base, TimestampMixin, UUIDMixin

incident_alerts = Table(
    "incident_alerts",
    Base.metadata,
    Column("incident_id", UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True),
    Column("alert_id", UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True),
)


class Incident(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "incidents"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="open", index=True)
    impact: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    assigned_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timeline: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="incidents")
    assigned_to: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_to_id])
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])
    alerts: Mapped[List["Alert"]] = relationship("Alert", secondary=incident_alerts)
    ai_analyses: Mapped[List["AIAnalysis"]] = relationship("AIAnalysis", back_populates="incident")


from app.models.organization import Organization  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401
from app.models.alert import Alert  # noqa: E402, F401
from app.models.ai_analysis import AIAnalysis  # noqa: E402, F401
