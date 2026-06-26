from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel


class AgentRegisterRequest(BaseModel):
    registration_token: str
    hostname: str
    ip_addresses: Optional[List[str]] = None
    os_type: Optional[str] = None
    os_version: Optional[str] = None
    kernel_version: Optional[str] = None
    cpu_count: Optional[int] = None
    cpu_model: Optional[str] = None
    memory_total_bytes: Optional[int] = None
    agent_version: Optional[str] = None


class AgentRegisterResponse(BaseModel):
    agent_token: str
    server_id: str
    organization_id: str
    heartbeat_interval_seconds: int
    message: str


class AgentHeartbeatRequest(BaseModel):
    agent_version: Optional[str] = None
    ip_addresses: Optional[List[str]] = None


class MetricDataPoint(BaseModel):
    name: str
    value: float
    unit: Optional[str] = None
    labels: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None


class AgentMetricsBatch(BaseModel):
    metrics: List[MetricDataPoint]


class LogDataPoint(BaseModel):
    message: str
    severity: str = "info"
    source: Optional[str] = None
    service: Optional[str] = None
    application: Optional[str] = None
    raw_log: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None


class AgentLogsBatch(BaseModel):
    logs: List[LogDataPoint]
