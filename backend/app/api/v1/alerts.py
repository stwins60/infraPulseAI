from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.core.dependencies import require_org_role
from app.core.exceptions import NotFoundError, ForbiddenError
from app.models.alert import Alert, AlertRule
from app.models.server import Server
from app.schemas.alert import (
    AlertOut, AlertDetailOut, AlertUpdate, AlertRuleCreate, AlertRuleOut, AlertRuleUpdate
)

router = APIRouter()


# ── Alert Rules ───────────────────────────────────────────────────────────────
@router.get("/rules", response_model=List[AlertRuleOut])
async def list_alert_rules(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    result = await db.execute(
        select(AlertRule).where(AlertRule.organization_id == org.id).order_by(AlertRule.created_at.desc())
    )
    return result.scalars().all()


@router.post("/rules", response_model=AlertRuleOut, status_code=201)
async def create_alert_rule(
    data: AlertRuleCreate,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, current_user = org_context
    rule = AlertRule(
        organization_id=org.id,
        name=data.name,
        description=data.description,
        rule_type=data.rule_type,
        severity=data.severity,
        condition=data.condition,
        threshold_value=data.threshold_value,
        threshold_operator=data.threshold_operator,
        duration_seconds=data.duration_seconds,
        scope=data.scope,
        is_active=data.is_active,
        cooldown_minutes=data.cooldown_minutes,
        auto_resolve=data.auto_resolve,
        ai_analysis_enabled=data.ai_analysis_enabled,
        created_by_id=current_user.id,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.put("/rules/{rule_id}", response_model=AlertRuleOut)
async def update_alert_rule(
    rule_id: UUID,
    data: AlertRuleUpdate,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    rule = await db.get(AlertRule, rule_id)
    if not rule or rule.organization_id != org.id:
        raise NotFoundError("Alert rule")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(
    rule_id: UUID,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    rule = await db.get(AlertRule, rule_id)
    if not rule or rule.organization_id != org.id:
        raise NotFoundError("Alert rule")
    await db.delete(rule)
    await db.commit()
    return {"message": "Alert rule deleted"}


# ── Alerts ────────────────────────────────────────────────────────────────────
@router.get("", response_model=dict)
async def list_alerts(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    server_id: Optional[UUID] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    org, _, _ = org_context
    query = select(Alert).where(Alert.organization_id == org.id)
    if status:
        query = query.where(Alert.status == status)
    if severity:
        query = query.where(Alert.severity == severity)
    if server_id:
        query = query.where(Alert.server_id == server_id)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(Alert.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    alerts = result.scalars().all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "alerts": [
            {
                "id": str(a.id),
                "title": a.title,
                "severity": a.severity,
                "status": a.status,
                "source_type": a.source_type,
                "server_id": str(a.server_id) if a.server_id else None,
                "rule_type": a.rule_type,
                "trigger_value": a.trigger_value,
                "created_at": a.created_at.isoformat(),
                "ai_analyzed": a.ai_analyzed,
            }
            for a in alerts
        ],
    }


@router.get("/{alert_id}", response_model=AlertDetailOut)
async def get_alert(
    alert_id: UUID,
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    alert = await db.get(Alert, alert_id)
    if not alert or alert.organization_id != org.id:
        raise NotFoundError("Alert")
    return alert


@router.put("/{alert_id}/status")
async def update_alert_status(
    alert_id: UUID,
    data: AlertUpdate,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, current_user = org_context
    alert = await db.get(Alert, alert_id)
    if not alert or alert.organization_id != org.id:
        raise NotFoundError("Alert")

    now = datetime.now(timezone.utc)
    if data.status == "acknowledged" and alert.status == "open":
        alert.acknowledged_at = now
        alert.acknowledged_by_id = current_user.id
    elif data.status == "resolved":
        alert.resolved_at = now
        alert.resolved_by_id = current_user.id
        if data.resolution_notes:
            alert.resolution_notes = data.resolution_notes

    alert.status = data.status
    await db.commit()
    return {"message": f"Alert {data.status}"}


@router.get("/stats/summary")
async def get_alert_stats(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context

    result = await db.execute(
        select(Alert.status, Alert.severity, func.count(Alert.id))
        .where(Alert.organization_id == org.id)
        .group_by(Alert.status, Alert.severity)
    )
    rows = result.all()

    stats = {"by_status": {}, "by_severity": {}, "total": 0}
    for status, severity, count in rows:
        stats["by_status"][status] = stats["by_status"].get(status, 0) + count
        stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + count
        stats["total"] += count

    return stats
