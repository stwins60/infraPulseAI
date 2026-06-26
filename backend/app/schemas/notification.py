from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel


class NotificationChannelCreate(BaseModel):
    name: str
    channel_type: str  # slack, email, webhook, teams
    config: Dict[str, Any] = {}
    is_active: bool = True


class NotificationChannelOut(BaseModel):
    id: UUID
    name: str
    channel_type: str
    config: Optional[Dict[str, Any]] = None
    is_active: bool
    last_tested_at: Optional[datetime] = None
    last_test_success: Optional[bool] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class NotificationPolicyCreate(BaseModel):
    name: str
    is_active: bool = True
    rules: List[Dict[str, Any]] = []


class NotificationPolicyOut(BaseModel):
    id: UUID
    name: str
    is_active: bool
    rules: List[Dict[str, Any]]
    created_at: datetime
    model_config = {"from_attributes": True}
