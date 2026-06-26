from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, EmailStr


class SubscriptionPlanOut(BaseModel):
    id: UUID
    name: str
    display_name: str
    max_servers: int
    max_users: int
    max_proxmox_connections: int
    ai_analysis_enabled: bool
    advanced_alerting: bool
    price_monthly: Optional[float] = None
    model_config = {"from_attributes": True}


class OrganizationOut(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool
    onboarding_completed: bool
    onboarding_step: int
    timezone: str
    contact_email: Optional[str] = None
    logo_url: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    timezone: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    logo_url: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class MembershipOut(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: UUID
    role: str
    is_active: bool
    accepted_at: Optional[datetime] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class MembershipUpdate(BaseModel):
    role: str


class InviteUserRequest(BaseModel):
    email: EmailStr
    role: str = "viewer"
