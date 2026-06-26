from fastapi import APIRouter

from app.api.v1 import (
    auth,
    organizations,
    users,
    servers,
    agent,
    metrics,
    logs,
    alerts,
    incidents,
    proxmox,
    ai_ops,
    notifications,
    audit,
    dashboard,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["Organizations"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(servers.router, prefix="/organizations/{org_id}/servers", tags=["Servers"])
api_router.include_router(agent.router, prefix="/agent", tags=["Agent"])
api_router.include_router(metrics.router, prefix="/organizations/{org_id}/metrics", tags=["Metrics"])
api_router.include_router(logs.router, prefix="/organizations/{org_id}/logs", tags=["Logs"])
api_router.include_router(alerts.router, prefix="/organizations/{org_id}/alerts", tags=["Alerts"])
api_router.include_router(incidents.router, prefix="/organizations/{org_id}/incidents", tags=["Incidents"])
api_router.include_router(proxmox.router, prefix="/organizations/{org_id}/proxmox", tags=["Proxmox"])
api_router.include_router(ai_ops.router, prefix="/organizations/{org_id}/ai", tags=["AI Operations"])
api_router.include_router(notifications.router, prefix="/organizations/{org_id}/notifications", tags=["Notifications"])
api_router.include_router(audit.router, prefix="/organizations/{org_id}/audit", tags=["Audit Logs"])
api_router.include_router(dashboard.router, prefix="/organizations/{org_id}/dashboard", tags=["Dashboard"])
