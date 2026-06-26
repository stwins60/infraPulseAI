from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel


class LogEntryOut(BaseModel):
    id: UUID
    server_id: Optional[UUID] = None
    severity: str
    source: Optional[str] = None
    service: Optional[str] = None
    application: Optional[str] = None
    message: str
    timestamp: datetime
    model_config = {"from_attributes": True}


class LogSearchParams(BaseModel):
    q: Optional[str] = None
    server_id: Optional[UUID] = None
    severity: Optional[str] = None
    source: Optional[str] = None
    service: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = 100
    offset: int = 0


class SavedSearchCreate(BaseModel):
    name: str
    query_params: Dict[str, Any]
    is_shared: bool = False


class SavedSearchOut(BaseModel):
    id: UUID
    name: str
    query_params: Dict[str, Any]
    is_shared: bool
    created_at: datetime
    model_config = {"from_attributes": True}
