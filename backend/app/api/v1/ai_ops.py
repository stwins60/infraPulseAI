from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.dependencies import require_org_role
from app.core.exceptions import NotFoundError, ValidationError
from app.models.alert import Alert
from app.models.incident import Incident
from app.models.server import Server
from app.models.ai_analysis import AIAnalysis
from app.schemas.ai_analysis import AIAnalysisRequest, AIAnalysisOut
from app.services.ai.orchestrator import AIOrchestrator

router = APIRouter()


@router.post("/analyze-alert/{alert_id}", response_model=AIAnalysisOut, status_code=201)
async def analyze_alert(
    alert_id: UUID,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, current_user = org_context
    alert = await db.get(Alert, alert_id)
    if not alert or alert.organization_id != org.id:
        raise NotFoundError("Alert")

    orchestrator = AIOrchestrator(org, db)
    analysis = await orchestrator.analyze_alert(alert, requested_by_id=current_user.id)
    return analysis


@router.post("/analyze-server/{server_id}", response_model=AIAnalysisOut, status_code=201)
async def analyze_server(
    server_id: UUID,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, current_user = org_context
    server = await db.get(Server, server_id)
    if not server or server.organization_id != org.id:
        raise NotFoundError("Server")

    orchestrator = AIOrchestrator(org, db)
    analysis = await orchestrator.analyze_server(server, requested_by_id=current_user.id)
    return analysis


@router.post("/analyze-incident/{incident_id}", response_model=AIAnalysisOut, status_code=201)
async def analyze_incident(
    incident_id: UUID,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, current_user = org_context
    incident = await db.get(Incident, incident_id)
    if not incident or incident.organization_id != org.id:
        raise NotFoundError("Incident")

    orchestrator = AIOrchestrator(org, db)
    analysis = await orchestrator.analyze_incident(incident, requested_by_id=current_user.id)
    return analysis


@router.get("/analyses", response_model=dict)
async def list_analyses(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    org, _, _ = org_context
    result = await db.execute(
        select(AIAnalysis)
        .where(AIAnalysis.organization_id == org.id)
        .order_by(AIAnalysis.created_at.desc())
        .offset(offset).limit(limit)
    )
    analyses = result.scalars().all()
    return {
        "analyses": [
            {
                "id": str(a.id),
                "analysis_type": a.analysis_type,
                "provider": a.provider,
                "model": a.model,
                "status": a.status,
                "alert_id": str(a.alert_id) if a.alert_id else None,
                "server_id": str(a.server_id) if a.server_id else None,
                "summary": a.result.get("summary", ""),
                "severity_assessment": a.result.get("severity_assessment", ""),
                "created_at": a.created_at.isoformat(),
            }
            for a in analyses
        ]
    }


@router.get("/analyses/{analysis_id}", response_model=AIAnalysisOut)
async def get_analysis(
    analysis_id: UUID,
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    analysis = await db.get(AIAnalysis, analysis_id)
    if not analysis or analysis.organization_id != org.id:
        raise NotFoundError("AI analysis")
    return analysis


@router.put("/config")
async def update_ai_config(
    config: dict,
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    from app.services.encryption_service import encrypt
    import json

    # Encrypt sensitive fields
    safe_config = {k: v for k, v in config.items() if "key" not in k.lower() and "secret" not in k.lower()}
    sensitive_config = {k: v for k, v in config.items() if "key" in k.lower() or "secret" in k.lower()}

    org.ai_provider_config = {
        **safe_config,
        "_encrypted_sensitive": encrypt(json.dumps(sensitive_config)) if sensitive_config else None,
    }
    await db.commit()
    return {"message": "AI configuration updated"}


@router.get("/config")
async def get_ai_config(
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    config = org.ai_provider_config or {}
    # Return config without sensitive values
    return {k: v for k, v in config.items() if not k.startswith("_")}
