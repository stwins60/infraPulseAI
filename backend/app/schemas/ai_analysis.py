from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel


class AIAnalysisRequest(BaseModel):
    analysis_type: str = "alert_analysis"
    context: Optional[Dict[str, Any]] = None


class AIAnalysisOut(BaseModel):
    id: UUID
    analysis_type: str
    provider: str
    model: str
    status: str
    result: Dict[str, Any]
    alert_id: Optional[UUID] = None
    incident_id: Optional[UUID] = None
    server_id: Optional[UUID] = None
    created_at: datetime
    model_config = {"from_attributes": True}
