"""Read and replace an employee meal plan for one delivery date."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.catalog.models import Dish
from app.planning.models import MealPlan, PlanItem, PlanStatus
from app.planning.schemas import PlanItemOut, PlanOut, PlanReplace
from app.users.models import Settings, User, UserRole
from app.users.quota import assert_plan_within_limit
from app.users.settings_service import get_or_create_settings


@dataclass
class EditablePlan:
    session: AsyncSession
    user: User
    plan: MealPlan | None
    settings: Settings
    delivery_date: date


@dataclass(frozen=True)
class ActualPriceStamp:
    plans_stamped: int
    items_priced: int
    items_unavailable: int


def _now(tz: ZoneInfo) -> datetime:
    return datetime.now(tz)


def _deadline(delivery_date: date, settings: Settings) -> datetime:
    hour_text, minute_text = settings.cutoff_time.split(":", maxsplit=1)
    previous = delivery_date - timedelta(days=1)
    tz = ZoneInfo(settings.timezone)
    return datetime(
        previous.year,
        previous.month,
        previous.day,
        int(hour_text),
        int(minute_text),
        tzinfo=tz,
    )


def is_editable(
    delivery_date: date,
    plan_status: PlanStatus | None,
    settings: Settings,
) -> bool:
    """True while now is strictly before the cutoff and the plan is draft or absent."""
    tz = ZoneInfo(settings.timezone)
    now = _now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    clock_open = now < _deadline(delivery_date, settings)
    status_open = plan_status is None or plan_status == PlanStatus.DRAFT
    return clock_open and status_open


def _planned_total(items: list[PlanItem]) -> int:
    return sum(item.planned_price_kopecks * item.qty for item in items)


def _actual_total(items: list[PlanItem], plan_status: PlanStatus) -> int | None:
    if plan_status == PlanStatus.DRAFT:
        return None
    return sum(
        item.actual_price_kopecks * item.qty
        for item in items
        if not item.unavailable and item.actual_price_kopecks is not None
    )


def _to_out(plan: MealPlan, settings: Settings) -> PlanOut:
    items = list(plan.items)
    return PlanOut(
        id=plan.id,
        user_id=plan.user_id,
        delivery_date=plan.delivery_date,
        status=plan.status,
        editable=is_editable(plan.delivery_date, plan.status, settings),
        planned_total_kopecks=_planned_total(items),
        actual_total_kopecks=_actual_total(items, plan.status),
        items=[
            PlanItemOut(
                dish_id=item.dish_id,
                name=item.dish.name,
                qty=item.qty,
                planned_price_kopecks=item.planned_price_kopecks,
                actual_price_kopecks=item.actual_price_kopecks,
                unavailable=item.unavailable,
            )
            for item in items
        ],
    )


def _empty_out(
    *,
    user_id: int,
    delivery_date: date,
    settings: Settings,
) -> PlanOut:
    return PlanOut(
        id=None,
        user_id=user_id,
        delivery_date=delivery_date,
        status=PlanStatus.DRAFT,
        editable=is_editable(delivery_date, None, settings),
        planned_total_kopecks=0,
        actual_total_kopecks=None,
        items=[],
    )


async def _find_plan(
    session: AsyncSession,
    user_id: int,
    delivery_date: date,
    *,
    for_update: bool = False,
) -> MealPlan | None:
    stmt = (
        select(MealPlan)
        .where(
            MealPlan.user_id == user_id,
            MealPlan.delivery_date == delivery_date,
        )
        .options(selectinload(MealPlan.items).selectinload(PlanItem.dish))
    )
    if for_update:
        stmt = stmt.with_for_update(of=MealPlan).execution_options(
            populate_existing=True,
        )
    return await session.scalar(stmt)


async def _subject_user(
    session: AsyncSession,
    actor: User,
    user_id: int | None,
) -> User:
    if user_id is None or user_id == actor.id:
        return actor
    if actor.role == UserRole.EMPLOYEE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    subject = await session.get(User, user_id)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return subject


async def get_plan(
    session: AsyncSession,
    actor: User,
    delivery_date: date,
    user_id: int | None,
) -> PlanOut:
    settings = await get_or_create_settings(session)
    subject = await _subject_user(session, actor, user_id)
    plan = await _find_plan(session, subject.id, delivery_date)
    if plan is None:
        return _empty_out(
            user_id=subject.id,
            delivery_date=delivery_date,
            settings=settings,
        )
    return _to_out(plan, settings)


async def load_editable_employee_plan(
    session: AsyncSession,
    *,
    user: User,
    delivery_date: date,
) -> EditablePlan:
    if user.role != UserRole.EMPLOYEE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    settings = await get_or_create_settings(session)
    plan = await _find_plan(session, user.id, delivery_date, for_update=True)
    plan_status = plan.status if plan is not None else None
    if not is_editable(delivery_date, plan_status, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cutoff passed",
        )
    return EditablePlan(
        session=session,
        user=user,
        plan=plan,
        settings=settings,
        delivery_date=delivery_date,
    )


def _reject_invalid_dishes(
    dish_ids: list[int],
    dishes: dict[int, Dish],
) -> None:
    # Missing outranks unavailable. Within one kind, the smallest dish_id wins.
    failures: list[tuple[int, int, str]] = []
    for dish_id in dish_ids:
        dish = dishes.get(dish_id)
        if dish is None:
            failures.append((0, dish_id, "Dish not found"))
        elif not dish.available:
            failures.append((1, dish_id, "Dish unavailable"))
    if not failures:
        return
    failures.sort()
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=failures[0][2],
    )


async def _load_dishes(
    session: AsyncSession,
    dish_ids: list[int],
) -> dict[int, Dish]:
    if not dish_ids:
        return {}
    rows = await session.scalars(select(Dish).where(Dish.id.in_(dish_ids)))
    return {dish.id: dish for dish in rows.all()}


async def replace_plan(ctx: EditablePlan, body: PlanReplace) -> PlanOut:
    session = ctx.session
    dish_ids = [item.dish_id for item in body.items]
    dishes = await _load_dishes(session, dish_ids)
    _reject_invalid_dishes(dish_ids, dishes)
    total = sum(dishes[item.dish_id].price_kopecks * item.qty for item in body.items)
    await assert_plan_within_limit(
        session,
        user=ctx.user,
        total_kopecks=total,
    )

    plan = ctx.plan
    if plan is None:
        plan = MealPlan(
            user_id=ctx.user.id,
            delivery_date=ctx.delivery_date,
            status=PlanStatus.DRAFT,
        )
        session.add(plan)
        await session.flush()
    else:
        for item in list(plan.items):
            await session.delete(item)
        await session.flush()

    for item in body.items:
        dish = dishes[item.dish_id]
        session.add(
            PlanItem(
                plan_id=plan.id,
                dish_id=dish.id,
                qty=item.qty,
                planned_price_kopecks=dish.price_kopecks,
                actual_price_kopecks=None,
                unavailable=False,
            )
        )
    await session.commit()
    session.expire(plan, ["items"])

    stored = await _find_plan(session, ctx.user.id, ctx.delivery_date)
    assert stored is not None
    return _to_out(stored, ctx.settings)


async def apply_actual_prices(
    session: AsyncSession,
    delivery_date: date,
) -> ActualPriceStamp:
    """Stamp stored catalog prices onto draft and locked plans for one date."""
    stmt = (
        select(MealPlan)
        .where(
            MealPlan.delivery_date == delivery_date,
            MealPlan.status.in_((PlanStatus.DRAFT, PlanStatus.LOCKED)),
        )
        .options(selectinload(MealPlan.items).selectinload(PlanItem.dish))
        .with_for_update(of=MealPlan)
        .execution_options(populate_existing=True)
    )
    plans = list((await session.scalars(stmt)).all())
    items_priced = 0
    items_unavailable = 0
    for plan in plans:
        for item in plan.items:
            dish = item.dish
            if dish.available:
                item.actual_price_kopecks = dish.price_kopecks
                item.unavailable = False
                items_priced += 1
            else:
                item.actual_price_kopecks = None
                item.unavailable = True
                items_unavailable += 1
        plan.status = PlanStatus.PRICED
    await session.commit()
    return ActualPriceStamp(
        plans_stamped=len(plans),
        items_priced=items_priced,
        items_unavailable=items_unavailable,
    )
