"""Day-summary builder on the fixture catalog (no network)."""

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select

from app.catalog.models import Dish
from app.catalog.service import upsert_catalog
from app.db import SessionLocal
from app.orders.models import OfficeOrder, OfficeOrderStatus
from app.orders.schemas import OrderSummary
from app.orders.service import build_order_summary, run_cutoff
from app.planning.models import MealPlan, PlanItem, PlanStatus
from app.providers import MealtyError, NormalizedDish, parse_html
from app.users.models import Department, User, UserRole

FIXTURE = Path(__file__).parent / "fixtures" / "mealty_catalog.html"
DELIVERY = date.today() + timedelta(days=9)
PLANNED = 41000
STAMPED = 42500


class _FailingProvider:
    source = "mealty"

    async def fetch_catalog(self) -> list[NormalizedDish]:
        raise MealtyError("Mealty request failed")


def _parsed_fixture() -> list[NormalizedDish]:
    return parse_html(FIXTURE.read_text(encoding="utf-8"))


async def _seed_fixture_catalog() -> dict[str, Dish]:
    async with SessionLocal() as session:
        await upsert_catalog(session, "mealty", _parsed_fixture())
        rows = list((await session.scalars(select(Dish))).all())
        return {row.external_id: row for row in rows}


async def _user(
    email: str,
    full_name: str,
    department_name: str | None = None,
) -> int:
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
        return user.id


async def _plan(
    user_id: int,
    items: list[tuple[int, int, int]],
    *,
    delivery: date = DELIVERY,
) -> int:
    async with SessionLocal() as session:
        plan = MealPlan(
            user_id=user_id,
            delivery_date=delivery,
            status=PlanStatus.DRAFT,
        )
        session.add(plan)
        await session.flush()
        for dish_id, qty, price in items:
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


async def _set_price(
    dish_id: int,
    price_kopecks: int,
    *,
    available: bool = True,
) -> None:
    async with SessionLocal() as session:
        dish = await session.get(Dish, dish_id)
        assert dish is not None
        dish.price_kopecks = price_kopecks
        dish.available = available
        await session.commit()


async def _summary(delivery: date = DELIVERY) -> OrderSummary:
    async with SessionLocal() as session:
        return await build_order_summary(session, delivery)


async def _order_count() -> int:
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(OfficeOrder))
        return int(count or 0)


async def _close(delivery: date = DELIVERY) -> None:
    async with SessionLocal() as session:
        with patch("app.catalog.service.MealtyProvider", _FailingProvider):
            await run_cutoff(session, delivery)


async def test_closed_day_aggregates_snapshot_and_live_people() -> None:
    dishes = await _seed_fixture_catalog()
    gnocchi = dishes["875"]
    casserole = dishes["880"]
    await _set_price(gnocchi.id, STAMPED)
    ivan = await _user("ivan@summary.test", "Иван Сотрудник", "Разработка")
    maria = await _user("maria@summary.test", "Мария Сотрудница", "HR")
    petr = await _user("petr@summary.test", "Пётр Без Обеда")
    await _plan(ivan, [(gnocchi.id, 2, PLANNED), (casserole.id, 1, 36000)])
    await _plan(maria, [(gnocchi.id, 2, PLANNED)])
    await _plan(petr, [(casserole.id, 3, 36000)])
    await _set_price(casserole.id, 36000, available=False)

    await _close()
    summary = await _summary()

    assert summary.status == OfficeOrderStatus.LOCKED
    assert [item.external_id for item in summary.items] == ["875"]
    line = summary.items[0]
    assert line.name == "Картофельные ньокки"
    assert line.qty == 4
    assert line.unit_price_kopecks == STAMPED
    assert line.line_total_kopecks == 4 * STAMPED
    assert all(item.dish_id != casserole.id for item in summary.items)

    assert summary.totals.planned_kopecks == 4 * PLANNED
    assert summary.totals.actual_kopecks == 4 * STAMPED
    assert summary.totals.delta_kopecks == 4 * STAMPED - 4 * PLANNED
    assert summary.totals.delta_kopecks == 6000
    assert summary.totals.unavailable_count == 2
    assert type(summary.totals.actual_kopecks) is int
    assert type(summary.totals.planned_kopecks) is int

    by_id = {row.user_id: row for row in summary.by_employee}
    assert set(by_id) == {ivan, maria, petr}
    assert by_id[ivan].department_name == "Разработка"
    assert by_id[ivan].actual_total_kopecks == 2 * STAMPED
    assert by_id[ivan].unavailable_count == 1
    assert by_id[maria].actual_total_kopecks == 2 * STAMPED
    assert by_id[maria].unavailable_count == 0
    assert by_id[petr].actual_total_kopecks == 0
    assert by_id[petr].unavailable_count == 1
    assert by_id[petr].department_id is None
    names = [row.full_name for row in summary.by_employee]
    assert names == sorted(names)


async def test_snapshot_prices_ignore_later_catalog_sync() -> None:
    dishes = await _seed_fixture_catalog()
    gnocchi = dishes["875"]
    user_id = await _user("sync@summary.test", "Синк Сотрудник")
    await _plan(user_id, [(gnocchi.id, 2, gnocchi.price_kopecks)])
    await _close()
    before = await _summary()

    bumped = [
        dish.model_copy(update={"price_kopecks": dish.price_kopecks + 5000})
        for dish in _parsed_fixture()
    ]
    async with SessionLocal() as session:
        await upsert_catalog(session, "mealty", bumped)
    after = await _summary()

    assert [(item.model_dump()) for item in after.items] == [
        item.model_dump() for item in before.items
    ]
    assert after.totals.actual_kopecks == before.totals.actual_kopecks
    assert after.items[0].unit_price_kopecks == gnocchi.price_kopecks


async def test_collecting_is_live_and_does_not_persist() -> None:
    dishes = await _seed_fixture_catalog()
    gnocchi = dishes["875"]
    casserole = dishes["880"]
    ivan = await _user("open-ivan@summary.test", "Иван Открытый", "Разработка")
    maria = await _user("open-maria@summary.test", "Мария Открытая", "HR")
    await _plan(ivan, [(gnocchi.id, 2, PLANNED)])
    await _plan(maria, [(casserole.id, 1, 36000)])
    await _set_price(gnocchi.id, STAMPED)

    summary = await _summary()

    assert summary.status == OfficeOrderStatus.COLLECTING
    assert summary.totals.actual_kopecks is None
    assert summary.totals.delta_kopecks is None
    assert summary.totals.planned_kopecks == 2 * PLANNED + 36000
    assert summary.totals.unavailable_count == 0
    assert await _order_count() == 0
    preview = {item.external_id: item for item in summary.items}
    assert preview["875"].unit_price_kopecks == STAMPED
    assert preview["875"].qty == 2
    assert preview["875"].line_total_kopecks == 2 * STAMPED
    assert preview["880"].unit_price_kopecks == 36000
    assert [item.name for item in summary.items] == sorted(
        item.name for item in summary.items
    )
    people = {row.user_id: row for row in summary.by_employee}
    assert set(people) == {ivan, maria}
    assert people[ivan].actual_total_kopecks is None
    assert people[maria].department_name == "HR"

    async with SessionLocal() as session:
        stored = await session.scalar(select(MealPlan).where(MealPlan.user_id == ivan))
        assert stored is not None
        assert stored.status == PlanStatus.DRAFT

    await _close()
    closed = await _summary()
    assert closed.status == OfficeOrderStatus.LOCKED
    assert closed.totals.actual_kopecks == 2 * STAMPED + 36000
    assert closed.totals.delta_kopecks == (
        closed.totals.actual_kopecks - closed.totals.planned_kopecks
    )
    assert await _order_count() == 1


async def test_collecting_keeps_priced_plan_visible_without_office_order() -> None:
    """Cutoff can commit the price stamp and die before inserting the order."""
    dishes = await _seed_fixture_catalog()
    gnocchi = dishes["875"]
    user_id = await _user("priced-open@summary.test", "Пётр После Сбоя")
    plan_id = await _plan(user_id, [(gnocchi.id, 2, PLANNED)])
    async with SessionLocal() as session:
        plan = await session.get(MealPlan, plan_id)
        assert plan is not None
        plan.status = PlanStatus.PRICED
        await session.commit()

    summary = await _summary()

    assert summary.status == OfficeOrderStatus.COLLECTING
    assert summary.totals.actual_kopecks is None
    assert summary.totals.delta_kopecks is None
    assert summary.totals.planned_kopecks == 2 * PLANNED
    assert [row.user_id for row in summary.by_employee] == [user_id]
    assert summary.by_employee[0].actual_total_kopecks is None
    assert summary.items[0].external_id == "875"
    assert summary.items[0].qty == 2
    assert await _order_count() == 0
