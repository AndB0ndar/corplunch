from unittest.mock import patch

import bcrypt
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.providers import NormalizedDish
from app.users.models import CatalogSyncRun, User, UserRole
from app.users.quota import assert_plan_within_limit
from app.users.settings_service import get_or_create_settings


class _StubProvider:
    source = "mealty"
    fetches = 0

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def fetch_catalog(self) -> list[NormalizedDish]:
        type(self).fetches += 1
        return [
            NormalizedDish(
                external_id="875",
                seller_product_id="100875",
                name="Ньокки",
                subtitle="note",
                description=None,
                category="main_dish",
                price_kopecks=41000,
                old_price_kopecks=None,
                weight_g=300,
                proteins=8.1,
                fats=12.0,
                carbs=42.0,
                calories=310.0,
                image_url="https://www.mealty.ru/upload/example.jpg",
                available=True,
            )
        ]


async def _create_user(role: UserRole, **overrides: object) -> User:
    email = f"{role.value}@quota.test"
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    values: dict[str, object] = {
        "email": email,
        "password_hash": password_hash,
        "full_name": "Quota User",
        "role": role,
        "is_active": True,
        "daily_limit_kopecks": None,
    }
    values.update(overrides)
    async with SessionLocal() as session:
        user = User(**values)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _token(client: AsyncClient, role: UserRole) -> str:
    await _create_user(role)
    response = await client.post(
        "/api/auth/login",
        json={"email": f"{role.value}@quota.test", "password": "secret"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _run_count() -> int:
    async with SessionLocal() as session:
        return int(
            await session.scalar(select(func.count()).select_from(CatalogSyncRun))
            or 0
        )


async def test_sync_quota_allows_then_blocks(client: AsyncClient) -> None:
    _StubProvider.fetches = 0
    token = await _token(client, UserRole.PROCUREMENT)

    async with SessionLocal() as session:
        settings = await get_or_create_settings(session)
        settings.catalog_sync_per_day = 2
        await session.commit()

    with patch("app.catalog.service.MealtyProvider", _StubProvider):
        first = await client.post("/api/catalog/sync", headers=_auth(token))
        second = await client.post("/api/catalog/sync", headers=_auth(token))
        third = await client.post("/api/catalog/sync", headers=_auth(token))

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["detail"] == "Sync quota exceeded"
    assert _StubProvider.fetches == 2
    assert await _run_count() == 2


async def test_plan_limit_uses_personal_then_system() -> None:
    async with SessionLocal() as session:
        settings = await get_or_create_settings(session)
        settings.daily_limit_kopecks = 10000
        await session.commit()

    personal = await _create_user(
        UserRole.EMPLOYEE,
        email="personal@quota.test",
        daily_limit_kopecks=5000,
    )
    system = await _create_user(
        UserRole.EMPLOYEE,
        email="system@quota.test",
        daily_limit_kopecks=None,
    )

    async with SessionLocal() as session:
        await assert_plan_within_limit(
            session,
            user=personal,
            total_kopecks=5000,
        )
        with pytest.raises(HTTPException) as personal_exc:
            await assert_plan_within_limit(
                session,
                user=personal,
                total_kopecks=5001,
            )
        assert personal_exc.value.status_code == 422
        assert personal_exc.value.detail == "Daily limit exceeded"

        await assert_plan_within_limit(
            session,
            user=system,
            total_kopecks=10000,
        )
        with pytest.raises(HTTPException) as system_exc:
            await assert_plan_within_limit(
                session,
                user=system,
                total_kopecks=10001,
            )
        assert system_exc.value.status_code == 422


async def test_plan_limit_skipped_when_no_limits() -> None:
    user = await _create_user(
        UserRole.EMPLOYEE,
        email="nolimit@quota.test",
        daily_limit_kopecks=None,
    )
    async with SessionLocal() as session:
        settings = await get_or_create_settings(session)
        settings.daily_limit_kopecks = None
        await session.commit()
        await assert_plan_within_limit(
            session,
            user=user,
            total_kopecks=999999,
        )
