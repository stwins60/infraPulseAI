from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel


class MetricOut(BaseModel):
    id: UUID
    server_id: Optional[UUID] = None
    metric_name: str
    value: float
    unit: Optional[str] = None
    timestamp: datetime
    model_config = {"from_attributes": True}


class MetricDataPoint(BaseModel):
    timestamp: str
    value: float


class MetricSeries(BaseModel):
    name: str
    data: List[MetricDataPoint]


class MetricQuery(BaseModel):
    metric_names: List[str]
    time_range: str = "1h"
    server_id: Optional[UUID] = None
