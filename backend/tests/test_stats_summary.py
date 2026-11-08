"""Period stats: closed plans only, no network."""

from datetime import date, timedelta
from unittest.mock import patch

import bcrypt
from httpx import AsyncClient
from sqlalchemy import func, select

from app.catalog.models import Dish
from app.db import SessionLocal
from app.orders.models import OfficeOrder, OfficeOrderStatus
from app.planning.models import MealPlan, PlanItem, PlanStatus
from app.providers import MealtyError, NormalizedDish
from app.stats.router import INVERTED_RANGE_DETAIL
from app.stats.schemas import StatsSummary
from app.stats.service import build_summary
from app.users.models import Department, User, UserRole
from tests.conftest import BearerAuth

DAY = date(2026, 9, 16)
NEXT = date(2026, 9, 17)
PLANNED = 41000
STAMPED = 42500


class _FailingProvider:
    source = "mealty"

    async def fetch_catalog(self) -> list[NormalizedDish]:
        raise MealtyError("Mealty request failed")


async def _dish(external_id: str, name: str) -> int:
    async with SessionLocal() as session:
        dish = Dish(
            source="mealty",
            external_id=external_id,
            name=name,
            subtitle="",
            category="main_dish",
            price_kopecks=PLANNED,
            available=True,
        )
        session.add(dish)
        await session.commit()
        await session.refresh(dish)
        return dish.id


async def _user(
    email: str,
    full_name: str,
    department_name: str | None = None,
) -> tuple[int, int | None]:
    async with SessionLocal() as session:
        department_id = None
        if department_name is not None:
            department = Department(name=department_name)
            session.add(department)
            await session.flush()
            department_id = department.id
        user = User(
            email=email,
            password_hash="x",
            full_name=full_name,
            role=UserRole.EMPLOYEE,
            department_id=department_id,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id, department_id


async def _plan(
    user_id: int,
    delivery: date,
    items: list[tuple[int, int, int, int | None, bool]],
    *,
    status: PlanStatus = PlanStatus.INCLUDED_IN_ORDER,
    office_order_id: int | None = None,
) -> int:
    async with SessionLocal() as session:
        plan = MealPlan(
            user_id=user_id,
            delivery_date=delivery,
            status=status,
            office_order_id=office_order_id,
        )
        session.add(plan)
        await session.flush()
        for dish_id, qty, planned, actual, unavailable in items:
            session.add(
                PlanItem(
                    plan_id=plan.id,
                    dish_id=dish_id,
                    qty=qty,
                    planned_price_kopecks=planned,
                    actual_price_kopecks=actual,
                    unavailable=unavailable,
                )
            )
        await session.commit()
        return plan.id


async def _placed_order(delivery: date) -> int:
    async with SessionLocal() as session:
        order = OfficeOrder(
            delivery_date=delivery,
            status=OfficeOrderStatus.PLACED,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order.id


async def _summary(
    period_from: date = DAY,
    period_to: date = DAY,
    department_id: int | None = None,
) -> StatsSummary:
    async with SessionLocal() as session:
        return await build_summary(
            session,
            period_from=period_from,
            period_to=period_to,
            department_id=department_id,
        )


def _keys(summary: StatsSummary) -> set[str]:
    return set(summary.model_dump(by_alias=True))


async def test_price_rule_kopecks_delta_and_unavailable() -> None:
    gnocchi = await _dish("875", "Картофельные ньокки")
    gone = await _dish("880", "Запеканка")
    user_id, _department_id = await _user(
        "ivan@stats.test",
        "Иван Сотрудник",
        "Разработка",
    )
    await _plan(
        user_id,
        DAY,
        [
            (gnocchi, 2, PLANNED, STAMPED, False),
            (gone, 1, 36000, None, True),
        ],
    )

    summary = await _summary()

    assert summary.total_planned_kopecks == 82000
    assert summary.total_actual_kopecks == 85000
    assert summary.delta_kopecks == 3000
    assert summary.unavailable_count == 1
    assert type(summary.total_planned_kopecks) is int
    assert type(summary.total_actual_kopecks) is int
    assert type(summary.delta_kopecks) is int
    assert summary.by_employee[0].actual_kopecks == 85000
    assert "note" not in _keys(summary)
    assert "by_day" not in _keys(summary)


async def test_all_unavailable_plan_still_counted() -> None:
    dish_id = await _dish("gone", "Нет в меню")
    user_id, _department_id = await _user("empty@stats.test", "Пустой План")
    await _plan(user_id, DAY, [(dish_id, 2, 36000, None, True)])

    summary = await _summary()

    assert summary.total_planned_kopecks == 0
    assert summary.total_actual_kopecks == 0
    assert summary.delta_kopecks == 0
    assert summary.unavailable_count == 1
    assert len(summary.by_employee) == 1
    assert summary.by_employee[0].user_id == user_id
    assert summary.by_employee[0].actual_kopecks == 0
    assert summary.by_employee[0].order_count == 1
    assert summary.top_dishes == []
    assert summary.price_changes == []


async def test_two_days_merge_into_one_employee_row() -> None:
    dish_id = await _dish("875", "Ньокки")
    user_id, department_id = await _user(
        "ivan@stats.test",
        "Иван Сотрудник",
        "Разработка",
    )
    await _plan(user_id, DAY, [(dish_id, 1, PLANNED, STAMPED, False)])
    await _plan(user_id, NEXT, [(dish_id, 1, PLANNED, STAMPED, False)])

    summary = await _summary(DAY, NEXT)

    assert len(summary.by_employee) == 1
    assert summary.by_employee[0].order_count == 2
    assert summary.by_employee[0].actual_kopecks == 2 * STAMPED
    assert summary.by_department[0].department_id == department_id
    assert summary.by_department[0].order_count == 2
    assert summary.by_department[0].actual_kopecks == 2 * STAMPED
    assert len(summary.price_changes) == 1
    assert summary.price_changes[0].planned_price_kopecks == PLANNED
    assert summary.price_changes[0].actual_price_kopecks == STAMPED


async def test_top_dishes_sort_and_price_triples() -> None:
    popular = await _dish("2", "Борщ")
    richer = await _dish("9", "Стейк")
    same_qty = await _dish("3", "Суп")
    steady = await _dish("4", "Каша")
    user_id, _department_id = await _user("cook@stats.test", "Повар")
    await _plan(
        user_id,
        DAY,
        [
            (popular, 3, 10000, 11000, False),
            (richer, 1, 50000, 50000, False),
            (same_qty, 1, 20000, 25000, False),
            (steady, 1, 15000, 15000, False),
        ],
    )
    other_id, _other_department = await _user("cook2@stats.test", "Второй")
    await _plan(other_id, DAY, [(popular, 1, 10000, 11000, False)])
    third_id, _third_department = await _user("cook3@stats.test", "Третий")
    await _plan(third_id, NEXT, [(popular, 1, 9000, 11000, False)])

    summary = await _summary(DAY, NEXT)

    assert [row.dish_id for row in summary.top_dishes] == [
        popular,
        richer,
        same_qty,
        steady,
    ]
    assert summary.top_dishes[0].qty == 5
    assert summary.top_dishes[1].actual_kopecks == 50000
    assert summary.top_dishes[2].actual_kopecks == 25000
    triples = {
        (row.dish_id, row.planned_price_kopecks, row.actual_price_kopecks)
        for row in summary.price_changes
    }
    assert triples == {
        (popular, 10000, 11000),
        (popular, 9000, 11000),
        (same_qty, 20000, 25000),
    }
    assert all(row.dish_id != steady for row in summary.price_changes)
    assert all(row.dish_id != richer for row in summary.price_changes)


async def test_department_sums_and_filter_matches_slice() -> None:
    dev_dish = await _dish("dev", "Ньокки")
    hr_dish = await _dish("hr", "Салат")
    ivan, dev_id = await _user("ivan@stats.test", "Иван Сотрудник", "Разработка")
    maria, hr_id = await _user("maria@stats.test", "Мария Сотрудница", "HR")
    assert dev_id is not None
    assert hr_id is not None
    await _plan(
        ivan,
        DAY,
        [
            (dev_dish, 2, PLANNED, STAMPED, False),
            (hr_dish, 1, 1000, None, True),
        ],
    )
    await _plan(ivan, NEXT, [(dev_dish, 1, PLANNED, STAMPED, False)])
    await _plan(maria, DAY, [(hr_dish, 1, 36000, 36000, False)])

    full = await _summary(DAY, NEXT)
    sliced = await _summary(DAY, NEXT, department_id=dev_id)

    assert sum(row.actual_kopecks for row in full.by_employee) == (
        full.total_actual_kopecks
    )
    assert sum(row.actual_kopecks for row in full.by_department) == (
        full.total_actual_kopecks
    )
    assert full.by_department[0].name == "HR"
    assert [row.department_id for row in full.by_department] == [hr_id, dev_id]
    dev_row = next(row for row in full.by_department if row.department_id == dev_id)
    assert sliced.total_planned_kopecks == 3 * PLANNED
    assert sliced.total_actual_kopecks == dev_row.actual_kopecks
    assert sliced.delta_kopecks == sliced.total_actual_kopecks - 3 * PLANNED
    assert sliced.unavailable_count == 1
    assert full.unavailable_count == 1
    assert sliced.by_department == [dev_row]
    assert sliced.by_employee == [
        row for row in full.by_employee if row.user_id == ivan
    ]
    assert sliced.top_dishes == [
        row for row in full.top_dishes if row.dish_id == dev_dish
    ]
    assert sliced.price_changes == [
        row for row in full.price_changes if row.dish_id == dev_dish
    ]
    assert sliced.by_employee[0].order_count == 2


async def test_user_without_department_skips_department_row() -> None:
    dish_id = await _dish("solo", "Омлет")
    user_id, department_id = await _user("solo@stats.test", "Без Отдела")
    assert department_id is None
    await _plan(user_id, DAY, [(dish_id, 1, 10000, 10000, False)])

    summary = await _summary()

    assert summary.total_actual_kopecks == 10000
    assert summary.by_department == []
    assert summary.by_employee[0].user_id == user_id
    assert summary.by_employee[0].actual_kopecks == 10000


async def test_empty_period_and_unknown_department_are_zeros() -> None:
    dish_id = await _dish("875", "Ньокки")
    user_id, _department_id = await _user("ivan@stats.test", "Иван", "Разработка")
    await _plan(user_id, DAY, [(dish_id, 1, PLANNED, STAMPED, False)])

    empty = await _summary(date(2026, 1, 1), date(2026, 1, 2))
    unknown = await _summary(DAY, DAY, department_id=999_999)

    for summary in (empty, unknown):
        assert summary.period_from == (date(2026, 1, 1) if summary is empty else DAY)
        assert summary.total_planned_kopecks == 0
        assert summary.total_actual_kopecks == 0
        assert summary.delta_kopecks == 0
        assert summary.unavailable_count == 0
        assert summary.by_department == []
        assert summary.by_employee == []
        assert summary.top_dishes == []
        assert summary.price_changes == []
        assert "note" not in _keys(summary)
        assert "by_day" not in _keys(summary)
    assert unknown.period_from == DAY
    assert unknown.to == DAY


async def test_draft_priced_and_locked_are_excluded() -> None:
    dish_id = await _dish("875", "Ньокки")
    included_id, _included_department = await _user("in@stats.test", "В Заказе")
    draft_id, _draft_department = await _user("draft@stats.test", "Черновик")
    priced_id, _priced_department = await _user("priced@stats.test", "Оценён")
    locked_id, _locked_department = await _user("locked@stats.test", "Закрыт")
    await _plan(included_id, DAY, [(dish_id, 1, 10000, 11000, False)])
    await _plan(
        draft_id,
        DAY,
        [(dish_id, 5, 99999, 99999, False)],
        status=PlanStatus.DRAFT,
    )
    await _plan(
        priced_id,
        DAY,
        [(dish_id, 5, 88888, 88888, False)],
        status=PlanStatus.PRICED,
    )
    await _plan(
        locked_id,
        DAY,
        [(dish_id, 5, 77777, 77777, False)],
        status=PlanStatus.LOCKED,
    )

    summary = await _summary()

    assert summary.total_planned_kopecks == 10000
    assert summary.total_actual_kopecks == 11000
    assert [row.user_id for row in summary.by_employee] == [included_id]


async def test_placed_office_order_still_counts() -> None:
    dish_id = await _dish("875", "Ньокки")
    user_id, _department_id = await _user("placed@stats.test", "Уже Заказан")
    order_id = await _placed_order(DAY)
    await _plan(
        user_id,
        DAY,
        [(dish_id, 1, PLANNED, STAMPED, False)],
        office_order_id=order_id,
    )

    summary = await _summary()

    assert summary.total_actual_kopecks == STAMPED
    assert summary.by_employee[0].order_count == 1


def _http_day() -> date:
    return date.today() + timedelta(days=21)


async def _add_priced_dish(external_id: str, price_kopecks: int) -> int:
    async with SessionLocal() as session:
        dish = Dish(
            source="mealty",
            external_id=external_id,
            name=f"Блюдо {external_id}",
            subtitle="",
            category="main_dish",
            price_kopecks=price_kopecks,
            available=True,
        )
        session.add(dish)
        await session.commit()
        await session.refresh(dish)
        return dish.id


async def _employee(
    client: AsyncClient,
    email: str,
    full_name: str,
) -> BearerAuth:
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    async with SessionLocal() as session:
        user = User(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
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


async def _row_counts() -> tuple[int, int]:
    async with SessionLocal() as session:
        plans = await session.scalar(select(func.count()).select_from(MealPlan))
        orders = await session.scalar(select(func.count()).select_from(OfficeOrder))
        return int(plans or 0), int(orders or 0)


async def test_summary_access(
    client: AsyncClient,
    employee_auth: BearerAuth,
    procurement_auth: BearerAuth,
    admin_auth: BearerAuth,
) -> None:
    params = {"from": "2026-09-14", "to": "2026-09-18"}
    missing = await client.get("/api/stats/summary", params=params)
    assert missing.status_code == 401

    denied = await client.get(
        "/api/stats/summary",
        params=params,
        headers=employee_auth.headers,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Forbidden"

    for auth in (procurement_auth, admin_auth):
        allowed = await client.get(
            "/api/stats/summary",
            params=params,
            headers=auth.headers,
        )
        assert allowed.status_code == 200, allowed.text
        body = allowed.json()
        assert body["from"] == "2026-09-14"
        assert body["to"] == "2026-09-18"
        assert body["total_planned_kopecks"] == 0
        assert body["by_employee"] == []
        assert "note" not in body
        assert "by_day" not in body


async def test_inverted_range_is_422_before_aggregation(
    client: AsyncClient,
    procurement_auth: BearerAuth,
) -> None:
    with patch("app.stats.router.build_summary") as mocked:
        response = await client.get(
            "/api/stats/summary",
            params={"from": "2026-09-18", "to": "2026-09-14"},
            headers=procurement_auth.headers,
        )
    assert response.status_code == 422
    assert response.json()["detail"] == INVERTED_RANGE_DETAIL
    mocked.assert_not_called()

    missing = await client.get(
        "/api/stats/summary",
        params={"to": "2026-09-18"},
        headers=procurement_auth.headers,
    )
    assert missing.status_code == 422


async def test_closed_day_matches_order_totals_and_repeat_is_readonly(
    client: AsyncClient,
    procurement_auth: BearerAuth,
) -> None:
    day = _http_day()
    live = await _add_priced_dish("http-live", PLANNED)
    gone = await _add_priced_dish("http-gone", 36000)
    employee = await _employee(client, "ivan-http@stats.test", "Иван Сотрудник")
    saved = await client.put(
        f"/api/plans/{day.isoformat()}",
        headers=employee.headers,
        json={
            "items": [
                {"dish_id": live, "qty": 2},
                {"dish_id": gone, "qty": 1},
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    async with SessionLocal() as session:
        dish = await session.get(Dish, live)
        assert dish is not None
        dish.price_kopecks = STAMPED
        missing = await session.get(Dish, gone)
        assert missing is not None
        missing.available = False
        await session.commit()

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        closed = await client.post(
            f"/api/orders/{day.isoformat()}/cutoff",
            headers=procurement_auth.headers,
        )
    assert closed.status_code == 200, closed.text

    order = await client.get(
        f"/api/orders/{day.isoformat()}",
        headers=procurement_auth.headers,
    )
    assert order.status_code == 200, order.text
    params = {"from": day.isoformat(), "to": day.isoformat()}
    before = await _row_counts()
    first = await client.get(
        "/api/stats/summary",
        params=params,
        headers=procurement_auth.headers,
    )
    second = await client.get(
        "/api/stats/summary",
        params=params,
        headers=procurement_auth.headers,
    )
    after = await _row_counts()

    assert first.status_code == 200, first.text
    assert second.json() == first.json()
    assert before == after
    totals = order.json()["totals"]
    body = first.json()
    assert body["total_planned_kopecks"] == totals["planned_kopecks"]
    assert body["total_actual_kopecks"] == totals["actual_kopecks"]
    assert body["delta_kopecks"] == totals["delta_kopecks"]
    assert body["unavailable_count"] == totals["unavailable_count"]
    assert body["total_planned_kopecks"] == 2 * PLANNED
    assert body["total_actual_kopecks"] == 2 * STAMPED
    assert body["unavailable_count"] == 1
