"""Shared pytest fixtures. Env is set before app imports."""

import os
from collections.abc import AsyncIterator

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
from app.db import Base, engine
from app.main import app
from app.users.models import Department  # noqa: F401


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
