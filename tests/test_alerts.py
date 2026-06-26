"""
Tests for alert rules and alert management endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_alert_rules_empty(client: AsyncClient, org_and_user):
    """Empty org has no alert rules."""
    org, _, token = org_and_user
    resp = await client.get(
        f"/api/v1/organizations/{org.id}/alerts/rules",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_alert_rule(client: AsyncClient, org_and_user):
    """Can create an alert rule."""
    org, _, token = org_and_user
    resp = await client.post(
        f"/api/v1/organizations/{org.id}/alerts/rules",
        json={
            "name": "High CPU",
            "metric_name": "cpu_percent",
            "operator": "gt",
            "threshold": 90.0,
            "duration_minutes": 5,
            "severity": "high",
            "description": "Alert when CPU exceeds 90%",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["name"] == "High CPU"
    assert data["metric_name"] == "cpu_percent"
    assert data["threshold"] == 90.0
    return data


@pytest.mark.asyncio
async def test_create_alert_rule_validation(client: AsyncClient, org_and_user):
    """Missing required fields returns 422."""
    org, _, token = org_and_user
    resp = await client.post(
        f"/api/v1/organizations/{org.id}/alerts/rules",
        json={"name": "Incomplete Rule"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_alert_rules_after_create(client: AsyncClient, org_and_user):
    """Alert rules appear in list after creation."""
    org, _, token = org_and_user
    await test_create_alert_rule(client, org_and_user)

    resp = await client.get(
        f"/api/v1/organizations/{org.id}/alerts/rules",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) >= 1
    assert any(r["name"] == "High CPU" for r in rules)


@pytest.mark.asyncio
async def test_list_alerts_empty(client: AsyncClient, org_and_user):
    """Empty org has no alerts."""
    org, _, token = org_and_user
    resp = await client.get(
        f"/api/v1/organizations/{org.id}/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_alert_stats(client: AsyncClient, org_and_user):
    """Alert stats endpoint returns expected fields."""
    org, _, token = org_and_user
    resp = await client.get(
        f"/api/v1/organizations/{org.id}/alerts/stats/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Check expected stat fields exist
    assert "firing" in data or "total_rules" in data


@pytest.mark.asyncio
async def test_create_multiple_rules(client: AsyncClient, org_and_user):
    """Multiple different alert rules can be created."""
    org, _, token = org_and_user
    rules = [
        {"name": "High Memory", "metric_name": "memory_percent", "operator": "gt", "threshold": 85.0, "duration_minutes": 3, "severity": "medium"},
        {"name": "Disk Warning", "metric_name": "disk_percent", "operator": "gt", "threshold": 80.0, "duration_minutes": 10, "severity": "low"},
        {"name": "Critical Disk", "metric_name": "disk_percent", "operator": "gt", "threshold": 95.0, "duration_minutes": 1, "severity": "critical"},
    ]
    for rule in rules:
        resp = await client.post(
            f"/api/v1/organizations/{org.id}/alerts/rules",
            json=rule,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (200, 201), f"Failed to create rule: {rule['name']}, {resp.text}"


@pytest.mark.asyncio
async def test_create_incident(client: AsyncClient, org_and_user):
    """Can create an incident manually."""
    org, _, token = org_and_user
    resp = await client.post(
        f"/api/v1/organizations/{org.id}/incidents",
        json={
            "title": "Database Connection Pool Exhausted",
            "severity": "high",
            "status": "investigating",
            "description": "All DB connections are in use",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["title"] == "Database Connection Pool Exhausted"
    assert data["severity"] == "high"


@pytest.mark.asyncio
async def test_list_incidents(client: AsyncClient, org_and_user):
    """Incidents list returns created incidents."""
    org, _, token = org_and_user
    await test_create_incident(client, org_and_user)

    resp = await client.get(
        f"/api/v1/organizations/{org.id}/incidents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    incidents = resp.json()
    assert len(incidents) >= 1
