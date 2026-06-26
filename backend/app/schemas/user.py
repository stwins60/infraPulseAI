from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool
    is_verified: bool
    is_platform_admin: bool
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    last_login_at: Optional[datetime] = None
    mfa_enabled: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    preferences: Optional[dict] = None
