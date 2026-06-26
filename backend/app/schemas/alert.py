from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel


class AlertRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    rule_type: str
    severity: str = "medium"
    condition: Dict[str, Any]
    threshold_value: Optional[float] = None
    threshold_operator: Optional[str] = None
    duration_seconds: Optional[int] = None
    scope: str = "all"
    is_active: bool = True
    cooldown_minutes: int = 15
    auto_resolve: bool = True
    ai_analysis_enabled: bool = False


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    condition: Optional[Dict[str, Any]] = None
    threshold_value: Optional[float] = None
    is_active: Optional[bool] = None
    cooldown_minutes: Optional[int] = None
    ai_analysis_enabled: Optional[bool] = None


class AlertRuleOut(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    rule_type: str
    severity: str
    condition: Dict[str, Any]
    threshold_value: Optional[float] = None
    threshold_operator: Optional[str] = None
    is_active: bool
    cooldown_minutes: int
    ai_analysis_enabled: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class AlertOut(BaseModel):
    id: UUID
    title: str
    severity: str
    status: str
    source_type: str
    server_id: Optional[UUID] = None
    rule_type: Optional[str] = None
    trigger_value: Optional[float] = None
    created_at: datetime
    ai_analyzed: bool
    model_config = {"from_attributes": True}


class AlertDetailOut(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    severity: str
    status: str
    source_type: str
    rule_type: Optional[str] = None
    server_id: Optional[UUID] = None
    trigger_value: Optional[float] = None
    threshold_value: Optional[float] = None
    trigger_data: Optional[Dict[str, Any]] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    notification_sent: bool
    ai_analyzed: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class AlertUpdate(BaseModel):
    status: str
    resolution_notes: Optional[str] = None
