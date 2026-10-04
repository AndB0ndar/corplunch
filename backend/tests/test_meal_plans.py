from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.catalog.models import Dish
from app.db import SessionLocal
from app.planning.models import MealPlan, PlanItem, PlanStatus
from app.planning.service import ActualPriceStamp, apply_actual_prices
from app.users.models import User, UserRole

OPEN_DAY = date.today() + timedelta(days=30)
CLOSED_DAY = date(2020, 1, 15)
MOSCOW = ZoneInfo("Europe/Moscow")


def _path(day: date, user_id: int | None = None) -> str:
    path = f"/api/plans/{day.isoformat()}"
    if user_id is not None:
        return f"{path}?user_id={user_id}"
    return path


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_user(
    role: UserRole,
    email: str | None = None,
    *,
    daily_limit_kopecks: int | None = None,
) -> tuple[str, int]:
    email = email or f"{role.value}@test.local"
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    async with SessionLocal() as session:
        user = User(
            email=email,
            password_hash=password_hash,
            full_name="Test User",
            role=role,
            is_active=True,
            daily_limit_kopecks=daily_limit_kopecks,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return email, user.id


async def _token(
    client: AsyncClient,
    role: UserRole,
    email: str | None = None,
    *,
    daily_limit_kopecks: int | None = None,
) -> tuple[str, int]:
    email, user_id = await _create_user(
        role,
        email,
        daily_limit_kopecks=daily_limit_kopecks,
    )
    response = await client.post(
        "/api/auth/login",
        json={"email": email, "password": "secret"},
    )
    assert response.status_code == 200
    return response.json()["access_token"], user_id


async def _add_dish(**overrides: object) -> int:
    values: dict[str, object] = {
        "source": "mealty",
        "external_id": "875",
        "seller_product_id": "1001",
        "name": "Картофельные ньокки с грибами",
        "subtitle": "заметка",
        "description": None,
        "category": "main_dish",
        "price_kopecks": 41000,
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
        dish = Dish(**values)
        session.add(dish)
        await session.commit()
        await session.refresh(dish)
        return dish.id


async def _set_dish(dish_id: int, **overrides: object) -> None:
    async with SessionLocal() as session:
        dish = await session.get(Dish, dish_id)
        assert dish is not None
        for key, value in overrides.items():
            setattr(dish, key, value)
        await session.commit()


async def _plan_count() -> int:
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(MealPlan))
    return int(count or 0)


async def _insert_plan(
    user_id: int,
    delivery: date,
    status: PlanStatus,
    items: list[tuple[int, int, int]] | None = None,
) -> int:
    async with SessionLocal() as session:
        plan = MealPlan(
            user_id=user_id,
            delivery_date=delivery,
            status=status,
        )
        session.add(plan)
        await session.flush()
        for dish_id, qty, price in items or []:
            session.add(
                PlanItem(
                    plan_id=plan.id,
                    dish_id=dish_id,
                    qty=qty,
                    planned_price_kopecks=price,
                    actual_price_kopecks=None,
                    unavailable=False,
                )
            )
        await session.commit()
        return plan.id


async def _freeze_plan_items(
    plan_id: int,
    facts: dict[int, tuple[int | None, bool]],
) -> None:
    async with SessionLocal() as session:
        items = list(
            await session.scalars(select(PlanItem).where(PlanItem.plan_id == plan_id))
        )
        assert {item.dish_id for item in items} == set(facts)
        for item in items:
            actual, unavailable = facts[item.dish_id]
            item.actual_price_kopecks = actual
            item.unavailable = unavailable
        await session.commit()


async def _stamp(delivery: date) -> ActualPriceStamp:
    async with SessionLocal() as session:
        return await apply_actual_prices(session, delivery)


async def _stored_plan(
    plan_id: int,
) -> tuple[PlanStatus, list[tuple[int, int, int, int | None, bool]]]:
    async with SessionLocal() as session:
        plan = await session.scalar(
            select(MealPlan)
            .where(MealPlan.id == plan_id)
            .options(selectinload(MealPlan.items))
        )
        assert plan is not None
        rows = [
            (
                item.dish_id,
                item.qty,
                item.planned_price_kopecks,
                item.actual_price_kopecks,
                item.unavailable,
            )
            for item in plan.items
        ]
        return plan.status, rows


async def test_plans_require_token(client: AsyncClient) -> None:
    missing = await client.get(_path(OPEN_DAY))
    assert missing.status_code == 401

    missing_put = await client.put(
        _path(OPEN_DAY),
        json={"items": [{"dish_id": 1, "qty": 0}]},
    )
    assert missing_put.status_code == 401
    assert await _plan_count() == 0


async def test_empty_get_does_not_insert(client: AsyncClient) -> None:
    token, user_id = await _token(client, UserRole.EMPLOYEE)
    response = await client.get(_path(OPEN_DAY), headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] is None
    assert body["user_id"] == user_id
    assert body["delivery_date"] == OPEN_DAY.isoformat()
    assert body["status"] == "draft"
    assert body["editable"] is True
    assert body["planned_total_kopecks"] == 0
    assert body["actual_total_kopecks"] is None
    assert body["items"] == []
    assert await _plan_count() == 0


async def test_invalid_date_is_422(client: AsyncClient) -> None:
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    response = await client.get("/api/plans/not-a-date", headers=_auth(token))
    assert response.status_code == 422


async def test_employee_can_pass_own_user_id(client: AsyncClient) -> None:
    token, user_id = await _token(client, UserRole.EMPLOYEE)
    response = await client.get(_path(OPEN_DAY, user_id), headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["user_id"] == user_id
    assert await _plan_count() == 0


async def test_employee_cannot_read_another_user(client: AsyncClient) -> None:
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    _other_token, other_id = await _token(
        client,
        UserRole.EMPLOYEE,
        email="employee2@test.local",
    )
    response = await client.get(_path(OPEN_DAY, other_id), headers=_auth(token))
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"

    unknown = await client.get(_path(OPEN_DAY, 999999), headers=_auth(token))
    assert unknown.status_code == 403
    assert unknown.json()["detail"] == "Forbidden"


@pytest.mark.parametrize("role", [UserRole.PROCUREMENT, UserRole.ADMIN])
async def test_procurement_and_admin_can_read_a_plan(
    client: AsyncClient,
    role: UserRole,
) -> None:
    dish_id = await _add_dish()
    employee_token, employee_id = await _token(client, UserRole.EMPLOYEE)
    saved = await client.put(
        _path(OPEN_DAY),
        headers=_auth(employee_token),
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert saved.status_code == 200

    token, _reader_id = await _token(client, role)
    response = await client.get(_path(OPEN_DAY, employee_id), headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["id"] == saved.json()["id"]
    assert response.json()["items"][0]["dish_id"] == dish_id


async def test_procurement_without_user_id_reads_own_plan(
    client: AsyncClient,
) -> None:
    token, user_id = await _token(client, UserRole.PROCUREMENT)
    response = await client.get(_path(OPEN_DAY), headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == user_id
    assert body["id"] is None
    assert await _plan_count() == 0


@pytest.mark.parametrize("role", [UserRole.PROCUREMENT, UserRole.ADMIN])
async def test_unknown_user_is_404(client: AsyncClient, role: UserRole) -> None:
    token, _user_id = await _token(client, role)
    response = await client.get(_path(OPEN_DAY, 999999), headers=_auth(token))
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"
    assert await _plan_count() == 0


async def test_exact_deadline_is_not_editable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed = datetime(2026, 10, 4, 16, 0, tzinfo=MOSCOW)
    monkeypatch.setattr("app.planning.service._now", lambda tz: fixed)
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    dish_id = await _add_dish()

    response = await client.get(_path(date(2026, 10, 5)), headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["editable"] is False

    denied = await client.put(
        _path(date(2026, 10, 5)),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Cutoff passed"
    assert await _plan_count() == 0


async def test_before_deadline_is_editable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed = datetime(2026, 10, 4, 15, 59, tzinfo=MOSCOW)
    monkeypatch.setattr("app.planning.service._now", lambda tz: fixed)
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    response = await client.get(_path(date(2026, 10, 5)), headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["editable"] is True


@pytest.mark.parametrize(
    "plan_status",
    [PlanStatus.LOCKED, PlanStatus.PRICED, PlanStatus.INCLUDED_IN_ORDER],
)
async def test_non_draft_plan_is_not_editable(
    client: AsyncClient,
    plan_status: PlanStatus,
) -> None:
    dish_id = await _add_dish(external_id=f"status-{plan_status.value}")
    token, user_id = await _token(
        client,
        UserRole.EMPLOYEE,
        email=f"{plan_status.value}@test.local",
    )
    await _insert_plan(
        user_id,
        OPEN_DAY,
        plan_status,
        items=[(dish_id, 1, 41000)],
    )

    response = await client.get(_path(OPEN_DAY), headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["editable"] is False
    assert response.json()["status"] == plan_status.value

    denied = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 2}]},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Cutoff passed"
    assert response.json()["items"][0]["qty"] == 1
    again = await client.get(_path(OPEN_DAY), headers=_auth(token))
    assert again.json()["items"][0]["qty"] == 1


async def test_put_creates_replaces_and_clears(client: AsyncClient) -> None:
    first_dish = await _add_dish(external_id="875", price_kopecks=41000)
    second_dish = await _add_dish(
        external_id="876",
        name="Суп",
        price_kopecks=15000,
    )
    token, user_id = await _token(client, UserRole.EMPLOYEE)

    created = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": first_dish, "qty": 2}]},
    )
    assert created.status_code == 200
    created_body = created.json()
    assert created_body["id"] is not None
    assert created_body["status"] == "draft"
    assert created_body["user_id"] == user_id
    assert created_body["planned_total_kopecks"] == 82000
    assert created_body["actual_total_kopecks"] is None
    assert created_body["items"] == [
        {
            "dish_id": first_dish,
            "name": "Картофельные ньокки с грибами",
            "qty": 2,
            "planned_price_kopecks": 41000,
            "actual_price_kopecks": None,
            "unavailable": False,
        }
    ]
    listed = await client.get(_path(OPEN_DAY), headers=_auth(token))
    assert listed.json() == created_body

    replaced = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": second_dish, "qty": 1}]},
    )
    assert replaced.status_code == 200
    replaced_body = replaced.json()
    assert replaced_body["id"] == created_body["id"]
    assert [item["dish_id"] for item in replaced_body["items"]] == [second_dish]
    assert replaced_body["planned_total_kopecks"] == 15000

    cleared = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": []},
    )
    assert cleared.status_code == 200
    cleared_body = cleared.json()
    assert cleared_body["id"] == created_body["id"]
    assert cleared_body["items"] == []
    assert cleared_body["planned_total_kopecks"] == 0
    assert cleared_body["actual_total_kopecks"] is None
    assert await _plan_count() == 1


async def test_catalog_price_is_snapshotted_until_next_put(
    client: AsyncClient,
) -> None:
    dish_id = await _add_dish(price_kopecks=41000)
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    created = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 2}]},
    )
    assert created.status_code == 200
    plan_id = created.json()["id"]

    await _set_dish(dish_id, price_kopecks=50000)
    listed = await client.get(_path(OPEN_DAY), headers=_auth(token))
    assert listed.json()["items"][0]["planned_price_kopecks"] == 41000
    assert listed.json()["planned_total_kopecks"] == 82000

    refreshed = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 2}]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["id"] == plan_id
    assert refreshed.json()["items"][0]["planned_price_kopecks"] == 50000
    assert refreshed.json()["planned_total_kopecks"] == 100000


@pytest.mark.parametrize("role", [UserRole.PROCUREMENT, UserRole.ADMIN])
async def test_non_employee_cannot_put(client: AsyncClient, role: UserRole) -> None:
    dish_id = await _add_dish()
    token, _user_id = await _token(client, role)
    denied = await client.put(
        _path(CLOSED_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Forbidden"
    assert await _plan_count() == 0

    invalid = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 0}]},
    )
    assert invalid.status_code == 403
    assert invalid.json()["detail"] == "Forbidden"


async def test_closed_day_put_is_cutoff(client: AsyncClient) -> None:
    dish_id = await _add_dish()
    token, user_id = await _token(client, UserRole.EMPLOYEE)
    plan_id = await _insert_plan(
        user_id,
        CLOSED_DAY,
        PlanStatus.DRAFT,
        items=[(dish_id, 1, 41000)],
    )

    denied = await client.put(
        _path(CLOSED_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 3}]},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Cutoff passed"

    listed = await client.get(_path(CLOSED_DAY), headers=_auth(token))
    assert listed.json()["id"] == plan_id
    assert listed.json()["editable"] is False
    assert listed.json()["items"][0]["qty"] == 1


async def test_qty_below_one_does_not_change_plan(client: AsyncClient) -> None:
    dish_id = await _add_dish()
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    created = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert created.status_code == 200

    denied = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 0}]},
    )
    assert denied.status_code == 422
    listed = await client.get(_path(OPEN_DAY), headers=_auth(token))
    assert listed.json()["items"][0]["qty"] == 1


async def test_duplicate_dish_is_422(client: AsyncClient) -> None:
    dish_id = await _add_dish()
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    denied = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={
            "items": [
                {"dish_id": dish_id, "qty": 1},
                {"dish_id": dish_id, "qty": 2},
            ]
        },
    )
    assert denied.status_code == 422
    assert await _plan_count() == 0


async def test_missing_dish_is_409(client: AsyncClient) -> None:
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    denied = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": 999999, "qty": 1}]},
    )
    assert denied.status_code == 409
    assert denied.json()["detail"] == "Dish not found"
    assert await _plan_count() == 0


async def test_unavailable_dish_is_409(client: AsyncClient) -> None:
    dish_id = await _add_dish(available=False, price_kopecks=50000)
    token, _user_id = await _token(
        client,
        UserRole.EMPLOYEE,
        daily_limit_kopecks=1000,
    )
    denied = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert denied.status_code == 409
    assert denied.json()["detail"] == "Dish unavailable"
    assert await _plan_count() == 0


async def test_stored_dish_stays_visible_after_it_becomes_unavailable(
    client: AsyncClient,
) -> None:
    dish_id = await _add_dish(available=True)
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    created = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert created.status_code == 200

    await _set_dish(dish_id, available=False)
    listed = await client.get(_path(OPEN_DAY), headers=_auth(token))
    assert listed.json()["items"][0]["unavailable"] is False

    denied = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert denied.status_code == 409
    assert denied.json()["detail"] == "Dish unavailable"
    again = await client.get(_path(OPEN_DAY), headers=_auth(token))
    assert again.json()["items"][0]["dish_id"] == dish_id
    assert again.json()["items"][0]["unavailable"] is False


async def test_missing_dish_is_reported_before_the_limit(
    client: AsyncClient,
) -> None:
    dish_id = await _add_dish(price_kopecks=50000)
    token, _user_id = await _token(
        client,
        UserRole.EMPLOYEE,
        daily_limit_kopecks=1000,
    )
    denied = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={
            "items": [
                {"dish_id": 999999, "qty": 1},
                {"dish_id": dish_id, "qty": 1},
            ]
        },
    )
    assert denied.status_code == 409
    assert denied.json()["detail"] == "Dish not found"
    assert await _plan_count() == 0


async def test_missing_dish_wins_over_unavailable(client: AsyncClient) -> None:
    unavailable_id = await _add_dish(external_id="1", available=False)
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    denied = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={
            "items": [
                {"dish_id": unavailable_id, "qty": 1},
                {"dish_id": unavailable_id + 1000, "qty": 1},
            ]
        },
    )
    assert denied.status_code == 409
    assert denied.json()["detail"] == "Dish not found"


async def test_over_limit_is_422(client: AsyncClient) -> None:
    dish_id = await _add_dish(price_kopecks=50000)
    token, _user_id = await _token(
        client,
        UserRole.EMPLOYEE,
        daily_limit_kopecks=1000,
    )
    denied = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert denied.status_code == 422
    assert denied.json()["detail"] == "Daily limit exceeded"
    assert await _plan_count() == 0


async def test_put_succeeds_when_no_limit_is_configured(client: AsyncClient) -> None:
    dish_id = await _add_dish(price_kopecks=9_000_000)
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    saved = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 3}]},
    )
    assert saved.status_code == 200
    assert saved.json()["planned_total_kopecks"] == 27_000_000


OTHER_DAY = OPEN_DAY + timedelta(days=1)


@pytest.mark.parametrize(
    ("catalog_price", "available", "actual", "unavailable", "priced", "removed"),
    [
        pytest.param(42500, True, 42500, False, 1, 0, id="price-up"),
        pytest.param(41000, True, 41000, False, 1, 0, id="price-unchanged"),
        pytest.param(39000, True, 39000, False, 1, 0, id="price-down"),
        pytest.param(50000, False, None, True, 0, 1, id="unavailable"),
    ],
)
async def test_stamp_sets_actual_price_or_unavailable(
    catalog_price: int,
    available: bool,
    actual: int | None,
    unavailable: bool,
    priced: int,
    removed: int,
) -> None:
    dish_id = await _add_dish(price_kopecks=41000)
    _email, user_id = await _create_user(UserRole.EMPLOYEE)
    plan_id = await _insert_plan(
        user_id,
        OPEN_DAY,
        PlanStatus.DRAFT,
        [(dish_id, 2, 41000)],
    )

    await _set_dish(dish_id, price_kopecks=catalog_price, available=available)
    stamp = await _stamp(OPEN_DAY)

    assert stamp == ActualPriceStamp(
        plans_stamped=1,
        items_priced=priced,
        items_unavailable=removed,
    )
    status, rows = await _stored_plan(plan_id)
    assert status == PlanStatus.PRICED
    assert rows == [(dish_id, 2, 41000, actual, unavailable)]


async def test_stamp_prices_empty_draft() -> None:
    _email, user_id = await _create_user(UserRole.EMPLOYEE)
    plan_id = await _insert_plan(user_id, OPEN_DAY, PlanStatus.DRAFT)

    stamp = await _stamp(OPEN_DAY)

    assert stamp == ActualPriceStamp(
        plans_stamped=1,
        items_priced=0,
        items_unavailable=0,
    )
    status, rows = await _stored_plan(plan_id)
    assert status == PlanStatus.PRICED
    assert rows == []


async def test_stamp_prices_locked_plan() -> None:
    dish_id = await _add_dish(price_kopecks=41000)
    _email, user_id = await _create_user(UserRole.EMPLOYEE)
    plan_id = await _insert_plan(
        user_id,
        OPEN_DAY,
        PlanStatus.LOCKED,
        [(dish_id, 1, 41000)],
    )

    await _set_dish(dish_id, price_kopecks=42500)
    stamp = await _stamp(OPEN_DAY)

    assert stamp.plans_stamped == 1
    status, rows = await _stored_plan(plan_id)
    assert status == PlanStatus.PRICED
    assert rows == [(dish_id, 1, 41000, 42500, False)]


async def test_stamp_leaves_other_delivery_date() -> None:
    dish_id = await _add_dish(price_kopecks=41000)
    _email, user_id = await _create_user(UserRole.EMPLOYEE)
    stamped_id = await _insert_plan(
        user_id,
        OPEN_DAY,
        PlanStatus.DRAFT,
        [(dish_id, 1, 41000)],
    )
    other_id = await _insert_plan(
        user_id,
        OTHER_DAY,
        PlanStatus.DRAFT,
        [(dish_id, 3, 41000)],
    )

    await _set_dish(dish_id, price_kopecks=42500)
    await _stamp(OPEN_DAY)

    stamped_status, stamped_rows = await _stored_plan(stamped_id)
    other_status, other_rows = await _stored_plan(other_id)
    assert stamped_status == PlanStatus.PRICED
    assert stamped_rows == [(dish_id, 1, 41000, 42500, False)]
    assert other_status == PlanStatus.DRAFT
    assert other_rows == [(dish_id, 3, 41000, None, False)]


async def test_stamp_does_not_insert_missing_plan() -> None:
    _email, _user_id = await _create_user(UserRole.EMPLOYEE)
    assert await _plan_count() == 0

    stamp = await _stamp(OPEN_DAY)

    assert stamp == ActualPriceStamp(
        plans_stamped=0,
        items_priced=0,
        items_unavailable=0,
    )
    assert await _plan_count() == 0


async def test_second_stamp_keeps_frozen_actual_price() -> None:
    dish_id = await _add_dish(price_kopecks=41000)
    _email, user_id = await _create_user(UserRole.EMPLOYEE)
    plan_id = await _insert_plan(
        user_id,
        OPEN_DAY,
        PlanStatus.DRAFT,
        [(dish_id, 2, 41000)],
    )
    await _set_dish(dish_id, price_kopecks=42500)
    first = await _stamp(OPEN_DAY)
    assert first.plans_stamped == 1

    await _set_dish(dish_id, price_kopecks=99900)
    second = await _stamp(OPEN_DAY)

    assert second == ActualPriceStamp(
        plans_stamped=0,
        items_priced=0,
        items_unavailable=0,
    )
    status, rows = await _stored_plan(plan_id)
    assert status == PlanStatus.PRICED
    assert rows == [(dish_id, 2, 41000, 42500, False)]


async def test_stamp_leaves_included_in_order_on_same_date() -> None:
    kept = await _add_dish(external_id="875", price_kopecks=41000)
    dropped = await _add_dish(external_id="900", name="Суп", price_kopecks=30000)
    _ordered_email, ordered_user = await _create_user(
        UserRole.EMPLOYEE,
        email="ordered@test.local",
    )
    _draft_email, draft_user = await _create_user(
        UserRole.EMPLOYEE,
        email="draft@test.local",
    )
    ordered_id = await _insert_plan(
        ordered_user,
        OPEN_DAY,
        PlanStatus.INCLUDED_IN_ORDER,
        [(kept, 2, 41000), (dropped, 1, 30000)],
    )
    draft_id = await _insert_plan(
        draft_user,
        OPEN_DAY,
        PlanStatus.DRAFT,
        [(kept, 1, 41000)],
    )
    await _freeze_plan_items(
        ordered_id,
        {
            kept: (42500, False),
            dropped: (None, True),
        },
    )

    await _set_dish(kept, price_kopecks=99900)
    await _set_dish(dropped, price_kopecks=35000, available=True)
    stamp = await _stamp(OPEN_DAY)

    assert stamp == ActualPriceStamp(
        plans_stamped=1,
        items_priced=1,
        items_unavailable=0,
    )
    ordered_status, ordered_rows = await _stored_plan(ordered_id)
    assert ordered_status == PlanStatus.INCLUDED_IN_ORDER
    assert ordered_rows == [
        (kept, 2, 41000, 42500, False),
        (dropped, 1, 30000, None, True),
    ]
    draft_status, draft_rows = await _stored_plan(draft_id)
    assert draft_status == PlanStatus.PRICED
    assert draft_rows == [(kept, 1, 41000, 99900, False)]


async def test_get_after_stamp_sums_buyable_items(client: AsyncClient) -> None:
    kept = await _add_dish(external_id="875", price_kopecks=41000)
    dropped = await _add_dish(
        external_id="900",
        name="Суп",
        price_kopecks=30000,
    )
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    saved = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={
            "items": [
                {"dish_id": kept, "qty": 2},
                {"dish_id": dropped, "qty": 1},
            ]
        },
    )
    assert saved.status_code == 200

    await _set_dish(kept, price_kopecks=42500)
    await _set_dish(dropped, available=False)
    await _stamp(OPEN_DAY)

    listed = await client.get(_path(OPEN_DAY), headers=_auth(token))
    assert listed.status_code == 200
    body = listed.json()
    assert body["status"] == "priced"
    assert body["editable"] is False
    assert body["actual_total_kopecks"] == 85000
    assert body["planned_total_kopecks"] == 112000


async def test_get_all_unavailable_priced_plan_actual_total_is_zero(
    client: AsyncClient,
) -> None:
    dish_id = await _add_dish(price_kopecks=30000)
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    saved = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert saved.status_code == 200
    await _set_dish(dish_id, available=False)
    await _stamp(OPEN_DAY)

    listed = await client.get(_path(OPEN_DAY), headers=_auth(token))
    body = listed.json()
    assert body["status"] == "priced"
    assert body["actual_total_kopecks"] == 0
    assert body["planned_total_kopecks"] == 30000
    assert body["items"][0]["unavailable"] is True
    assert body["items"][0]["actual_price_kopecks"] is None


async def test_get_empty_priced_plan_actual_total_is_zero(
    client: AsyncClient,
) -> None:
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    saved = await client.put(
        _path(OPEN_DAY),
        headers=_auth(token),
        json={"items": []},
    )
    assert saved.status_code == 200
    await _stamp(OPEN_DAY)

    listed = await client.get(_path(OPEN_DAY), headers=_auth(token))
    body = listed.json()
    assert body["status"] == "priced"
    assert body["actual_total_kopecks"] == 0
    assert body["planned_total_kopecks"] == 0
    assert body["items"] == []


async def test_put_after_stamp_is_cutoff_before_deadline(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed = datetime(2026, 10, 4, 15, 59, tzinfo=MOSCOW)
    monkeypatch.setattr("app.planning.service._now", lambda tz: fixed)
    day = date(2026, 10, 5)
    dish_id = await _add_dish(price_kopecks=41000)
    token, _user_id = await _token(client, UserRole.EMPLOYEE)
    saved = await client.put(
        _path(day),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 2}]},
    )
    assert saved.status_code == 200

    await _set_dish(dish_id, price_kopecks=42500)
    await _stamp(day)

    denied = await client.put(
        _path(day),
        headers=_auth(token),
        json={"items": [{"dish_id": dish_id, "qty": 1}]},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Cutoff passed"

    listed = await client.get(_path(day), headers=_auth(token))
    assert listed.status_code == 200
    body = listed.json()
    assert body["items"] == [
        {
            "dish_id": dish_id,
            "name": "Картофельные ньокки с грибами",
            "qty": 2,
            "planned_price_kopecks": 41000,
            "actual_price_kopecks": 42500,
            "unavailable": False,
        }
    ]
