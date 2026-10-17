"""Shared pytest fixtures. Env is set before app imports."""

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

import bcrypt
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import create_async_engine

TEST_DB_NAME = "corplunch_test"


def _database_url_for_tests() -> str:
    raw = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://corplunch:corplunch@localhost:5432/corplunch_test",
    )
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    return (
        make_url(raw).set(database=TEST_DB_NAME).render_as_string(hide_password=False)
    )


os.environ["DATABASE_URL"] = _database_url_for_tests()
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_EXPIRE_MINUTES", "480")
os.environ.setdefault("MEALTY_CITY", "Москва")
os.environ.setdefault("CUTOFF_TIME", "16:00")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.auth.deps import require_admin
from app.catalog.models import Dish, PriceHistory  # noqa: F401
from app.db import Base, SessionLocal, engine
from app.main import app
from app.orders.models import OfficeOrder, OfficeOrderItem  # noqa: F401
from app.planning.models import MealPlan, PlanItem  # noqa: F401
from app.users.models import (  # noqa: F401
    CatalogSyncRun,
    Department,
    Settings,
    User,
    UserRole,
)


def _permit_admin() -> None:
    return None


async def _ensure_test_database() -> None:
    url = make_url(os.environ["DATABASE_URL"])
    admin_engine = create_async_engine(
        url.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with admin_engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DB_NAME},
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        await admin_engine.dispose()


@pytest.fixture(autouse=True)
async def reset_schema(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    await _ensure_test_database()
    skip_create = request.node.get_closest_marker("migration") is not None
    if not skip_create:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[require_admin] = _permit_admin
    yield client


@dataclass(frozen=True, slots=True)
class BearerAuth:
    """Logged-in user for contract tests: token, headers, user_id, role."""

    token: str
    user_id: int
    role: UserRole
    email: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


async def _login_role(
    client: AsyncClient,
    role: UserRole,
    *,
    email: str | None = None,
    password: str = "secret",
) -> BearerAuth:
    email = email or f"{role.value}@fixture.test"
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
    async with SessionLocal() as session:
        user = User(
            email=email,
            password_hash=password_hash,
            full_name=f"{role.value.title()} Fixture",
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id
    response = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return BearerAuth(token=token, user_id=user_id, role=role, email=email)


@pytest.fixture
async def employee_auth(client: AsyncClient) -> BearerAuth:
    """Bearer for role=employee (Pyagay stage 2 shared fixture)."""
    return await _login_role(client, UserRole.EMPLOYEE)


@pytest.fixture
async def procurement_auth(client: AsyncClient) -> BearerAuth:
    """Bearer for role=procurement."""
    return await _login_role(client, UserRole.PROCUREMENT)


@pytest.fixture
async def admin_auth(client: AsyncClient) -> BearerAuth:
    """Bearer for role=admin."""
    return await _login_role(client, UserRole.ADMIN)


@pytest.fixture
async def employee_headers(employee_auth: BearerAuth) -> dict[str, str]:
    return employee_auth.headers


@pytest.fixture
async def procurement_headers(procurement_auth: BearerAuth) -> dict[str, str]:
    return procurement_auth.headers


@pytest.fixture
async def admin_headers(admin_auth: BearerAuth) -> dict[str, str]:
    return admin_auth.headers
