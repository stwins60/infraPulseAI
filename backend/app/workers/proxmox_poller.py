import asyncio
from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def get_async_session():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(name="app.workers.proxmox_poller.poll_all_proxmox_connections", queue="proxmox")
def poll_all_proxmox_connections():
    asyncio.run(_poll_all_connections())


async def _poll_all_connections():
    from app.models.proxmox import ProxmoxConnection

    session_factory = get_async_session()
    async with session_factory() as db:
        result = await db.execute(
            select(ProxmoxConnection).where(ProxmoxConnection.is_active == True)
        )
        connections = result.scalars().all()
        logger.info("Polling Proxmox connections", count=len(connections))
        for conn in connections:
            await _sync_connection(db, conn)


async def _sync_connection(db: AsyncSession, conn):
    from app.services.proxmox_service import ProxmoxService
    from app.services.encryption_service import decrypt
    from app.models.proxmox import ProxmoxNode, ProxmoxVM
    from app.models.metric import Metric

    try:
        token_secret = decrypt(conn.token_secret_encrypted)
        svc = ProxmoxService(conn.hostname, conn.port, conn.token_id, token_secret, conn.verify_ssl)
        inventory = await svc.collect_full_inventory()

        conn.connection_status = "connected"
        conn.last_connected_at = datetime.now(timezone.utc)
        conn.last_error = None
        conn.version = inventory.get("version")
        conn.node_count = len(inventory["nodes"])
        conn.vm_count = len([v for v in inventory["vms"] if v["vm_type"] == "qemu"])
        conn.container_count = len([v for v in inventory["vms"] if v["vm_type"] == "lxc"])

        # Sync nodes
        for node_data in inventory["nodes"]:
            node_result = await db.execute(
                select(ProxmoxNode).where(
                    ProxmoxNode.connection_id == conn.id,
                    ProxmoxNode.node_name == node_data["node_name"],
                )
            )
            node = node_result.scalar_one_or_none()
            if not node:
                node = ProxmoxNode(
                    connection_id=conn.id,
                    organization_id=conn.organization_id,
                    node_name=node_data["node_name"],
                )
                db.add(node)

            node.status = node_data["status"]
            node.uptime = node_data.get("uptime")
            node.cpu_usage = node_data.get("cpu_usage")
            node.memory_used = node_data.get("memory_used")
            node.memory_total = node_data.get("memory_total")
            node.disk_used = node_data.get("disk_used")
            node.disk_total = node_data.get("disk_total")
            node.cpu_count = node_data.get("cpu_count")
            node.pve_version = node_data.get("pve_version")
            node.last_seen_at = datetime.now(timezone.utc)

            await db.flush()

            # Store metrics
            if node_data.get("cpu_usage") is not None:
                db.add(Metric(
                    organization_id=conn.organization_id,
                    proxmox_node_id=node.id,
                    source_type="proxmox_node",
                    metric_name="cpu_percent",
                    value=node_data["cpu_usage"] * 100,
                    unit="%",
                    labels={"node": node_data["node_name"]},
                ))
            if node_data.get("memory_used") and node_data.get("memory_total"):
                mem_pct = (node_data["memory_used"] / node_data["memory_total"]) * 100
                db.add(Metric(
                    organization_id=conn.organization_id,
                    proxmox_node_id=node.id,
                    source_type="proxmox_node",
                    metric_name="memory_percent",
                    value=mem_pct,
                    unit="%",
                    labels={"node": node_data["node_name"]},
                ))

        # Sync VMs and containers
        all_vms = inventory["vms"] + inventory["containers"]
        for vm_data in all_vms:
            vm_result = await db.execute(
                select(ProxmoxVM).where(
                    ProxmoxVM.connection_id == conn.id,
                    ProxmoxVM.vmid == vm_data["vmid"],
                )
            )
            vm = vm_result.scalar_one_or_none()
            if not vm:
                vm = ProxmoxVM(
                    connection_id=conn.id,
                    organization_id=conn.organization_id,
                    vmid=vm_data["vmid"],
                )
                db.add(vm)

            vm.name = vm_data.get("name")
            vm.vm_type = vm_data.get("vm_type", "qemu")
            vm.status = vm_data.get("status", "unknown")
            vm.uptime = vm_data.get("uptime")
            vm.cpu_usage = vm_data.get("cpu_usage")
            vm.memory_used = vm_data.get("memory_used")
            vm.memory_total = vm_data.get("memory_total")
            vm.disk_used = vm_data.get("disk_used")
            vm.node_name = vm_data.get("node_name")
            vm.template = vm_data.get("template", False)
            vm.last_seen_at = datetime.now(timezone.utc)

        await db.commit()
        logger.info("Proxmox sync complete", connection_id=str(conn.id), nodes=len(inventory["nodes"]))

    except Exception as e:
        logger.error("Proxmox sync failed", connection_id=str(conn.id), error=str(e))
        conn.connection_status = "error"
        conn.last_error = str(e)[:500]
        await db.commit()


@celery_app.task(name="app.workers.proxmox_poller.poll_proxmox_connection", queue="proxmox")
def poll_proxmox_connection(connection_id: str):
    asyncio.run(_poll_single_connection(connection_id))


async def _poll_single_connection(connection_id: str):
    from app.models.proxmox import ProxmoxConnection
    session_factory = get_async_session()
    async with session_factory() as db:
        conn = await db.get(ProxmoxConnection, UUID(connection_id))
        if conn:
            await _sync_connection(db, conn)
