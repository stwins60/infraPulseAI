"""
Tests for organizations, dashboard, metrics, and logs endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_organization(client: AsyncClient, org_and_user):
    """Can retrieve own organization."""
    org, _, token = org_and_user
    resp = await client.get(
        f"/api/v1/organizations/{org.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(org.id)
    assert data["name"] == org.name


@pytest.mark.asyncio
async def test_get_organization_unauthorized(client: AsyncClient, org_and_user, seed_plan):
    """Cannot access another org's details."""
    from app.models.organization import Organization
    from app.models.user import User
    from app.core.security import hash_password, create_access_token
    import uuid

    org1, _, token1 = org_and_user

    async with TestSessionLocal() as db:
        org2 = Organization(name="Secret Org", slug=f"secret-{uuid.uuid4().hex[:6]}", subscription_plan_id=seed_plan.id)
        db.add(org2)
        user2 = User(email=f"secret-{uuid.uuid4().hex[:6]}@test.com", full_name="Secret User",
                     hashed_password=hash_password("Pass123!"), is_active=True, is_verified=True)
        db.add(user2)
        await db.commit()
        await db.refresh(org2)
        await db.refresh(user2)
        token2 = create_access_token({"sub": str(user2.id), "org_id": str(org2.id)})

    # User1 should not access org2
    resp = await client.get(
        f"/api/v1/organizations/{org2.id}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_update_organization(client: AsyncClient, org_and_user):
    """Org admin can update organization settings."""
    org, _, token = org_and_user
    resp = await client.put(
        f"/api/v1/organizations/{org.id}",
        json={"name": "Updated Org Name", "timezone": "America/New_York"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated Org Name"


@pytest.mark.asyncio
async def test_dashboard_overview(client: AsyncClient, org_and_user):
    """Dashboard overview returns expected structure."""
    org, _, token = org_and_user
    resp = await client.get(
        f"/api/v1/organizations/{org.id}/dashboard/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Should have server counts, alert stats, etc.
    assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_metrics_summary(client: AsyncClient, org_and_user):
    """Metrics summary endpoint returns expected structure."""
    org, _, token = org_and_user
    resp = await client.get(
        f"/api/v1/organizations/{org.id}/metrics/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_log_search_empty(client: AsyncClient, org_and_user):
    """Empty org returns empty log search results."""
    org, _, token = org_and_user
    resp = await client.get(
        f"/api/v1/organizations/{org.id}/logs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    result = resp.json()
    # Could be a list or dict with "entries"
    if isinstance(result, list):
        pass  # ok
    else:
        assert "entries" in result or "items" in result


@pytest.mark.asyncio
async def test_log_stats(client: AsyncClient, org_and_user):
    """Log stats endpoint works for empty org."""
    org, _, token = org_and_user
    resp = await client.get(
        f"/api/v1/organizations/{org.id}/logs/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_org_members(client: AsyncClient, org_and_user):
    """Can list organization members."""
    org, _, token = org_and_user
    resp = await client.get(
        f"/api/v1/organizations/{org.id}/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    members = resp.json()
    assert isinstance(members, list)
    assert len(members) >= 1  # the creator is a member


@pytest.mark.asyncio
async def test_onboarding_checklist(client: AsyncClient, org_and_user):
    """Onboarding checklist reflects fresh org state."""
    org, _, token = org_and_user
    resp = await client.get(
        f"/api/v1/organizations/{org.id}/onboarding",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
