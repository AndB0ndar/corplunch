import asyncio

from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.users.models import Settings
from app.users.settings_service import SETTINGS_ROW_ID, get_or_create_settings


async def test_settings_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/admin/settings")
    assert response.status_code == 401


async def test_get_settings_returns_defaults(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/api/admin/settings")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "cutoff_time": "16:00",
        "timezone": "Europe/Moscow",
        "mealty_city": "Москва",
        "daily_limit_kopecks": None,
        "catalog_sync_per_day": 2,
    }

    async with SessionLocal() as session:
        row = await session.get(Settings, SETTINGS_ROW_ID)
        assert row is not None
        assert row.cutoff_time == "16:00"


async def test_put_settings_full_replace(admin_client: AsyncClient) -> None:
    response = await admin_client.put(
        "/api/admin/settings",
        json={
            "cutoff_time": "15:30",
            "timezone": "Europe/Moscow",
            "mealty_city": "Санкт-Петербург",
            "daily_limit_kopecks": 50000,
            "catalog_sync_per_day": 5,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cutoff_time"] == "15:30"
    assert body["mealty_city"] == "Санкт-Петербург"
    assert body["daily_limit_kopecks"] == 50000
    assert body["catalog_sync_per_day"] == 5

    again = await admin_client.get("/api/admin/settings")
    assert again.status_code == 200
    assert again.json() == body


async def test_put_settings_rejects_bad_cutoff(admin_client: AsyncClient) -> None:
    response = await admin_client.put(
        "/api/admin/settings",
        json={
            "cutoff_time": "25:00",
            "timezone": "Europe/Moscow",
            "mealty_city": "Москва",
            "daily_limit_kopecks": None,
            "catalog_sync_per_day": 2,
        },
    )
    assert response.status_code == 422


async def test_put_settings_rejects_unknown_timezone(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.put(
        "/api/admin/settings",
        json={
            "cutoff_time": "16:00",
            "timezone": "Not/AZone",
            "mealty_city": "Москва",
            "daily_limit_kopecks": None,
            "catalog_sync_per_day": 2,
        },
    )
    assert response.status_code == 422

async def test_concurrent_get_or_create_settings_creates_one_row() -> None:
    """QA-CUTOFF-02: two empty-DB creators must not raise settings_pkey."""

    async def _one() -> int:
        async with SessionLocal() as session:
            row = await get_or_create_settings(session)
            await session.commit()
            return row.id

    first_id, second_id = await asyncio.gather(_one(), _one())
    assert first_id == SETTINGS_ROW_ID
    assert second_id == SETTINGS_ROW_ID

    async with SessionLocal() as session:
        rows = list((await session.scalars(select(Settings))).all())
    assert len(rows) == 1
    assert rows[0].id == SETTINGS_ROW_ID

