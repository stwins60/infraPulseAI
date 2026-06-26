"""
Tests for server and agent endpoints.
"""

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_servers_empty(client: AsyncClient, org_and_user):
    """Empty server list returns empty array."""
    org, _, token = org_and_user
    resp = await client.get(
        f"/api/v1/organizations/{org.id}/servers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_agent_token(client: AsyncClient, org_and_user):
    """Can create agent registration token."""
    org, _, token = org_and_user
    resp = await client.post(
        f"/api/v1/organizations/{org.id}/servers/agent-tokens",
        json={"label": "test-server", "environment": "production"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data or "registration_token" in data


@pytest.mark.asyncio
async def test_agent_register(client: AsyncClient, org_and_user):
    """Agent can register with a valid registration token."""
    org, _, token = org_and_user

    # First create a registration token
    resp = await client.post(
        f"/api/v1/organizations/{org.id}/servers/agent-tokens",
        json={"label": "ci-server"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    reg_token_data = resp.json()
    reg_token = reg_token_data.get("token") or reg_token_data.get("registration_token")

    # Register agent
    resp = await client.post("/api/v1/agent/register", json={
        "registration_token": reg_token,
        "hostname": "test-server-01",
        "ip_addresses": ["192.168.1.10"],
        "os_type": "linux",
        "os_version": "Ubuntu 22.04",
        "agent_version": "1.0.0",
        "environment": "production",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "agent_token" in data
    assert "server_id" in data
    return data


@pytest.mark.asyncio
async def test_agent_heartbeat(client: AsyncClient, org_and_user):
    """Agent can send heartbeat after registration."""
    # Register first
    data = await test_agent_register(client, org_and_user)
    agent_token = data["agent_token"]

    resp = await client.post(
        "/api/v1/agent/heartbeat",
        json={"hostname": "test-server-01", "uptime_seconds": 3600, "agent_version": "1.0.0"},
        headers={"X-Agent-Token": agent_token},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_agent_ingest_metrics(client: AsyncClient, org_and_user):
    """Agent can send metrics."""
    data = await test_agent_register(client, org_and_user)
    agent_token = data["agent_token"]

    metrics = [
        {"name": "cpu_percent", "value": 45.5, "unit": "%"},
        {"name": "memory_percent", "value": 62.1, "unit": "%"},
        {"name": "disk_percent", "value": 33.0, "unit": "%"},
    ]

    resp = await client.post(
        "/api/v1/agent/metrics",
        json={"metrics": metrics},
        headers={"X-Agent-Token": agent_token},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_agent_ingest_logs(client: AsyncClient, org_and_user):
    """Agent can send log entries."""
    data = await test_agent_register(client, org_and_user)
    agent_token = data["agent_token"]

    logs = [
        {"timestamp": "2026-06-25T10:00:00Z", "level": "info", "source": "syslog", "message": "System started"},
        {"timestamp": "2026-06-25T10:00:01Z", "level": "error", "source": "auth", "message": "Authentication failed for user root"},
    ]

    resp = await client.post(
        "/api/v1/agent/logs",
        json={"entries": logs},
        headers={"X-Agent-Token": agent_token},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_server_after_register(client: AsyncClient, org_and_user):
    """Server appears in list after agent registration."""
    org, _, token = org_and_user
    await test_agent_register(client, org_and_user)

    resp = await client.get(
        f"/api/v1/organizations/{org.id}/servers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    servers = resp.json()
    assert any(s["hostname"] == "test-server-01" for s in servers)


@pytest.mark.asyncio
async def test_agent_invalid_token(client: AsyncClient):
    """Invalid agent token returns 401."""
    resp = await client.post(
        "/api/v1/agent/heartbeat",
        json={"hostname": "ghost"},
        headers={"X-Agent-Token": "invalid-token-xyz"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_server_not_found(client: AsyncClient, org_and_user):
    """Non-existent server returns 404."""
    org, _, token = org_and_user
    resp = await client.get(
        f"/api/v1/organizations/{org.id}/servers/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
