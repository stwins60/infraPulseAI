from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel


class ProxmoxConnectionCreate(BaseModel):
    name: str
    hostname: str
    port: int = 8006
    token_id: str
    token_secret: str
    verify_ssl: bool = True
    cluster_label: Optional[str] = None
    environment: str = "production"


class ProxmoxConnectionUpdate(BaseModel):
    name: Optional[str] = None
    hostname: Optional[str] = None
    port: Optional[int] = None
    token_id: Optional[str] = None
    token_secret: Optional[str] = None
    verify_ssl: Optional[bool] = None
    cluster_label: Optional[str] = None
    environment: Optional[str] = None
    is_active: Optional[bool] = None


class ProxmoxConnectionOut(BaseModel):
    id: UUID
    name: str
    hostname: str
    port: int
    token_id: str
    verify_ssl: bool
    cluster_label: Optional[str] = None
    environment: str
    is_active: bool
    connection_status: str
    last_connected_at: Optional[datetime] = None
    node_count: Optional[int] = None
    vm_count: Optional[int] = None
    container_count: Optional[int] = None
    version: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class ProxmoxNodeOut(BaseModel):
    id: UUID
    node_name: str
    status: str
    uptime: Optional[int] = None
    cpu_usage: Optional[float] = None
    memory_used: Optional[int] = None
    memory_total: Optional[int] = None
    disk_used: Optional[int] = None
    disk_total: Optional[int] = None
    cpu_count: Optional[int] = None
    pve_version: Optional[str] = None
    ip_address: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class ProxmoxVMOut(BaseModel):
    id: UUID
    vmid: int
    name: Optional[str] = None
    vm_type: str
    status: str
    uptime: Optional[int] = None
    cpu_usage: Optional[float] = None
    memory_used: Optional[int] = None
    memory_total: Optional[int] = None
    disk_used: Optional[int] = None
    node_name: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    model_config = {"from_attributes": True}
