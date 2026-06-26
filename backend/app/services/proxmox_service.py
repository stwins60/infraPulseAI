import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import aiohttp
import structlog

logger = structlog.get_logger(__name__)


class ProxmoxService:
    """Service for interacting with the Proxmox VE API."""

    def __init__(self, hostname: str, port: int, token_id: str, token_secret: str, verify_ssl: bool = True):
        self.hostname = hostname
        self.port = port
        self.token_id = token_id
        self.token_secret = token_secret
        self.verify_ssl = verify_ssl
        self.base_url = f"https://{hostname}:{port}/api2/json"
        self._connector = None

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"PVEAPIToken={self.token_id}={self.token_secret}",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str) -> Dict[str, Any]:
        """Make an authenticated GET request to the Proxmox API."""
        import ssl
        ssl_context = False if not self.verify_ssl else None
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}{path}",
                headers=self._get_headers(),
                ssl=ssl_context,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("data", {})

    async def test_connection(self) -> Dict[str, Any]:
        """Test Proxmox API connectivity."""
        try:
            version_data = await self._get("/version")
            return {
                "success": True,
                "version": version_data.get("version"),
                "release": version_data.get("release"),
                "message": f"Connected to Proxmox VE {version_data.get('version', 'unknown')}",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Connection failed: {str(e)}",
                "error": str(e),
            }

    async def get_nodes(self) -> List[Dict[str, Any]]:
        """Get all nodes in the cluster."""
        try:
            data = await self._get("/nodes")
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error("Failed to get Proxmox nodes", error=str(e))
            return []

    async def get_node_status(self, node: str) -> Dict[str, Any]:
        """Get detailed status for a node."""
        try:
            return await self._get(f"/nodes/{node}/status")
        except Exception as e:
            logger.error("Failed to get node status", node=node, error=str(e))
            return {}

    async def get_vms(self, node: str) -> List[Dict[str, Any]]:
        """Get all VMs (QEMU) on a node."""
        try:
            data = await self._get(f"/nodes/{node}/qemu")
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error("Failed to get VMs", node=node, error=str(e))
            return []

    async def get_containers(self, node: str) -> List[Dict[str, Any]]:
        """Get all LXC containers on a node."""
        try:
            data = await self._get(f"/nodes/{node}/lxc")
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error("Failed to get containers", node=node, error=str(e))
            return []

    async def get_storage(self, node: str) -> List[Dict[str, Any]]:
        """Get storage information for a node."""
        try:
            data = await self._get(f"/nodes/{node}/storage")
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error("Failed to get storage", node=node, error=str(e))
            return []

    async def get_tasks(self, node: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent tasks for a node."""
        try:
            data = await self._get(f"/nodes/{node}/tasks?limit={limit}")
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error("Failed to get tasks", node=node, error=str(e))
            return []

    async def get_cluster_status(self) -> Dict[str, Any]:
        """Get cluster status information."""
        try:
            return await self._get("/cluster/status")
        except Exception as e:
            logger.error("Failed to get cluster status", error=str(e))
            return {}

    async def collect_full_inventory(self) -> Dict[str, Any]:
        """Collect complete inventory: nodes, VMs, containers."""
        version_info = {}
        try:
            version_info = await self._get("/version")
        except Exception:
            pass

        nodes_raw = await self.get_nodes()
        nodes = []
        vms = []
        containers = []

        for node_raw in nodes_raw:
            node_name = node_raw.get("node")
            if not node_name:
                continue

            node_status = {}
            try:
                node_status = await self.get_node_status(node_name)
            except Exception:
                pass

            nodes.append({
                "node_name": node_name,
                "status": node_raw.get("status", "unknown"),
                "uptime": node_raw.get("uptime"),
                "cpu_usage": node_raw.get("cpu"),
                "memory_used": node_raw.get("mem"),
                "memory_total": node_raw.get("maxmem"),
                "disk_used": node_raw.get("disk"),
                "disk_total": node_raw.get("maxdisk"),
                "cpu_count": node_status.get("cpuinfo", {}).get("cpus"),
                "pve_version": version_info.get("version"),
            })

            # Get VMs
            for vm in await self.get_vms(node_name):
                vms.append({
                    "vmid": vm.get("vmid"),
                    "name": vm.get("name"),
                    "vm_type": "qemu",
                    "status": vm.get("status", "unknown"),
                    "uptime": vm.get("uptime"),
                    "cpu_usage": vm.get("cpu"),
                    "memory_used": vm.get("mem"),
                    "memory_total": vm.get("maxmem"),
                    "disk_used": vm.get("disk"),
                    "disk_total": vm.get("maxdisk"),
                    "network_in": vm.get("netin"),
                    "network_out": vm.get("netout"),
                    "node_name": node_name,
                    "template": bool(vm.get("template")),
                })

            # Get containers
            for ct in await self.get_containers(node_name):
                containers.append({
                    "vmid": ct.get("vmid"),
                    "name": ct.get("name"),
                    "vm_type": "lxc",
                    "status": ct.get("status", "unknown"),
                    "uptime": ct.get("uptime"),
                    "cpu_usage": ct.get("cpu"),
                    "memory_used": ct.get("mem"),
                    "memory_total": ct.get("maxmem"),
                    "disk_used": ct.get("disk"),
                    "disk_total": ct.get("maxdisk"),
                    "node_name": node_name,
                })

        return {
            "version": version_info.get("version"),
            "nodes": nodes,
            "vms": vms,
            "containers": containers,
        }
