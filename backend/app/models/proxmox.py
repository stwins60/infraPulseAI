import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Integer, BigInteger, Float, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from app.models.base import Base, TimestampMixin, UUIDMixin


class ProxmoxConnection(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "proxmox_connections"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=8006)
    token_id: Mapped[str] = mapped_column(String(255), nullable=False)
    token_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    cluster_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    environment: Mapped[str] = mapped_column(String(50), default="production")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    connection_status: Mapped[str] = mapped_column(String(50), default="unknown")
    last_connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    node_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    vm_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    container_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="proxmox_connections")
    nodes: Mapped[List["ProxmoxNode"]] = relationship("ProxmoxNode", back_populates="connection", cascade="all, delete-orphan")
    vms: Mapped[List["ProxmoxVM"]] = relationship("ProxmoxVM", back_populates="connection", cascade="all, delete-orphan")


class ProxmoxNode(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "proxmox_nodes"

    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("proxmox_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    node_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="unknown")
    uptime: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    cpu_usage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_used: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    memory_total: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    disk_used: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    disk_total: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    cpu_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pve_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    connection: Mapped["ProxmoxConnection"] = relationship("ProxmoxConnection", back_populates="nodes")
    organization: Mapped["Organization"] = relationship("Organization")
    vms: Mapped[List["ProxmoxVM"]] = relationship("ProxmoxVM", back_populates="node")


class ProxmoxVM(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "proxmox_vms"

    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("proxmox_connections.id", ondelete="CASCADE"), nullable=False)
    node_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("proxmox_nodes.id", ondelete="SET NULL"), nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    vmid: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vm_type: Mapped[str] = mapped_column(String(20), default="qemu")  # qemu or lxc
    status: Mapped[str] = mapped_column(String(50), default="unknown")
    uptime: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    cpu_usage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_used: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    memory_total: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    disk_used: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    disk_total: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    network_in: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    network_out: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    node_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    os_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    template: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    connection: Mapped["ProxmoxConnection"] = relationship("ProxmoxConnection", back_populates="vms")
    node: Mapped[Optional["ProxmoxNode"]] = relationship("ProxmoxNode", back_populates="vms")
    organization: Mapped["Organization"] = relationship("Organization")


from app.models.organization import Organization  # noqa: E402, F401
