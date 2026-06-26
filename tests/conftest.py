"""
Test configuration and fixtures for InfraPulse AI test suite.
"""

import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.database import get_db
from app.models.base import Base
from app.models.organization import Organization, SubscriptionPlan
from app.models.user import User
from app.core.security import hash_password, create_access_token

# ── Test DB (SQLite in-memory) ────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def seed_plan(db: AsyncSession) -> SubscriptionPlan:
    plan = SubscriptionPlan(
        name="free",
        display_name="Free",
        max_servers=5,
        max_users=3,
        max_alert_rules=10,
        retention_days=7,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


@pytest_asyncio.fixture
async def org_and_user(db: AsyncSession, seed_plan: SubscriptionPlan):
    """Returns (org, user, access_token)"""
    org = Organization(
        name="Test Org",
        slug=f"test-org-{uuid.uuid4().hex[:6]}",
        subscription_plan_id=seed_plan.id,
    )
    db.add(org)
    await db.flush()

    user = User(
        email=f"test-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Test User",
        hashed_password=hash_password("TestPass123!"),
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(org)
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id), "org_id": str(org.id)})
    return org, user, token


@pytest.fixture
def auth_headers(org_and_user):
    _, _, token = org_and_user
    return {"Authorization": f"Bearer {token}"}
