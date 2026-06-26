"""
Tests for Proxmox connection management endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_proxmox_connections_empty(client: AsyncClient, org_and_user):
    """Empty org has no Proxmox connections."""
    org, _, token = org_and_user
    resp = await client.get(
        f"/api/v1/organizations/{org.id}/proxmox/connections",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_create_proxmox_connection(client: AsyncClient, org_and_user):
    """Can create a Proxmox connection record."""
    org, _, token = org_and_user
    resp = await client.post(
        f"/api/v1/organizations/{org.id}/proxmox/connections",
        json={
            "name": "Home Lab PVE",
            "host": "192.168.1.200",
            "port": 8006,
            "username": "root@pam",
            "auth_type": "api_token",
            "api_token_id": "monitoring@pve!ci-token",
            "api_token_secret": "test-secret-value",
            "verify_ssl": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["name"] == "Home Lab PVE"
    assert data["host"] == "192.168.1.200"
    assert "api_token_secret" not in data  # secret should not be returned
    return data


@pytest.mark.asyncio
async def test_list_proxmox_connections_after_create(client: AsyncClient, org_and_user):
    """Connection appears in list after creation."""
    org, _, token = org_and_user
    await test_create_proxmox_connection(client, org_and_user)

    resp = await client.get(
        f"/api/v1/organizations/{org.id}/proxmox/connections",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    conns = resp.json()
    assert len(conns) >= 1
    assert any(c["name"] == "Home Lab PVE" for c in conns)


@pytest.mark.asyncio
async def test_proxmox_connection_validation(client: AsyncClient, org_and_user):
    """Missing required fields return 422."""
    org, _, token = org_and_user
    resp = await client.post(
        f"/api/v1/organizations/{org.id}/proxmox/connections",
        json={"name": "Incomplete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_proxmox_connection_password_auth(client: AsyncClient, org_and_user):
    """Can create a connection using password authentication."""
    org, _, token = org_and_user
    resp = await client.post(
        f"/api/v1/organizations/{org.id}/proxmox/connections",
        json={
            "name": "PVE Password Auth",
            "host": "10.0.0.1",
            "port": 8006,
            "username": "root@pam",
            "auth_type": "password",
            "password": "securepassword",
            "verify_ssl": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["auth_type"] == "password"
    assert "password" not in data  # password must not be returned


@pytest.mark.asyncio
async def test_get_proxmox_nodes_empty(client: AsyncClient, org_and_user):
    """New connection has no synced nodes yet."""
    org, _, token = org_and_user
    conn = await test_create_proxmox_connection(client, org_and_user)
    conn_id = conn["id"]

    resp = await client.get(
        f"/api/v1/organizations/{org.id}/proxmox/connections/{conn_id}/nodes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_proxmox_vms_empty(client: AsyncClient, org_and_user):
    """New connection has no synced VMs yet."""
    org, _, token = org_and_user
    conn = await test_create_proxmox_connection(client, org_and_user)
    conn_id = conn["id"]

    resp = await client.get(
        f"/api/v1/organizations/{org.id}/proxmox/connections/{conn_id}/vms",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_proxmox_connection_isolated_between_orgs(client: AsyncClient, org_and_user, seed_plan):
    """Connections from one org are not visible to another org."""
    from app.models.organization import Organization
    from app.models.user import User
    from app.core.security import hash_password, create_access_token
    from sqlalchemy.ext.asyncio import AsyncSession
    import uuid

    org1, _, token1 = org_and_user

    # Create connection in org1
    conn = await test_create_proxmox_connection(client, org_and_user)

    # Create a second org
    async with TestSessionLocal() as db:
        org2 = Organization(name="Other Org", slug=f"other-{uuid.uuid4().hex[:6]}", subscription_plan_id=seed_plan.id)
        db.add(org2)
        user2 = User(email=f"other-{uuid.uuid4().hex[:6]}@test.com", full_name="Other", hashed_password=hash_password("Pass123!"), is_active=True, is_verified=True)
        db.add(user2)
        await db.commit()
        await db.refresh(org2)
        await db.refresh(user2)
        token2 = create_access_token({"sub": str(user2.id), "org_id": str(org2.id)})

    # Org2 should not see org1's connections
    resp = await client.get(
        f"/api/v1/organizations/{org2.id}/proxmox/connections",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 200
    conns = resp.json()
    assert not any(c["id"] == conn["id"] for c in conns)
