"""Pyagay stage-2 contract tests against Bondar plans/cutoff APIs.

Uses shared Bearer fixtures from conftest (employee / procurement / admin).
`POST /place` is stage-3 Bondar work — skipped until the route exists.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import bcrypt
import pytest
from httpx import AsyncClient

from app.catalog.models import Dish
from app.db import SessionLocal
from app.main import app
from app.providers import MealtyError, NormalizedDish
from app.users.models import User, UserRole
from tests.conftest import BearerAuth

OPEN_DAY = date.today() + timedelta(days=30)
CLOSED_DAY = date(2020, 1, 15)


class _FailingProvider:
    source = "mealty"

    async def fetch_catalog(self) -> list[NormalizedDish]:
        raise MealtyError("Mealty request failed")


def _plans_path(day: date, user_id: int | None = None) -> str:
    path = f"/api/plans/{day.isoformat()}"
    if user_id is not None:
        return f"{path}?user_id={user_id}"
    return path


def _cutoff_path(day: date) -> str:
    return f"/api/orders/{day.isoformat()}/cutoff"


def _place_path(day: date) -> str:
    return f"/api/orders/{day.isoformat()}/place"


def _has_place_route() -> bool:
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        methods = getattr(route, "methods", set()) or set()
        if path.endswith("/place") and "POST" in methods:
            return True
    return False


async def _add_dish(external_id: str = "c-875", **overrides: object) -> int:
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


async def _other_employee(client: AsyncClient, email: str) -> BearerAuth:
    """Second employee (fixtures already seeded one role each)."""
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    async with SessionLocal() as session:
        user = User(
            email=email,
            password_hash=password_hash,
            full_name="Other Employee",
            role=UserRole.EMPLOYEE,
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
    assert response.status_code == 200, response.text
    return BearerAuth(
        token=response.json()["access_token"],
        user_id=user_id,
        role=UserRole.EMPLOYEE,
        email=email,
    )


# --- 401 without JWT ---------------------------------------------------------


async def test_plans_get_requires_bearer(client: AsyncClient) -> None:
    response = await client.get(_plans_path(OPEN_DAY))
    assert response.status_code == 401


async def test_plans_put_requires_bearer(client: AsyncClient) -> None:
    response = await client.put(_plans_path(OPEN_DAY), json={"items": []})
    assert response.status_code == 401


async def test_cutoff_requires_bearer(client: AsyncClient) -> None:
    response = await client.post(_cutoff_path(OPEN_DAY))
    assert response.status_code == 401


# --- 403 foreign plan / wrong role -------------------------------------------


async def test_employee_put_only_touches_own_plan(
    client: AsyncClient,
    employee_auth: BearerAuth,
    procurement_auth: BearerAuth,
) -> None:
    """PUT /plans has no user_id — always the caller's plan (чужой план не пишется)."""
    other = await _other_employee(client, "other-employee@contract.test")
    dish_id = await _add_dish("c-foreign")
    # peer seeds their own plan first
    peer_put = await client.put(
        _plans_path(OPEN_DAY),
        headers=other.headers,
        json={"items": [{"dish_id": dish_id, "qty": 3}]},
    )
    assert peer_put.status_code == 200, peer_put.text

    own = await client.put(
        _plans_path(OPEN_DAY),
        headers=employee_auth.headers,
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert own.status_code == 200, own.text
    assert own.json()["user_id"] == employee_auth.user_id

    peer_view = await client.get(
        _plans_path(OPEN_DAY, user_id=other.user_id),
        headers=procurement_auth.headers,
    )
    assert peer_view.status_code == 200
    assert peer_view.json()["user_id"] == other.user_id
    assert peer_view.json()["items"][0]["qty"] == 3


async def test_procurement_cannot_put_plan(
    client: AsyncClient,
    procurement_auth: BearerAuth,
) -> None:
    dish_id = await _add_dish("c-proc-put")
    denied = await client.put(
        _plans_path(OPEN_DAY),
        headers=procurement_auth.headers,
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Forbidden"


async def test_admin_cannot_put_plan(
    client: AsyncClient,
    admin_auth: BearerAuth,
) -> None:
    dish_id = await _add_dish("c-admin-put")
    denied = await client.put(
        _plans_path(OPEN_DAY),
        headers=admin_auth.headers,
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Forbidden"


async def test_employee_cannot_read_foreign_plan(
    client: AsyncClient,
    employee_auth: BearerAuth,
) -> None:
    other = await _other_employee(client, "peer@contract.test")
    denied = await client.get(
        _plans_path(OPEN_DAY, user_id=other.user_id),
        headers=employee_auth.headers,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Forbidden"


# --- 403 after cutoff --------------------------------------------------------


async def test_put_after_natural_cutoff_is_403(
    client: AsyncClient,
    employee_auth: BearerAuth,
) -> None:
    dish_id = await _add_dish("c-closed")
    denied = await client.put(
        _plans_path(CLOSED_DAY),
        headers=employee_auth.headers,
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Cutoff passed"


async def test_put_after_manual_cutoff_is_403(
    client: AsyncClient,
    employee_auth: BearerAuth,
    procurement_auth: BearerAuth,
) -> None:
    dish_id = await _add_dish("c-manual-cut")
    saved = await client.put(
        _plans_path(OPEN_DAY),
        headers=employee_auth.headers,
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert saved.status_code == 200, saved.text

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        closed = await client.post(
            _cutoff_path(OPEN_DAY),
            headers=procurement_auth.headers,
        )
    assert closed.status_code == 200, closed.text
    assert closed.json()["already_closed"] is False

    denied = await client.put(
        _plans_path(OPEN_DAY),
        headers=employee_auth.headers,
        json={"items": [{"dish_id": dish_id, "qty": 2}]},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Cutoff passed"


# --- cutoff idempotency ------------------------------------------------------


async def test_cutoff_is_idempotent(
    client: AsyncClient,
    employee_auth: BearerAuth,
    procurement_auth: BearerAuth,
) -> None:
    dish_id = await _add_dish("c-idem")
    saved = await client.put(
        _plans_path(OPEN_DAY),
        headers=employee_auth.headers,
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert saved.status_code == 200, saved.text

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        first = await client.post(
            _cutoff_path(OPEN_DAY),
            headers=procurement_auth.headers,
        )
        second = await client.post(
            _cutoff_path(OPEN_DAY),
            headers=procurement_auth.headers,
        )

    assert first.status_code == 200
    assert first.json()["already_closed"] is False
    assert second.status_code == 200
    assert second.json()["already_closed"] is True
    assert second.json()["status"] == "locked"
    assert second.json()["plans_closed"] == 0
    assert second.json()["sync"] == "skipped"


async def test_employee_cannot_cutoff(
    client: AsyncClient,
    employee_auth: BearerAuth,
) -> None:
    denied = await client.post(
        _cutoff_path(OPEN_DAY),
        headers=employee_auth.headers,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Forbidden"


# --- place (stage 3 Bondar): skip until route lands --------------------------


@pytest.mark.skipif(
    not _has_place_route(),
    reason="POST /api/orders/{date}/place not landed yet (Bondar stage 3)",
)
async def test_place_requires_bearer(client: AsyncClient) -> None:
    response = await client.post(_place_path(OPEN_DAY))
    assert response.status_code == 401


@pytest.mark.skipif(
    not _has_place_route(),
    reason="POST /api/orders/{date}/place not landed yet (Bondar stage 3)",
)
async def test_place_forbidden_while_collecting(
    client: AsyncClient,
    procurement_auth: BearerAuth,
) -> None:
    """No office_order yet → still collecting → 403."""
    denied = await client.post(
        _place_path(OPEN_DAY),
        headers=procurement_auth.headers,
    )
    assert denied.status_code == 403


@pytest.mark.skipif(
    not _has_place_route(),
    reason="POST /api/orders/{date}/place not landed yet (Bondar stage 3)",
)
async def test_place_is_idempotent(
    client: AsyncClient,
    employee_auth: BearerAuth,
    procurement_auth: BearerAuth,
) -> None:
    dish_id = await _add_dish("c-place")
    saved = await client.put(
        _plans_path(OPEN_DAY),
        headers=employee_auth.headers,
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert saved.status_code == 200, saved.text

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        cut = await client.post(
            _cutoff_path(OPEN_DAY),
            headers=procurement_auth.headers,
        )
    assert cut.status_code == 200, cut.text

    first = await client.post(_place_path(OPEN_DAY), headers=procurement_auth.headers)
    second = await client.post(_place_path(OPEN_DAY), headers=procurement_auth.headers)
    assert first.status_code == 200
    assert second.status_code == 200
