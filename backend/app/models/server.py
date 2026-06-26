import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Integer, BigInteger, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from app.models.base import Base, TimestampMixin, UUIDMixin


class Server(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "servers"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ip_addresses: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    os_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    os_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    kernel_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cpu_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cpu_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    memory_total_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    environment: Mapped[str] = mapped_column(String(50), default="production")
    status: Mapped[str] = mapped_column(String(50), default="offline", index=True)
    health_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    owner_team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="servers")
    agent: Mapped[Optional["ServerAgent"]] = relationship("ServerAgent", back_populates="server", uselist=False, cascade="all, delete-orphan")
    metrics: Mapped[List["Metric"]] = relationship("Metric", back_populates="server", cascade="all, delete-orphan")
    log_entries: Mapped[List["LogEntry"]] = relationship("LogEntry", back_populates="server", cascade="all, delete-orphan")
    alerts: Mapped[List["Alert"]] = relationship("Alert", back_populates="server")


class ServerAgent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "server_agents"

    server_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), unique=True, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    agent_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    server: Mapped["Server"] = relationship("Server", back_populates="agent")
    organization: Mapped["Organization"] = relationship("Organization")


class AgentRegistrationToken(Base, UUIDMixin):
    __tablename__ = "agent_registration_tokens"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    environment: Mapped[str] = mapped_column(String(50), default="production")
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_by_server_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization: Mapped["Organization"] = relationship("Organization")
    created_by: Mapped["User"] = relationship("User")


from app.models.organization import Organization  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401
from app.models.metric import Metric  # noqa: E402, F401
from app.models.log_entry import LogEntry  # noqa: E402, F401
from app.models.alert import Alert  # noqa: E402, F401
