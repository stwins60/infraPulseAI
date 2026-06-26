from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel


class IncidentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    severity: str
    alert_ids: Optional[List[UUID]] = None


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    severity: Optional[str] = None
    resolution_summary: Optional[str] = None
    assigned_to_id: Optional[UUID] = None


class IncidentOut(BaseModel):
    id: UUID
    title: str
    severity: str
    status: str
    impact: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class IncidentDetailOut(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    severity: str
    status: str
    impact: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_summary: Optional[str] = None
    timeline: Optional[List[Dict[str, Any]]] = None
    tags: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
