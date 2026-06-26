import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.core.dependencies import get_current_user, require_org_role
from app.core.exceptions import NotFoundError, ConflictError, PlanLimitError
from app.core.security import hash_token
from app.models.server import Server, ServerAgent, AgentRegistrationToken
from app.models.metric import Metric
from app.models.alert import Alert
from app.models.ai_analysis import AIAnalysis
from app.schemas.server import (
    ServerOut, ServerUpdate, ServerDetailOut,
    AgentRegistrationTokenCreate, AgentRegistrationTokenOut,
    AgentTokenOut,
)

router = APIRouter()


@router.get("", response_model=List[ServerOut])
async def list_servers(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    environment: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    org, _, _ = org_context
    query = select(Server).where(Server.organization_id == org.id, Server.is_active == True)

    if status:
        query = query.where(Server.status == status)
    if environment:
        query = query.where(Server.environment == environment)
    if search:
        query = query.where(Server.hostname.ilike(f"%{search}%") | Server.display_name.ilike(f"%{search}%"))

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{server_id}", response_model=ServerDetailOut)
async def get_server(
    server_id: UUID,
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    server = await db.get(Server, server_id)
    if not server or server.organization_id != org.id:
        raise NotFoundError("Server")

    # Fetch recent alerts count
    alert_count_result = await db.execute(
        select(func.count(Alert.id)).where(
            Alert.server_id == server_id,
            Alert.status == "open",
        )
    )
    open_alerts = alert_count_result.scalar() or 0

    return {**server.__dict__, "open_alerts": open_alerts}


@router.put("/{server_id}", response_model=ServerOut)
async def update_server(
    server_id: UUID,
    data: ServerUpdate,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    server = await db.get(Server, server_id)
    if not server or server.organization_id != org.id:
        raise NotFoundError("Server")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(server, field, value)
    await db.commit()
    await db.refresh(server)
    return server


@router.delete("/{server_id}")
async def delete_server(
    server_id: UUID,
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    server = await db.get(Server, server_id)
    if not server or server.organization_id != org.id:
        raise NotFoundError("Server")
    server.is_active = False
    await db.commit()
    return {"message": "Server deleted"}


# ── Agent Registration Tokens ─────────────────────────────────────────────────
@router.post("/agent-tokens", response_model=AgentTokenOut, status_code=201)
async def create_agent_registration_token(
    data: AgentRegistrationTokenCreate,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, current_user = org_context

    raw_token = f"ipa_agent_{secrets.token_urlsafe(32)}"
    token = AgentRegistrationToken(
        organization_id=org.id,
        token=raw_token,
        label=data.label,
        environment=data.environment,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        created_by_id=current_user.id,
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)

    return AgentTokenOut(
        id=str(token.id),
        token=raw_token,
        label=token.label,
        environment=token.environment,
        expires_at=token.expires_at,
        created_at=token.created_at,
        install_command=f'curl -fsSL http://your-domain.com/install-agent.sh | sudo bash -s -- --token {raw_token}',
    )


@router.get("/agent-tokens", response_model=List[AgentRegistrationTokenOut])
async def list_agent_tokens(
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    result = await db.execute(
        select(AgentRegistrationToken).where(
            AgentRegistrationToken.organization_id == org.id,
        ).order_by(AgentRegistrationToken.created_at.desc())
    )
    return result.scalars().all()
