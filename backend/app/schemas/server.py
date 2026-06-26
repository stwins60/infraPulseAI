from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel


class ServerOut(BaseModel):
    id: UUID
    organization_id: UUID
    hostname: str
    display_name: Optional[str] = None
    ip_addresses: Optional[List[str]] = None
    os_type: Optional[str] = None
    os_version: Optional[str] = None
    environment: str
    status: str
    health_score: Optional[int] = None
    tags: Optional[List[str]] = None
    region: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class ServerDetailOut(BaseModel):
    id: UUID
    organization_id: UUID
    hostname: str
    display_name: Optional[str] = None
    ip_addresses: Optional[List[str]] = None
    os_type: Optional[str] = None
    os_version: Optional[str] = None
    kernel_version: Optional[str] = None
    cpu_count: Optional[int] = None
    cpu_model: Optional[str] = None
    memory_total_bytes: Optional[int] = None
    environment: str
    status: str
    health_score: Optional[int] = None
    tags: Optional[List[str]] = None
    region: Optional[str] = None
    owner_team: Optional[str] = None
    notes: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    open_alerts: int = 0
    created_at: datetime
    model_config = {"from_attributes": True}


class ServerUpdate(BaseModel):
    display_name: Optional[str] = None
    environment: Optional[str] = None
    tags: Optional[List[str]] = None
    region: Optional[str] = None
    owner_team: Optional[str] = None
    notes: Optional[str] = None


class AgentRegistrationTokenCreate(BaseModel):
    label: Optional[str] = None
    environment: str = "production"


class AgentRegistrationTokenOut(BaseModel):
    id: UUID
    label: Optional[str] = None
    environment: str
    is_used: bool
    expires_at: datetime
    created_at: datetime
    model_config = {"from_attributes": True}


class AgentTokenOut(BaseModel):
    id: str
    token: str
    label: Optional[str] = None
    environment: str
    expires_at: datetime
    created_at: datetime
    install_command: str
