"""HTTP contract tests for POST /api/orders/{date}/cutoff (no network)."""

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.catalog.models import Dish
from app.db import SessionLocal
from app.orders.models import OfficeOrder, OfficeOrderItem
from app.planning.models import MealPlan
from app.providers import MealtyError, NormalizedDish, parse_html
from app.users.models import User, UserRole

FAR_FUTURE = date.today() + timedelta(days=30)


class _FailingProvider:
    source = "mealty"

    async def fetch_catalog(self) -> list[NormalizedDish]:
        raise MealtyError("Mealty request failed")


def _path(day: date) -> str:
    return f"/api/orders/{day.isoformat()}/cutoff"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _token(
    client: AsyncClient, role: UserRole, *, email: str | None = None
) -> tuple[str, int]:
    email = email or f"{role.value}@cutoff.test"
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    async with SessionLocal() as session:
        user = User(
            email=email,
            password_hash=password_hash,
            full_name="Cutoff Test",
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id
    response = await client.post(
        "/api/auth/login",
        json={"email": email, "password": "secret"},
    )
    assert response.status_code == 200
    return response.json()["access_token"], user_id


async def _add_dish(external_id: str, **overrides: object) -> int:
    values: dict[str, object] = {
        "source": "mealty",
        "external_id": external_id,
        "seller_product_id": None,
        "name": f"Блюдо {external_id}",
        "subtitle": "",
        "description": None,
        "category": "main_dish",
        "price_kopecks": 41000,
        "old_price_kopecks": None,
        "weight_g": 300,
        "proteins": None,
        "fats": None,
        "carbs": None,
        "calories": None,
        "image_url": None,
        "available": True,
    }
    values.update(overrides)
    async with SessionLocal() as session:
        dish = Dish(**values)
        session.add(dish)
        await session.commit()
        await session.refresh(dish)
        return dish.id


async def _office_order_count() -> int:
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(OfficeOrder))
    return int(count or 0)


async def _plan_count_for(user_id: int) -> int:
    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(MealPlan)
            .where(MealPlan.user_id == user_id)
        )
    return int(count or 0)


async def _employee_plan(
    client: AsyncClient,
    day: date,
    items: list[dict[str, int]],
) -> str:
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    saved = await client.put(
        f"/api/plans/{day.isoformat()}",
        headers=_auth(token),
        json={"items": items},
    )
    assert saved.status_code == 200, saved.text
    return token


async def test_cutoff_requires_token(client: AsyncClient) -> None:
    response = await client.post(_path(FAR_FUTURE))
    assert response.status_code == 401
    assert await _office_order_count() == 0


@pytest.mark.parametrize("role", [UserRole.PROCUREMENT, UserRole.ADMIN])
async def test_cutoff_http_fixture_prices_and_excludes_removed_dish(
    client: AsyncClient, role: UserRole
) -> None:
    parsed = parse_html(
        (Path(__file__).parent / "fixtures" / "mealty_catalog.html").read_text(
            encoding="utf-8"
        )
    )
    kept = await _add_dish(parsed[0].external_id, price_kopecks=41000)
    dropped = await _add_dish(parsed[1].external_id, price_kopecks=30000)
    employee = await _employee_plan(
        client,
        FAR_FUTURE,
        [{"dish_id": kept, "qty": 2}, {"dish_id": dropped, "qty": 1}],
    )

    class ChangedFixtureProvider:
        source = "mealty"

        async def fetch_catalog(self) -> list[NormalizedDish]:
            return [parsed[0].model_copy(update={"price_kopecks": 42500})]

    token, _ = await _token(client, role)
    with patch("app.catalog.service.MealtyProvider", ChangedFixtureProvider):
        closed = await client.post(_path(FAR_FUTURE), headers=_auth(token))
        assert closed.status_code == 200
        assert closed.json()["sync"] == "ok"
        assert closed.json()["items_unavailable"] == 1
        assert closed.json()["plans_closed"] == 1
        repeated = await client.post(_path(FAR_FUTURE), headers=_auth(token))
        assert repeated.status_code == 200
        assert repeated.json()["already_closed"] is True
        assert repeated.json()["plans_closed"] == 0
    plan = (
        await client.get(
            f"/api/plans/{FAR_FUTURE.isoformat()}", headers=_auth(employee)
        )
    ).json()
    assert plan["status"] == "included_in_order"
    assert plan["editable"] is False
    assert plan["planned_total_kopecks"] == 112000
    assert plan["actual_total_kopecks"] == 85000
    items = {item["dish_id"]: item for item in plan["items"]}
    assert items[kept]["planned_price_kopecks"] == 41000
    assert items[kept]["actual_price_kopecks"] == 42500
    assert items[dropped]["unavailable"] is True
    assert items[dropped]["actual_price_kopecks"] is None
    async with SessionLocal() as session:
        rows = list((await session.scalars(select(OfficeOrderItem))).all())
        assert [
            (row.dish_id, row.qty, row.unit_price_kopecks, row.line_total_kopecks)
            for row in rows
        ] == [(kept, 2, 42500, 85000)]


async def test_new_employee_cannot_create_plan_after_manual_cutoff(
    client: AsyncClient,
) -> None:
    dish = await _add_dish("late-plan", price_kopecks=41000)
    await _employee_plan(client, FAR_FUTURE, [{"dish_id": dish, "qty": 1}])
    token, _ = await _token(client, UserRole.PROCUREMENT)
    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        closed = await client.post(_path(FAR_FUTURE), headers=_auth(token))
    assert closed.status_code == 200
    employee, employee_id = await _token(
        client, UserRole.EMPLOYEE, email="late@cutoff.test"
    )
    path = f"/api/plans/{FAR_FUTURE.isoformat()}"
    listed = await client.get(path, headers=_auth(employee))
    assert listed.status_code == 200
    body = listed.json()
    assert body["id"] is None
    assert body["status"] == "draft"
    assert body["items"] == []
    assert body["editable"] is False
    saved = await client.put(
        path, headers=_auth(employee), json={"items": [{"dish_id": dish, "qty": 1}]}
    )
    assert saved.status_code == 403
    assert saved.json()["detail"] == "Cutoff passed"
    assert await _plan_count_for(employee_id) == 0
    again = await client.get(path, headers=_auth(employee))
    assert again.status_code == 200
    assert again.json()["id"] is None
    assert again.json()["editable"] is False


async def test_cutoff_forbidden_for_employee(client: AsyncClient) -> None:
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    response = await client.post(_path(FAR_FUTURE), headers=_auth(token))
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"
    assert await _office_order_count() == 0


async def test_cutoff_invalid_date_is_422(client: AsyncClient) -> None:
    token, _user_id = await _token(client, UserRole.PROCUREMENT)
    response = await client.post(
        "/api/orders/not-a-date/cutoff",
        headers=_auth(token),
    )
    assert response.status_code == 422


async def test_cutoff_empty_day_is_400(client: AsyncClient) -> None:
    token, _user_id = await _token(client, UserRole.PROCUREMENT)
    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        response = await client.post(_path(FAR_FUTURE), headers=_auth(token))
    assert response.status_code == 400
    assert response.json()["detail"] == "Empty day"
    assert await _office_order_count() == 0


async def test_cutoff_closes_early_and_blocks_plan_edits(
    client: AsyncClient,
) -> None:
    # Deadline for FAR_FUTURE is far away: closing early must still work.
    kept = await _add_dish("9001", price_kopecks=41000)
    dropped = await _add_dish("9002", price_kopecks=30000)
    employee_token = await _employee_plan(
        client,
        FAR_FUTURE,
        [{"dish_id": kept, "qty": 2}, {"dish_id": dropped, "qty": 1}],
    )
    async with SessionLocal() as session:
        dish = await session.get(Dish, dropped)
        assert dish is not None
        dish.available = False
        await session.commit()

    token, _user_id = await _token(client, UserRole.PROCUREMENT)
    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        response = await client.post(_path(FAR_FUTURE), headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "delivery_date": FAR_FUTURE.isoformat(),
        "status": "locked",
        "already_closed": False,
        "sync": "skipped",
        "plans_closed": 1,
        "items_unavailable": 1,
    }
    assert await _office_order_count() == 1

    denied = await client.put(
        f"/api/plans/{FAR_FUTURE.isoformat()}",
        headers=_auth(employee_token),
        json={"items": [{"dish_id": kept, "qty": 1}]},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Cutoff passed"


async def test_cutoff_idempotent_second_call(client: AsyncClient) -> None:
    dish_id = await _add_dish("9003")
    await _employee_plan(client, FAR_FUTURE, [{"dish_id": dish_id, "qty": 1}])
    token, _user_id = await _token(client, UserRole.PROCUREMENT)

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        first = await client.post(_path(FAR_FUTURE), headers=_auth(token))
        second = await client.post(_path(FAR_FUTURE), headers=_auth(token))

    assert first.status_code == 200
    assert first.json()["already_closed"] is False
    assert second.status_code == 200
    assert second.json() == {
        "delivery_date": FAR_FUTURE.isoformat(),
        "status": "locked",
        "already_closed": True,
        "sync": "skipped",
        "plans_closed": 0,
        "items_unavailable": 0,
    }
    assert await _office_order_count() == 1
