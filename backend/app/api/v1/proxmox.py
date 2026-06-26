from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.dependencies import require_org_role
from app.core.exceptions import NotFoundError, ValidationError
from app.models.proxmox import ProxmoxConnection, ProxmoxNode, ProxmoxVM
from app.services.proxmox_service import ProxmoxService
from app.services.encryption_service import encrypt, decrypt
from app.schemas.proxmox import (
    ProxmoxConnectionCreate, ProxmoxConnectionOut, ProxmoxConnectionUpdate,
    ProxmoxNodeOut, ProxmoxVMOut,
)

router = APIRouter()


@router.get("/connections", response_model=List[ProxmoxConnectionOut])
async def list_connections(
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    result = await db.execute(
        select(ProxmoxConnection).where(ProxmoxConnection.organization_id == org.id)
    )
    return result.scalars().all()


@router.post("/connections", response_model=ProxmoxConnectionOut, status_code=201)
async def create_connection(
    data: ProxmoxConnectionCreate,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context

    encrypted_secret = encrypt(data.token_secret)
    conn = ProxmoxConnection(
        organization_id=org.id,
        name=data.name,
        hostname=data.hostname,
        port=data.port,
        token_id=data.token_id,
        token_secret_encrypted=encrypted_secret,
        verify_ssl=data.verify_ssl,
        cluster_label=data.cluster_label,
        environment=data.environment,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return conn


@router.get("/connections/{conn_id}", response_model=ProxmoxConnectionOut)
async def get_connection(
    conn_id: UUID,
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    conn = await db.get(ProxmoxConnection, conn_id)
    if not conn or conn.organization_id != org.id:
        raise NotFoundError("Proxmox connection")
    return conn


@router.put("/connections/{conn_id}", response_model=ProxmoxConnectionOut)
async def update_connection(
    conn_id: UUID,
    data: ProxmoxConnectionUpdate,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    conn = await db.get(ProxmoxConnection, conn_id)
    if not conn or conn.organization_id != org.id:
        raise NotFoundError("Proxmox connection")

    update_data = data.model_dump(exclude_unset=True)
    if "token_secret" in update_data:
        conn.token_secret_encrypted = encrypt(update_data.pop("token_secret"))
    for field, value in update_data.items():
        setattr(conn, field, value)
    await db.commit()
    await db.refresh(conn)
    return conn


@router.delete("/connections/{conn_id}")
async def delete_connection(
    conn_id: UUID,
    org_context=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    conn = await db.get(ProxmoxConnection, conn_id)
    if not conn or conn.organization_id != org.id:
        raise NotFoundError("Proxmox connection")
    conn.is_active = False
    await db.commit()
    return {"message": "Connection deactivated"}


@router.post("/connections/{conn_id}/test")
async def test_connection(
    conn_id: UUID,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    conn = await db.get(ProxmoxConnection, conn_id)
    if not conn or conn.organization_id != org.id:
        raise NotFoundError("Proxmox connection")

    token_secret = decrypt(conn.token_secret_encrypted)
    svc = ProxmoxService(conn.hostname, conn.port, conn.token_id, token_secret, conn.verify_ssl)
    result = await svc.test_connection()
    return result


@router.post("/connections/{conn_id}/sync")
async def sync_connection(
    conn_id: UUID,
    background_tasks: BackgroundTasks,
    org_context=Depends(require_org_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    conn = await db.get(ProxmoxConnection, conn_id)
    if not conn or conn.organization_id != org.id:
        raise NotFoundError("Proxmox connection")

    from app.workers.proxmox_poller import poll_proxmox_connection
    background_tasks.add_task(poll_proxmox_connection, str(conn_id))
    return {"message": "Sync started"}


@router.get("/connections/{conn_id}/nodes", response_model=List[ProxmoxNodeOut])
async def list_nodes(
    conn_id: UUID,
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    result = await db.execute(
        select(ProxmoxNode).where(
            ProxmoxNode.connection_id == conn_id,
            ProxmoxNode.organization_id == org.id,
        )
    )
    return result.scalars().all()


@router.get("/connections/{conn_id}/vms", response_model=List[ProxmoxVMOut])
async def list_vms(
    conn_id: UUID,
    vm_type: Optional[str] = None,
    org_context=Depends(require_org_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = org_context
    query = select(ProxmoxVM).where(
        ProxmoxVM.connection_id == conn_id,
        ProxmoxVM.organization_id == org.id,
    )
    if vm_type:
        query = query.where(ProxmoxVM.vm_type == vm_type)
    result = await db.execute(query)
    return result.scalars().all()
