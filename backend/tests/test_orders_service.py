"""run_cutoff orchestrator tests on the fixture catalog (no network)."""

import asyncio
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.catalog.models import Dish
from app.catalog.service import upsert_catalog
from app.db import SessionLocal
from app.orders.models import OfficeOrder, OfficeOrderItem, OfficeOrderStatus
from app.orders.service import CutoffOutcome, run_cutoff
from app.planning.models import MealPlan, PlanItem, PlanStatus
from app.planning.service import apply_actual_prices
from app.providers import MealtyError, NormalizedDish, parse_html
from app.users.models import CatalogSyncRun, Settings, User, UserRole

FIXTURE = Path(__file__).parent / "fixtures" / "mealty_catalog.html"
DELIVERY = date.today() + timedelta(days=7)


def _parsed_fixture() -> list[NormalizedDish]:
    return parse_html(FIXTURE.read_text(encoding="utf-8"))


class _FailingProvider:
    source = "mealty"

    async def fetch_catalog(self) -> list[NormalizedDish]:
        raise MealtyError("Mealty request failed")


class _StubProvider:
    source = "mealty"

    async def fetch_catalog(self) -> list[NormalizedDish]:
        return _parsed_fixture()


async def _seed_fixture_catalog() -> dict[str, Dish]:
    async with SessionLocal() as session:
        await upsert_catalog(session, "mealty", _parsed_fixture())
        rows = list((await session.scalars(select(Dish))).all())
        return {row.external_id: row for row in rows}


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


async def _plan(
    user_id: int,
    delivery: date,
    items: list[tuple[int, int, int]],
    status: PlanStatus = PlanStatus.DRAFT,
) -> int:
    async with SessionLocal() as session:
        plan = MealPlan(
            user_id=user_id,
            delivery_date=delivery,
            status=status,
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


async def _stored_order(delivery: date) -> tuple[OfficeOrder, list[OfficeOrderItem]]:
    async with SessionLocal() as session:
        order = await session.scalar(
            select(OfficeOrder)
            .where(OfficeOrder.delivery_date == delivery)
            .options(selectinload(OfficeOrder.items))
        )
        assert order is not None
        return order, list(order.items)


async def _stored_plan(plan_id: int) -> MealPlan:
    async with SessionLocal() as session:
        plan = await session.scalar(
            select(MealPlan)
            .where(MealPlan.id == plan_id)
            .options(selectinload(MealPlan.items))
        )
        assert plan is not None
        return plan


async def _run(delivery: date):
    async with SessionLocal() as session:
        return await run_cutoff(session, delivery)


async def test_cutoff_aggregates_two_employees_and_sync_ok() -> None:
    dishes = await _seed_fixture_catalog()
    first = next(iter(dishes.values()))
    second = list(dishes.values())[1]
    u1 = await _user("agg1@test.local")
    u2 = await _user("agg2@test.local")
    p1 = await _plan(u1, DELIVERY, [(first.id, 2, first.price_kopecks)])
    p2 = await _plan(u2, DELIVERY, [(first.id, 2, first.price_kopecks)])
    p3 = await _plan(u2, DELIVERY + timedelta(days=1), [(second.id, 1, 41000)])

    with patch("app.catalog.service.MealtyProvider", _StubProvider):
        result = await _run(DELIVERY)

    assert result.outcome == CutoffOutcome.CLOSED
    assert result.sync == "ok"
    assert result.order_status == OfficeOrderStatus.LOCKED
    assert result.plans_closed == 2
    assert result.items_unavailable == 0

    order, items = await _stored_order(DELIVERY)
    assert order.status == OfficeOrderStatus.LOCKED
    line = next(item for item in items if item.dish_id == first.id)
    assert line.qty == 4
    assert line.unit_price_kopecks == first.price_kopecks
    assert line.line_total_kopecks == 4 * first.price_kopecks
    assert all(item.dish_id != second.id for item in items)

    for plan_id in (p1, p2):
        stored = await _stored_plan(plan_id)
        assert stored.status == PlanStatus.INCLUDED_IN_ORDER
        assert stored.office_order_id == order.id

    other = await _stored_plan(p3)
    assert other.status == PlanStatus.DRAFT
    assert other.office_order_id is None


async def test_cutoff_sync_failure_closes_on_stored_snapshot() -> None:
    dishes = await _seed_fixture_catalog()
    dish = next(iter(dishes.values()))
    available_before = await _dish_availability()
    u = await _user("offline@test.local")
    p = await _plan(u, DELIVERY, [(dish.id, 1, dish.price_kopecks)])

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        result = await _run(DELIVERY)

    assert result.outcome == CutoffOutcome.CLOSED
    assert result.sync == "skipped"
    order, items = await _stored_order(DELIVERY)
    line = items[0]
    assert line.dish_id == dish.id
    assert line.unit_price_kopecks == dish.price_kopecks
    stored = await _stored_plan(p)
    assert stored.status == PlanStatus.INCLUDED_IN_ORDER
    assert stored.items[0].actual_price_kopecks == dish.price_kopecks
    assert stored.items[0].unavailable is False
    # No mass delisting: the failed snapshot changed no dish row.
    assert available_before == await _dish_availability()


async def _dish_availability() -> dict[int, bool]:
    async with SessionLocal() as session:
        rows = list((await session.scalars(select(Dish))).all())
        return {row.id: row.available for row in rows}


async def test_cutoff_excludes_unavailable_items() -> None:
    dishes = await _seed_fixture_catalog()
    kept = next(iter(dishes.values()))
    dropped = list(dishes.values())[1]
    async with SessionLocal() as session:
        gone = await session.get(Dish, dropped.id)
        assert gone is not None
        gone.available = False
        await session.commit()

    u = await _user("unavail@test.local")
    await _plan(
        u,
        DELIVERY,
        [(kept.id, 1, kept.price_kopecks), (dropped.id, 2, dropped.price_kopecks)],
    )

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        result = await _run(DELIVERY)

    assert result.outcome == CutoffOutcome.CLOSED
    assert result.items_unavailable == 1
    order, items = await _stored_order(DELIVERY)
    assert [item.dish_id for item in items] == [kept.id]
    assert items[0].line_total_kopecks == kept.price_kopecks


async def test_cutoff_moves_empty_plans_too() -> None:
    await _seed_fixture_catalog()
    u_full = await _user("full@test.local")
    u_empty = await _user("empty@test.local")
    dish = (await _dish_map()).popitem()[1]
    await _plan(u_full, DELIVERY, [(dish.id, 1, dish.price_kopecks)])
    await _plan(u_empty, DELIVERY, [])

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        result = await _run(DELIVERY)

    assert result.plans_closed == 2


async def _dish_map() -> dict[str, Dish]:
    async with SessionLocal() as session:
        rows = list((await session.scalars(select(Dish))).all())
        return {row.external_id: row for row in rows}


async def test_cutoff_retry_after_crash_between_steps_converges() -> None:
    dishes = await _seed_fixture_catalog()
    dish = next(iter(dishes.values()))
    u1 = await _user("retry1@test.local")
    u2 = await _user("retry2@test.local")
    p1 = await _plan(u1, DELIVERY, [(dish.id, 1, dish.price_kopecks)])
    p2 = await _plan(u2, DELIVERY, [(dish.id, 3, dish.price_kopecks)])

    # Crash after the stamp step: plans are priced, no order exists yet.
    async with SessionLocal() as session:
        stamp = await apply_actual_prices(session, DELIVERY)
    assert stamp.plans_stamped == 2

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        result = await _run(DELIVERY)

    assert result.outcome == CutoffOutcome.CLOSED
    assert result.plans_closed == 2
    order, items = await _stored_order(DELIVERY)
    line = items[0]
    assert line.qty == 4
    assert line.line_total_kopecks == 4 * dish.price_kopecks
    for plan_id in (p1, p2):
        stored = await _stored_plan(plan_id)
        assert stored.status == PlanStatus.INCLUDED_IN_ORDER
        assert stored.office_order_id == order.id


async def test_cutoff_picks_up_included_plans_without_double_count() -> None:
    dishes = await _seed_fixture_catalog()
    dish = next(iter(dishes.values()))
    u1 = await _user("inc1@test.local")
    u2 = await _user("inc2@test.local")
    # Leftover from a hypothetical partial run: plan already aggregated.
    p_inc = await _plan(
        u1,
        DELIVERY,
        [(dish.id, 2, dish.price_kopecks)],
        status=PlanStatus.INCLUDED_IN_ORDER,
    )
    async with SessionLocal() as session:
        item = await session.scalar(select(PlanItem).where(PlanItem.plan_id == p_inc))
        assert item is not None
        item.actual_price_kopecks = dish.price_kopecks
        await session.commit()
    p_priced = await _plan(u2, DELIVERY, [(dish.id, 1, dish.price_kopecks)])
    async with SessionLocal() as session:
        await apply_actual_prices(session, DELIVERY)

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        result = await _run(DELIVERY)

    assert result.plans_closed == 1
    order, items = await _stored_order(DELIVERY)
    assert len(items) == 1
    assert items[0].qty == 3
    for plan_id in (p_inc, p_priced):
        stored = await _stored_plan(plan_id)
        assert stored.office_order_id == order.id


async def test_cutoff_second_call_is_idempotent_noop() -> None:
    dishes = await _seed_fixture_catalog()
    dish = next(iter(dishes.values()))
    u = await _user("idem@test.local")
    await _plan(u, DELIVERY, [(dish.id, 2, dish.price_kopecks)])

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        first = await _run(DELIVERY)
    assert first.outcome == CutoffOutcome.CLOSED

    order_before, items_before = await _stored_order(DELIVERY)

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        second = await _run(DELIVERY)

    assert second.outcome == CutoffOutcome.ALREADY_CLOSED
    assert second.sync == "skipped"
    assert second.plans_closed == 0
    assert second.items_unavailable == 0
    order_after, items_after = await _stored_order(DELIVERY)
    assert order_after.id == order_before.id
    assert order_after.status == order_before.status
    assert {(i.dish_id, i.qty) for i in items_after} == {
        (i.dish_id, i.qty) for i in items_before
    }


async def test_cutoff_snapshot_immune_to_later_sync() -> None:
    dishes = await _seed_fixture_catalog()
    dish = next(iter(dishes.values()))
    u = await _user("immune@test.local")
    await _plan(u, DELIVERY, [(dish.id, 2, dish.price_kopecks)])

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        await _run(DELIVERY)

    _order_before, items_before = await _stored_order(DELIVERY)
    line_before = items_before[0]

    # A later successful sync reprices the whole catalog.
    repriced = [
        parsed.model_copy(update={"price_kopecks": parsed.price_kopecks + 5000})
        for parsed in _parsed_fixture()
    ]
    async with SessionLocal() as session:
        await upsert_catalog(session, "mealty", repriced)

    # The catalog really changed …
    async with SessionLocal() as session:
        fresh = await session.get(Dish, dish.id)
        assert fresh is not None
        assert fresh.price_kopecks == dish.price_kopecks + 5000

    # … but the closed order's snapshot did not.
    _order_after, items_after = await _stored_order(DELIVERY)
    (line_after,) = items_after
    assert line_after.qty == line_before.qty
    assert line_after.unit_price_kopecks == line_before.unit_price_kopecks
    assert line_after.line_total_kopecks == line_before.line_total_kopecks


async def test_cutoff_nothing_to_close_without_items() -> None:
    await _seed_fixture_catalog()
    u = await _user("quiet@test.local")
    await _plan(u, DELIVERY, [])

    result = await _run(DELIVERY)

    assert result.outcome == CutoffOutcome.NOTHING_TO_CLOSE
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(OfficeOrder))
    assert int(count or 0) == 0


async def test_cutoff_records_quota_run_but_never_blocks() -> None:
    dishes = await _seed_fixture_catalog()
    dish = next(iter(dishes.values()))
    u = await _user("quota@test.local")
    await _plan(u, DELIVERY, [(dish.id, 1, dish.price_kopecks)])

    from datetime import datetime
    from zoneinfo import ZoneInfo

    async with SessionLocal() as session:
        session.add(
            Settings(
                id=1,
                cutoff_time="16:00",
                timezone="Europe/Moscow",
                mealty_city="Москва",
                daily_limit_kopecks=None,
                catalog_sync_per_day=1,
            )
        )
        session.add(CatalogSyncRun(ran_at=datetime.now(ZoneInfo("Europe/Moscow"))))
        await session.commit()

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        result = await _run(DELIVERY)

    assert result.outcome == CutoffOutcome.CLOSED
    async with SessionLocal() as session:
        runs = await session.scalar(select(func.count()).select_from(CatalogSyncRun))
    assert int(runs or 0) == 2


async def test_concurrent_cutoffs_create_exactly_one_order() -> None:
    dishes = await _seed_fixture_catalog()
    dish = next(iter(dishes.values()))
    u = await _user("race@test.local")
    await _plan(u, DELIVERY, [(dish.id, 2, dish.price_kopecks)])

    async def _one() -> object:
        async with SessionLocal() as session:
            return await run_cutoff(session, DELIVERY)

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        first, second = await asyncio.gather(_one(), _one())

    outcomes = {first.outcome, second.outcome}  # type: ignore[attr-defined]
    assert outcomes <= {CutoffOutcome.CLOSED, CutoffOutcome.ALREADY_CLOSED}
    assert CutoffOutcome.CLOSED in outcomes
    async with SessionLocal() as session:
        orders = list(
            (
                await session.scalars(
                    select(OfficeOrder).where(OfficeOrder.delivery_date == DELIVERY)
                )
            ).all()
        )
        item_count = await session.scalar(
            select(func.count())
            .select_from(OfficeOrderItem)
            .join(OfficeOrder, OfficeOrder.id == OfficeOrderItem.office_order_id)
        )
    assert len(orders) == 1
    assert int(item_count or 0) == 1
