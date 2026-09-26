from pathlib import Path
from unittest.mock import patch

import bcrypt
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import func, select

from app.catalog.models import Dish, PriceHistory
from app.db import SessionLocal
from app.providers import MealtyError, NormalizedDish, parse_html
from app.users.models import User, UserRole

FIXTURE = Path(__file__).parent / "fixtures" / "mealty_catalog.html"


def _parsed_fixture() -> list[NormalizedDish]:
    return parse_html(FIXTURE.read_text(encoding="utf-8"))


async def _create_user(role: UserRole) -> str:
    email = f"{role.value}@test.local"
    password_hash = bcrypt.hashpw(
        b"secret",
        bcrypt.gensalt(),
    ).decode("utf-8")
    async with SessionLocal() as session:
        session.add(
            User(
                email=email,
                password_hash=password_hash,
                full_name="Test User",
                role=role,
                is_active=True,
            )
        )
        await session.commit()
    return email


async def _token(client: AsyncClient, role: UserRole) -> str:
    email = await _create_user(role)
    response = await client.post(
        "/api/auth/login",
        json={"email": email, "password": "secret"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _add_dish(**overrides: object) -> None:
    values: dict[str, object] = {
        "source": "mealty",
        "external_id": "1",
        "seller_product_id": "1001",
        "name": "Блюдо",
        "subtitle": "заметка",
        "description": None,
        "category": "main_dish",
        "price_kopecks": 10000,
        "old_price_kopecks": None,
        "weight_g": 300,
        "proteins": 8.1,
        "fats": 12.0,
        "carbs": 42.0,
        "calories": 310.0,
        "image_url": "https://www.mealty.ru/upload/example.jpg",
        "available": True,
    }
    values.update(overrides)
    async with SessionLocal() as session:
        session.add(Dish(**values))
        await session.commit()


async def _dish_count() -> int:
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(Dish))
    return int(count or 0)


async def _history_count() -> int:
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(PriceHistory))
    return int(count or 0)


class _StubProvider:
    source = "mealty"
    fetches = 0

    async def fetch_catalog(self) -> list[NormalizedDish]:
        type(self).fetches += 1
        return _parsed_fixture()


class _FailingProvider:
    source = "mealty"
    fetches = 0

    async def fetch_catalog(self) -> list[NormalizedDish]:
        type(self).fetches += 1
        raise MealtyError("Mealty request failed")


async def test_catalog_requires_token(client: AsyncClient) -> None:
    response = await client.get("/api/catalog")
    assert response.status_code == 401
    assert "detail" in response.json()


async def test_employee_reads_catalog(client: AsyncClient) -> None:
    await _add_dish(external_id="875", name="Картофельные ньокки", price_kopecks=41000)
    token = await _token(client, UserRole.EMPLOYEE)
    response = await client.get("/api/catalog", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    dish = body[0]
    assert dish["external_id"] == "875"
    assert dish["price_kopecks"] == 41000
    assert isinstance(dish["price_kopecks"], int)
    assert dish["proteins"] == 8.1
    assert isinstance(dish["proteins"], float)
    assert dish["available"] is True
    assert set(dish) == {
        "id",
        "source",
        "external_id",
        "seller_product_id",
        "name",
        "subtitle",
        "description",
        "category",
        "price_kopecks",
        "old_price_kopecks",
        "weight_g",
        "proteins",
        "fats",
        "carbs",
        "calories",
        "image_url",
        "available",
    }


async def test_empty_catalog_returns_empty_list(client: AsyncClient) -> None:
    token = await _token(client, UserRole.EMPLOYEE)
    response = await client.get("/api/catalog", headers=_auth(token))
    assert response.status_code == 200
    assert response.json() == []


async def test_default_hides_unavailable(client: AsyncClient) -> None:
    await _add_dish(external_id="1", name="В меню", available=True)
    await _add_dish(external_id="2", name="Снято", available=False, price_kopecks=22200)
    token = await _token(client, UserRole.EMPLOYEE)
    response = await client.get("/api/catalog", headers=_auth(token))
    assert response.status_code == 200
    names = [dish["name"] for dish in response.json()]
    assert names == ["В меню"]


async def test_available_only_false_returns_last_card(client: AsyncClient) -> None:
    await _add_dish(external_id="2", name="Снято", available=False, price_kopecks=22200)
    token = await _token(client, UserRole.EMPLOYEE)
    response = await client.get(
        "/api/catalog",
        headers=_auth(token),
        params={"available_only": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["available"] is False
    assert body[0]["price_kopecks"] == 22200


async def test_category_and_name_filters(client: AsyncClient) -> None:
    await _add_dish(
        external_id="875",
        name="Картофельные ньокки",
        category="main_dish",
        available=True,
    )
    await _add_dish(
        external_id="2",
        name="Ньокки в салате",
        category="salad",
        available=True,
    )
    await _add_dish(
        external_id="3",
        name="Скрытые ньокки",
        category="main_dish",
        available=False,
    )
    token = await _token(client, UserRole.EMPLOYEE)
    response = await client.get(
        "/api/catalog",
        headers=_auth(token),
        params={"category": "main_dish", "q": "НЬОККИ"},
    )
    assert response.status_code == 200
    body = response.json()
    assert [dish["external_id"] for dish in body] == ["875"]


async def test_procurement_syncs_fixture(client: AsyncClient) -> None:
    _StubProvider.fetches = 0
    token = await _token(client, UserRole.PROCUREMENT)
    with patch("app.catalog.router.MealtyProvider", _StubProvider):
        response = await client.post("/api/catalog/sync", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    snapshot = _parsed_fixture()
    assert body["upserted"] == len(snapshot)
    assert body["unavailable"] == 0
    assert "+03:00" in body["recorded_at"]
    assert _StubProvider.fetches == 1
    assert await _dish_count() == len(snapshot)


async def test_employee_cannot_sync(client: AsyncClient) -> None:
    _StubProvider.fetches = 0
    token = await _token(client, UserRole.EMPLOYEE)
    with patch("app.catalog.router.MealtyProvider", _StubProvider):
        response = await client.post("/api/catalog/sync", headers=_auth(token))
    assert response.status_code == 403
    assert "detail" in response.json()
    assert _StubProvider.fetches == 0
    assert await _dish_count() == 0


async def test_mealty_error_leaves_rows_unchanged(client: AsyncClient) -> None:
    await _add_dish(
        external_id="875",
        name="Картофельные ньокки",
        price_kopecks=41000,
        available=True,
    )
    token = await _token(client, UserRole.PROCUREMENT)
    with patch("app.catalog.router.MealtyProvider", _FailingProvider):
        response = await client.post("/api/catalog/sync", headers=_auth(token))
    assert response.status_code == 502
    assert response.json()["detail"] == "Mealty request failed"
    async with SessionLocal() as session:
        row = await session.scalar(select(Dish).where(Dish.external_id == "875"))
        assert row is not None
        assert row.available is True
        assert row.price_kopecks == 41000
    assert await _history_count() == 0


async def _deny_quota() -> None:
    raise HTTPException(status_code=429, detail="Sync quota exceeded")


async def test_quota_refusal_skips_mealty(client: AsyncClient) -> None:
    _StubProvider.fetches = 0
    token = await _token(client, UserRole.PROCUREMENT)
    with (
        patch("app.catalog.router.assert_catalog_sync_allowed", _deny_quota),
        patch("app.catalog.router.MealtyProvider", _StubProvider),
    ):
        response = await client.post("/api/catalog/sync", headers=_auth(token))
    assert response.status_code == 429
    assert response.json()["detail"] == "Sync quota exceeded"
    assert _StubProvider.fetches == 0
    assert await _dish_count() == 0
