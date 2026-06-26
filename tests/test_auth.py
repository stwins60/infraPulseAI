"""
Tests for authentication endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, seed_plan):
    """User can register and receives tokens."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": "newuser@example.com",
        "password": "SecurePass123!",
        "full_name": "New User",
        "organization_name": "New Org",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["email"] == "newuser@example.com"
    assert "organization_id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, seed_plan):
    """Duplicate email registration returns 400."""
    payload = {
        "email": "duplicate@example.com",
        "password": "SecurePass123!",
        "full_name": "User",
        "organization_name": "Org",
    }
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient, seed_plan):
    """Weak password returns validation error."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": "user@example.com",
        "password": "123",
        "full_name": "User",
        "organization_name": "Org",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, seed_plan):
    """Valid credentials return tokens."""
    email = "login_test@example.com"
    password = "LoginPass456!"
    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "Login User",
        "organization_name": "Login Org",
    })
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, seed_plan):
    """Wrong password returns 401."""
    email = "wrongpwd@example.com"
    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "RightPass123!",
        "full_name": "User",
        "organization_name": "Org",
    })
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPass!"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """Nonexistent email returns 401."""
    resp = await client.post("/api/v1/auth/login", json={
        "email": "nobody@nowhere.com",
        "password": "SomePass123!",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_refresh(client: AsyncClient, seed_plan):
    """Refresh token returns new access token."""
    # Register + login
    email = "refresh_user@example.com"
    await client.post("/api/v1/auth/register", json={
        "email": email, "password": "RefreshPass123!", "full_name": "Refresh User", "organization_name": "Org"
    })
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "RefreshPass123!"})
    refresh_token = login.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_protected_endpoint_without_token(client: AsyncClient):
    """Accessing protected endpoint without token returns 401."""
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient, org_and_user):
    """Authenticated user can get own profile."""
    _, user, token = org_and_user
    resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == user.email
