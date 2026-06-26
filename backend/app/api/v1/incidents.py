from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.dependencies import require_org_role
from app.core.exceptions import NotFoundError
from app.models.incident import Incident
from app.models.alert import Alert
from app.schemas.incident import IncidentCreate, IncidentOut, IncidentUpdate, IncidentDetailOut

router = APIRouter()


@router.get("", response_model=List[IncidentOut])
async def list_incidents(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    org, _, _ = org_context
    query = select(Incident).where(Incident.organization_id == org.id)
    if status:
        query = query.where(Incident.status == status)
    if severity:
        query = query.where(Incident.severity == severity)
    query = query.order_by(Incident.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=IncidentOut, status_code=201)
async def create_incident(
    data: IncidentCreate,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, current_user = org_context
    incident = Incident(
        organization_id=org.id,
        title=data.title,
        description=data.description,
        severity=data.severity,
        status="open",
        created_by_id=current_user.id,
        timeline=[{"time": datetime.now(timezone.utc).isoformat(), "event": "Incident created", "user": str(current_user.id)}],
    )
    db.add(incident)
    await db.flush()

    # Link alerts
    if data.alert_ids:
        for alert_id in data.alert_ids:
            alert = await db.get(Alert, alert_id)
            if alert and alert.organization_id == org.id:
                incident.alerts.append(alert)

    await db.commit()
    await db.refresh(incident)
    return incident


@router.get("/{incident_id}", response_model=IncidentDetailOut)
async def get_incident(
    incident_id: UUID,
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    incident = await db.get(Incident, incident_id)
    if not incident or incident.organization_id != org.id:
        raise NotFoundError("Incident")
    return incident


@router.put("/{incident_id}", response_model=IncidentOut)
async def update_incident(
    incident_id: UUID,
    data: IncidentUpdate,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, current_user = org_context
    incident = await db.get(Incident, incident_id)
    if not incident or incident.organization_id != org.id:
        raise NotFoundError("Incident")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(incident, field, value)

    if data.status == "resolved" and not incident.resolved_at:
        incident.resolved_at = datetime.now(timezone.utc)
        timeline = incident.timeline or []
        timeline.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "event": "Incident resolved",
            "user": str(current_user.id),
        })
        incident.timeline = timeline

    await db.commit()
    await db.refresh(incident)
    return incident


@router.post("/{incident_id}/alerts/{alert_id}")
async def link_alert_to_incident(
    incident_id: UUID,
    alert_id: UUID,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    incident = await db.get(Incident, incident_id)
    if not incident or incident.organization_id != org.id:
        raise NotFoundError("Incident")
    alert = await db.get(Alert, alert_id)
    if not alert or alert.organization_id != org.id:
        raise NotFoundError("Alert")
    incident.alerts.append(alert)
    await db.commit()
    return {"message": "Alert linked to incident"}
