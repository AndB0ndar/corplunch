"""Read-only period report over plans already included in an office order."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.planning.models import MealPlan, PlanItem, PlanStatus
from app.stats.schemas import (
    DepartmentStats,
    EmployeeStats,
    PriceChange,
    StatsSummary,
    TopDish,
)
from app.users.models import User


@dataclass
class _EmployeeBucket:
    full_name: str
    actual_kopecks: int = 0
    order_count: int = 0


@dataclass
class _DepartmentBucket:
    name: str
    actual_kopecks: int = 0
    order_count: int = 0


@dataclass
class _DishBucket:
    name: str
    qty: int = 0
    actual_kopecks: int = 0


@dataclass
class _Accum:
    planned: int = 0
    actual: int = 0
    unavailable_count: int = 0
    employees: dict[int, _EmployeeBucket] = field(default_factory=dict)
    departments: dict[int, _DepartmentBucket] = field(default_factory=dict)
    dishes: dict[int, _DishBucket] = field(default_factory=dict)
    price_changes: dict[tuple[int, int, int], str] = field(default_factory=dict)


async def build_summary(
    session: AsyncSession,
    *,
    period_from: date,
    period_to: date,
    department_id: int | None = None,
) -> StatsSummary:
    """Aggregate included plans. Does not write, cut off, or read price history."""
    plans = await _included_plans(session, period_from, period_to)
    users = await _users_by_id(session, [plan.user_id for plan in plans])
    if department_id is not None:
        plans = [
            plan for plan in plans if users[plan.user_id].department_id == department_id
        ]
    totals = _accumulate(plans, users)
    return _to_summary(period_from, period_to, totals)


async def _included_plans(
    session: AsyncSession,
    period_from: date,
    period_to: date,
) -> list[MealPlan]:
    return list(
        (
            await session.scalars(
                select(MealPlan)
                .where(
                    MealPlan.status == PlanStatus.INCLUDED_IN_ORDER,
                    MealPlan.delivery_date >= period_from,
                    MealPlan.delivery_date <= period_to,
                )
                .options(selectinload(MealPlan.items).selectinload(PlanItem.dish))
            )
        ).all()
    )


async def _users_by_id(
    session: AsyncSession,
    user_ids: list[int],
) -> dict[int, User]:
    if not user_ids:
        return {}
    rows = (
        await session.scalars(
            select(User)
            .where(User.id.in_(set(user_ids)))
            .options(selectinload(User.department))
        )
    ).all()
    return {user.id: user for user in rows}


def _accumulate(plans: list[MealPlan], users: dict[int, User]) -> _Accum:
    totals = _Accum()
    for plan in plans:
        user = users[plan.user_id]
        employee = totals.employees.setdefault(
            user.id,
            _EmployeeBucket(full_name=user.full_name),
        )
        employee.order_count += 1
        department = _department_bucket(totals, user)
        if department is not None:
            department.order_count += 1
        for item in plan.items:
            _add_item(totals, employee, department, item)
    return totals


def _department_bucket(totals: _Accum, user: User) -> _DepartmentBucket | None:
    if user.department_id is None or user.department is None:
        return None
    return totals.departments.setdefault(
        user.department_id,
        _DepartmentBucket(name=user.department.name),
    )


def _add_item(
    totals: _Accum,
    employee: _EmployeeBucket,
    department: _DepartmentBucket | None,
    item: PlanItem,
) -> None:
    if item.unavailable:
        totals.unavailable_count += 1
        return
    planned_line = item.planned_price_kopecks * item.qty
    actual_unit = item.actual_price_kopecks
    # Closed-day actuals skip a missing stamp; do not invent a price.
    actual_line = 0 if actual_unit is None else actual_unit * item.qty
    totals.planned += planned_line
    totals.actual += actual_line
    employee.actual_kopecks += actual_line
    if department is not None:
        department.actual_kopecks += actual_line
    dish = totals.dishes.setdefault(
        item.dish_id,
        _DishBucket(name=item.dish.name),
    )
    dish.qty += item.qty
    dish.actual_kopecks += actual_line
    if actual_unit is not None and item.planned_price_kopecks != actual_unit:
        totals.price_changes[
            (item.dish_id, item.planned_price_kopecks, actual_unit)
        ] = item.dish.name


def _to_summary(period_from: date, period_to: date, totals: _Accum) -> StatsSummary:
    by_department = [
        DepartmentStats(
            department_id=department_id,
            name=bucket.name,
            actual_kopecks=bucket.actual_kopecks,
            order_count=bucket.order_count,
        )
        for department_id, bucket in totals.departments.items()
    ]
    by_department.sort(key=lambda row: (row.name, row.department_id))
    by_employee = [
        EmployeeStats(
            user_id=user_id,
            full_name=bucket.full_name,
            actual_kopecks=bucket.actual_kopecks,
            order_count=bucket.order_count,
        )
        for user_id, bucket in totals.employees.items()
    ]
    by_employee.sort(key=lambda row: (row.full_name, row.user_id))
    top_dishes = [
        TopDish(
            dish_id=dish_id,
            name=bucket.name,
            qty=bucket.qty,
            actual_kopecks=bucket.actual_kopecks,
        )
        for dish_id, bucket in totals.dishes.items()
    ]
    top_dishes.sort(key=lambda row: (-row.qty, -row.actual_kopecks, row.dish_id))
    price_changes = [
        PriceChange(
            dish_id=dish_id,
            name=name,
            planned_price_kopecks=planned,
            actual_price_kopecks=actual,
        )
        for (dish_id, planned, actual), name in totals.price_changes.items()
    ]
    price_changes.sort(
        key=lambda row: (
            row.name,
            row.dish_id,
            row.planned_price_kopecks,
            row.actual_price_kopecks,
        )
    )
    return StatsSummary(
        period_from=period_from,
        to=period_to,
        total_planned_kopecks=totals.planned,
        total_actual_kopecks=totals.actual,
        delta_kopecks=totals.actual - totals.planned,
        unavailable_count=totals.unavailable_count,
        by_department=by_department,
        by_employee=by_employee,
        top_dishes=top_dishes,
        price_changes=price_changes,
    )
