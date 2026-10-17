"""Poll-job tests: overdue dates close, quiet days skip, no network."""

from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.catalog.models import Dish
from app.db import SessionLocal
from app.jobs import cutoff as cutoff_job
from app.orders.models import OfficeOrder
from app.planning.models import MealPlan, PlanItem, PlanStatus
from app.providers import MealtyError, NormalizedDish
from app.users.models import Settings, User, UserRole

MOSCOW = ZoneInfo("Europe/Moscow")
TODAY = date(2026, 10, 12)
YESTERDAY = date(2026, 10, 11)
TOMORROW = date(2026, 10, 13)
BEYOND_LOOKBACK = date(2026, 10, 9)
FIXED_NOW = datetime(2026, 10, 12, 10, 0, tzinfo=MOSCOW)


class _FailingProvider:
    source = "mealty"

    async def fetch_catalog(self) -> list[NormalizedDish]:
        raise MealtyError("Mealty request failed")


async def _add_dish(external_id: str) -> int:
    async with SessionLocal() as session:
        dish = Dish(
            source="mealty",
            external_id=external_id,
            name=f"Блюдо {external_id}",
            subtitle="",
            category="main_dish",
            price_kopecks=41000,
            available=True,
        )
        session.add(dish)
        await session.commit()
        await session.refresh(dish)
        return dish.id


async def _user(email: str) -> int:
    async with SessionLocal() as session:
        user = User(
            email=email,
            password_hash="x",
            full_name=email,
            role=UserRole.EMPLOYEE,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


async def _plan(user_id: int, delivery: date, dish_id: int, qty: int = 1) -> int:
    async with SessionLocal() as session:
        plan = MealPlan(
            user_id=user_id,
            delivery_date=delivery,
            status=PlanStatus.DRAFT,
        )
        session.add(plan)
        await session.flush()
        session.add(
            PlanItem(
                plan_id=plan.id,
                dish_id=dish_id,
                qty=qty,
                planned_price_kopecks=41000,
                actual_price_kopecks=None,
                unavailable=False,
            )
        )
        await session.commit()
        return plan.id


async def _orders_by_date() -> dict[date, str]:
    async with SessionLocal() as session:
        rows = list((await session.scalars(select(OfficeOrder))).all())
        return {row.delivery_date: row.status.value for row in rows}


async def _tick(
    monkeypatch: pytest.MonkeyPatch,
    now: datetime = FIXED_NOW,
) -> None:
    monkeypatch.setattr(cutoff_job, "_now", lambda tz: now)
    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        await cutoff_job.run_day_cutoff_tick()


async def test_tick_closes_overdue_date(monkeypatch: pytest.MonkeyPatch) -> None:
    dish_id = await _add_dish("tick-1")
    user_id = await _user("tick1@test.local")
    plan_id = await _plan(user_id, TODAY, dish_id)

    await _tick(monkeypatch)

    orders = await _orders_by_date()
    assert orders == {TODAY: "locked"}
    async with SessionLocal() as session:
        plan = await session.get(MealPlan, plan_id)
        assert plan is not None
        assert plan.status == PlanStatus.INCLUDED_IN_ORDER
        assert plan.office_order_id is not None


async def test_tick_skips_date_with_future_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dish_id = await _add_dish("tick-2")
    user_id = await _user("tick2@test.local")
    # Deadline for TOMORROW is today 16:00; fixed now is 10:00.
    await _plan(user_id, TOMORROW, dish_id)

    await _tick(monkeypatch)

    assert await _orders_by_date() == {}


async def test_tick_skips_quiet_day(monkeypatch: pytest.MonkeyPatch) -> None:
    await _tick(monkeypatch)
    assert await _orders_by_date() == {}


async def test_tick_ignores_dates_beyond_lookback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dish_id = await _add_dish("tick-4")
    user_id = await _user("tick4@test.local")
    await _plan(user_id, BEYOND_LOOKBACK, dish_id)

    await _tick(monkeypatch)

    assert await _orders_by_date() == {}


async def test_tick_picks_up_cutoff_time_change_without_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dish_id = await _add_dish("tick-5")
    user_id = await _user("tick5@test.local")
    await _plan(user_id, TOMORROW, dish_id)
    async with SessionLocal() as session:
        session.add(
            Settings(
                id=1,
                cutoff_time="16:00",
                timezone="Europe/Moscow",
                mealty_city="Москва",
                daily_limit_kopecks=None,
                catalog_sync_per_day=2,
            )
        )
        await session.commit()

    afternoon = datetime(2026, 10, 12, 13, 0, tzinfo=MOSCOW)
    await _tick(monkeypatch, now=afternoon)
    assert await _orders_by_date() == {}

    # Admin moved cutoff_time to 12:00 via PUT /api/admin/settings (no restart).
    async with SessionLocal() as session:
        settings = await session.get(Settings, 1)
        assert settings is not None
        settings.cutoff_time = "12:00"
        await session.commit()

    await _tick(monkeypatch, now=afternoon)
    assert await _orders_by_date() == {TOMORROW: "locked"}


async def test_tick_swallows_per_date_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dish_id = await _add_dish("tick-6")
    user_id = await _user("tick6@test.local")
    await _plan(user_id, YESTERDAY, dish_id)
    await _plan(user_id, TODAY, dish_id)

    real_run_cutoff = cutoff_job.run_cutoff

    async def flaky(session, delivery_date):  # type: ignore[no-untyped-def]
        if delivery_date == YESTERDAY:
            raise RuntimeError("boom")
        return await real_run_cutoff(session, delivery_date)

    monkeypatch.setattr(cutoff_job, "run_cutoff", flaky)
    # Use _tick so FIXED_NOW keeps TODAY/YESTERDAY inside the lookback window.
    await _tick(monkeypatch, now=FIXED_NOW)

    orders = await _orders_by_date()
    assert orders == {TODAY: "locked"}
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(OfficeOrder))
    assert int(count or 0) == 1
