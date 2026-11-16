"""Deterministic live stats data; run ONLY through tests/.env.test Compose.

Creates new rows without deleting existing data. No provider/network calls.
The manifest on stdout contains IDs/dates for Playwright, never credentials.
"""

import asyncio
import json
from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.catalog.models import Dish
from app.config import settings
from app.db import SessionLocal, engine
from app.orders.models import OfficeOrder, OfficeOrderItem, OfficeOrderStatus
from app.planning.models import MealPlan, PlanItem, PlanStatus
from app.users.models import Department, User, UserRole


async def main() -> None:
    url = make_url(settings.database_url)
    if (
        settings.jwt_secret != "local-tests-only-not-for-deployment"
        or url.host != "db"
        or url.database != "corplunch"
    ):
        raise RuntimeError("Use only docker compose --env-file tests/.env.test")
    async with SessionLocal() as session:
        day = date(2040, 1, 10)
        while True:
            end = day + timedelta(days=3)
            occupied = await session.scalar(
                select(MealPlan.id)
                .where(MealPlan.delivery_date.between(day, end))
                .limit(1)
            )
            order = await session.scalar(
                select(OfficeOrder.id)
                .where(OfficeOrder.delivery_date.between(day, end))
                .limit(1)
            )
            if occupied is None and order is None:
                break
            day += timedelta(days=4)
        run = uuid4().hex[:10]
        departments = [Department(name=f"QA Статистика {i} {run}") for i in (1, 2)]
        session.add_all(departments)
        await session.flush()
        users = [
            User(
                email=f"stats-{run}-{i}@qa.local",
                password_hash="!",
                full_name=f"QA Статистика сотрудник {i}",
                role=UserRole.EMPLOYEE,
                department_id=departments[i - 1].id if i < 3 else None,
                is_active=False,
            )
            for i in (1, 2, 3)
        ]
        dishes = [
            Dish(
                source="mealty",
                external_id=f"stats-{run}-{i}",
                name=name,
                subtitle="",
                category="main_dish",
                price_kopecks=price,
                available=False,
            )
            for i, (name, price) in enumerate(
                [
                    ("QA Обед подорожал", 42500),
                    ("QA Обед подешевел", 27000),
                    ("QA Снятое блюдо", 36000),
                ]
            )
        ]
        session.add_all([*users, *dishes])
        await session.flush()
        orders = [
            OfficeOrder(delivery_date=day + timedelta(days=i), status=status)
            for i, status in enumerate(
                [OfficeOrderStatus.LOCKED, OfficeOrderStatus.PLACED]
            )
        ]
        session.add_all(orders)
        await session.flush()

        async def plan(
            user: int,
            offset: int,
            rows: list[tuple[int, int, int, int | None]],
            status: PlanStatus = PlanStatus.INCLUDED_IN_ORDER,
        ) -> None:
            record = MealPlan(
                user_id=users[user].id,
                delivery_date=day + timedelta(days=offset),
                status=status,
                office_order_id=orders[offset].id
                if status == PlanStatus.INCLUDED_IN_ORDER
                else None,
            )
            session.add(record)
            await session.flush()
            session.add_all(
                [
                    PlanItem(
                        plan_id=record.id,
                        dish_id=dishes[dish].id,
                        qty=qty,
                        planned_price_kopecks=planned,
                        actual_price_kopecks=actual,
                        unavailable=actual is None,
                    )
                    for dish, qty, planned, actual in rows
                ]
            )

        await plan(0, 0, [(0, 2, 41000, 42500), (2, 3, 36000, None)])
        await plan(1, 0, [(1, 1, 30000, 27000)])
        await plan(2, 0, [(2, 1, 36000, None)])
        await plan(0, 1, [(0, 1, 41000, 42500)])
        await plan(1, 1, [(1, 2, 30000, 27000)])
        await plan(2, 1, [(0, 5, 41000, 42500)], PlanStatus.LOCKED)
        await plan(0, 2, [(0, 5, 41000, 42500)], PlanStatus.DRAFT)
        await plan(1, 2, [(0, 5, 41000, 42500)], PlanStatus.PRICED)
        for index, quantities in enumerate([(2, 1), (1, 2)]):
            for dish_index, qty in enumerate(quantities):
                price = [42500, 27000][dish_index]
                session.add(
                    OfficeOrderItem(
                        office_order_id=orders[index].id,
                        dish_id=dishes[dish_index].id,
                        qty=qty,
                        unit_price_kopecks=price,
                        line_total_kopecks=qty * price,
                    )
                )
        await session.commit()
        print(
            json.dumps(
                {
                    "from": day.isoformat(),
                    "to": (day + timedelta(days=2)).isoformat(),
                    "second_day": (day + timedelta(days=1)).isoformat(),
                    "empty_day": end.isoformat(),
                    "departments": [{"id": d.id, "name": d.name} for d in departments],
                    "users": [{"id": u.id, "name": u.full_name} for u in users],
                    "dishes": [d.id for d in dishes],
                },
                ensure_ascii=False,
            )
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
