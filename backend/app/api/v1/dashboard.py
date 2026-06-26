from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.core.dependencies import require_org_role
from app.models.server import Server
from app.models.proxmox import ProxmoxConnection, ProxmoxNode, ProxmoxVM
from app.models.alert import Alert
from app.models.incident import Incident
from app.models.metric import Metric
from app.models.log_entry import LogEntry
from app.models.ai_analysis import AIAnalysis

router = APIRouter()


@router.get("/overview")
async def get_dashboard_overview(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context

    # Server stats
    server_stats = await db.execute(
        select(Server.status, func.count(Server.id))
        .where(Server.organization_id == org.id, Server.is_active == True)
        .group_by(Server.status)
    )
    status_counts = {row[0]: row[1] for row in server_stats.all()}

    total_servers = sum(status_counts.values())
    online_servers = status_counts.get("online", 0)
    warning_servers = status_counts.get("warning", 0)
    critical_servers = status_counts.get("critical", 0)
    offline_servers = status_counts.get("offline", 0)

    # Proxmox stats
    px_count = await db.execute(
        select(func.count(ProxmoxConnection.id))
        .where(ProxmoxConnection.organization_id == org.id, ProxmoxConnection.is_active == True)
    )
    proxmox_clusters = px_count.scalar() or 0

    running_vms = await db.execute(
        select(func.count(ProxmoxVM.id))
        .where(ProxmoxVM.organization_id == org.id, ProxmoxVM.status == "running", ProxmoxVM.vm_type == "qemu")
    )
    running_containers = await db.execute(
        select(func.count(ProxmoxVM.id))
        .where(ProxmoxVM.organization_id == org.id, ProxmoxVM.status == "running", ProxmoxVM.vm_type == "lxc")
    )

    # Alert stats (last 24h)
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    alerts_24h = await db.execute(
        select(func.count(Alert.id))
        .where(Alert.organization_id == org.id, Alert.created_at >= since_24h)
    )
    open_incidents = await db.execute(
        select(func.count(Incident.id))
        .where(Incident.organization_id == org.id, Incident.status == "open")
    )

    # Recent alerts
    recent_alerts = await db.execute(
        select(Alert)
        .where(Alert.organization_id == org.id)
        .order_by(Alert.created_at.desc())
        .limit(10)
    )
    alerts_list = recent_alerts.scalars().all()

    # Recent AI analyses
    recent_ai = await db.execute(
        select(AIAnalysis)
        .where(AIAnalysis.organization_id == org.id)
        .order_by(AIAnalysis.created_at.desc())
        .limit(5)
    )
    ai_list = recent_ai.scalars().all()

    # Health score
    health_score_result = await db.execute(
        select(func.avg(Server.health_score))
        .where(Server.organization_id == org.id, Server.is_active == True, Server.health_score.isnot(None))
    )
    avg_health = health_score_result.scalar()
    infrastructure_health_score = round(avg_health) if avg_health else 0

    return {
        "total_servers": total_servers,
        "online_servers": online_servers,
        "warning_servers": warning_servers,
        "critical_servers": critical_servers,
        "offline_servers": offline_servers,
        "proxmox_clusters": proxmox_clusters,
        "running_vms": running_vms.scalar() or 0,
        "running_containers": running_containers.scalar() or 0,
        "open_incidents": open_incidents.scalar() or 0,
        "alerts_24h": alerts_24h.scalar() or 0,
        "infrastructure_health_score": infrastructure_health_score,
        "recent_alerts": [
            {
                "id": str(a.id),
                "title": a.title,
                "severity": a.severity,
                "status": a.status,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts_list
        ],
        "recent_ai_analyses": [
            {
                "id": str(a.id),
                "analysis_type": a.analysis_type,
                "summary": a.result.get("summary", ""),
                "severity": a.result.get("severity_assessment", ""),
                "created_at": a.created_at.isoformat(),
            }
            for a in ai_list
        ],
    }
