import hashlib
import secrets
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.exceptions import UnauthorizedError, NotFoundError, ValidationError
from app.models.server import Server, ServerAgent, AgentRegistrationToken
from app.models.metric import Metric
from app.models.log_entry import LogEntry
from app.schemas.agent import (
    AgentRegisterRequest, AgentRegisterResponse,
    AgentHeartbeatRequest, AgentMetricsBatch,
    AgentLogsBatch,
)

router = APIRouter()


async def _get_agent_from_token(token: str, db: AsyncSession) -> ServerAgent:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    result = await db.execute(
        select(ServerAgent).where(
            ServerAgent.agent_token_hash == token_hash,
            ServerAgent.is_active == True,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise UnauthorizedError("Invalid agent token")
    return agent


@router.post("/register", response_model=AgentRegisterResponse, status_code=201)
async def register_agent(
    data: AgentRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Register a new agent using a one-time registration token."""
    # Validate registration token
    result = await db.execute(
        select(AgentRegistrationToken).where(
            AgentRegistrationToken.token == data.registration_token,
            AgentRegistrationToken.is_used == False,
        )
    )
    reg_token = result.scalar_one_or_none()
    if not reg_token:
        raise ValidationError("Invalid or already-used registration token")
    if reg_token.expires_at < datetime.now(timezone.utc):
        raise ValidationError("Registration token has expired")

    # Create or update server record
    server_result = await db.execute(
        select(Server).where(
            Server.organization_id == reg_token.organization_id,
            Server.hostname == data.hostname,
        )
    )
    server = server_result.scalar_one_or_none()
    if not server:
        server = Server(
            organization_id=reg_token.organization_id,
            hostname=data.hostname,
            display_name=data.hostname,
            environment=reg_token.environment,
            status="online",
        )
        db.add(server)
        await db.flush()

    # Update server metadata
    server.ip_addresses = data.ip_addresses
    server.os_type = data.os_type
    server.os_version = data.os_version
    server.kernel_version = data.kernel_version
    server.cpu_count = data.cpu_count
    server.cpu_model = data.cpu_model
    server.memory_total_bytes = data.memory_total_bytes
    server.status = "online"
    server.last_seen_at = datetime.now(timezone.utc)

    # Generate agent token
    agent_token_raw = f"ipa_at_{secrets.token_urlsafe(48)}"
    agent_token_hash = hashlib.sha256(agent_token_raw.encode()).hexdigest()

    # Create agent record
    if server.agent:
        server.agent.agent_token_hash = agent_token_hash
        server.agent.agent_version = data.agent_version
        server.agent.last_heartbeat_at = datetime.now(timezone.utc)
    else:
        agent = ServerAgent(
            server_id=server.id,
            organization_id=reg_token.organization_id,
            agent_token_hash=agent_token_hash,
            agent_version=data.agent_version,
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        db.add(agent)

    # Mark registration token as used
    reg_token.is_used = True
    reg_token.used_by_server_id = server.id

    await db.commit()
    await db.refresh(server)

    return AgentRegisterResponse(
        agent_token=agent_token_raw,
        server_id=str(server.id),
        organization_id=str(reg_token.organization_id),
        heartbeat_interval_seconds=60,
        message="Agent registered successfully",
    )


@router.post("/heartbeat")
async def agent_heartbeat(
    data: AgentHeartbeatRequest,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_agent_from_token(x_agent_token, db)
    agent.last_heartbeat_at = datetime.now(timezone.utc)
    if data.agent_version:
        agent.agent_version = data.agent_version

    server = await db.get(Server, agent.server_id)
    if server:
        server.status = "online"
        server.last_seen_at = datetime.now(timezone.utc)
        if data.ip_addresses:
            server.ip_addresses = data.ip_addresses

    await db.commit()
    return {"status": "ok", "server_id": str(agent.server_id)}


@router.post("/metrics")
async def ingest_metrics(
    data: AgentMetricsBatch,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_agent_from_token(x_agent_token, db)
    server = await db.get(Server, agent.server_id)
    if not server:
        raise NotFoundError("Server")

    metrics = []
    for m in data.metrics:
        metric = Metric(
            organization_id=server.organization_id,
            server_id=server.id,
            source_type="agent",
            metric_name=m.name,
            value=m.value,
            unit=m.unit,
            labels=m.labels or {},
            timestamp=m.timestamp or datetime.now(timezone.utc),
        )
        metrics.append(metric)

    db.add_all(metrics)

    # Update server status
    server.status = "online"
    server.last_seen_at = datetime.now(timezone.utc)

    # Extract health indicators from metrics
    health_score = 100
    for m in data.metrics:
        if m.name == "cpu_percent" and m.value > 90:
            health_score -= 20
        elif m.name == "memory_percent" and m.value > 90:
            health_score -= 20
        elif m.name == "disk_percent" and m.value > 90:
            health_score -= 20

    server.health_score = max(0, health_score)

    await db.commit()
    return {"status": "ok", "ingested": len(metrics)}


@router.post("/logs")
async def ingest_logs(
    data: AgentLogsBatch,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_agent_from_token(x_agent_token, db)
    server = await db.get(Server, agent.server_id)
    if not server:
        raise NotFoundError("Server")

    log_entries = []
    for entry in data.logs:
        log = LogEntry(
            organization_id=server.organization_id,
            server_id=server.id,
            severity=entry.severity,
            source=entry.source,
            service=entry.service,
            application=entry.application,
            message=entry.message,
            raw_log=entry.raw_log,
            log_metadata=entry.metadata or {},
            timestamp=entry.timestamp or datetime.now(timezone.utc),
        )
        log_entries.append(log)

    db.add_all(log_entries)
    await db.commit()
    return {"status": "ok", "ingested": len(log_entries)}


@router.get("/config")
async def get_agent_config(
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_agent_from_token(x_agent_token, db)
    return {
        "heartbeat_interval_seconds": agent.heartbeat_interval_seconds,
        "metrics_interval_seconds": 30,
        "logs_batch_size": 100,
        "logs_batch_interval_seconds": 10,
        "config": agent.config or {},
    }
