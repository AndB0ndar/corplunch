import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )


async def _reset_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


async def _public_tables() -> set[str]:
    async with engine.connect() as conn:
        return set(
            (
                await conn.execute(
                    text(
                        "SELECT tablename FROM pg_catalog.pg_tables "
                        "WHERE schemaname = 'public'"
                    )
                )
            ).scalars()
        )


@pytest.mark.migration
async def test_alembic_creates_required_tables() -> None:
    await _reset_schema()

    result = _alembic("upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr

    tables = await _public_tables()

    assert "departments" in tables
    assert "users" in tables
    assert "dishes" in tables
    assert "price_history" in tables
    assert "settings" in tables
    assert "catalog_sync_runs" in tables
    assert "meal_plans" in tables
    assert "plan_items" in tables
    assert "office_orders" in tables
    assert "office_order_items" in tables
    assert "alembic_version" in tables

    async with engine.connect() as conn:
        meal_columns = set(
            (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'meal_plans'"
                    )
                )
            ).scalars()
        )
        constraint_names = set(
            (
                await conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint WHERE conname IN ("
                        "'uq_meal_plans_user_id_delivery_date', "
                        "'uq_plan_items_plan_id_dish_id', "
                        "'ck_plan_items_qty_min', "
                        "'uq_office_orders_delivery_date', "
                        "'uq_office_order_items_office_order_id_dish_id', "
                        "'ck_office_order_items_qty_min')"
                    )
                )
            ).scalars()
        )
        status_index = await conn.scalar(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE indexname = 'ix_meal_plans_delivery_date_status'"
            )
        )
        office_index = await conn.scalar(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE indexname = 'ix_meal_plans_office_order_id'"
            )
        )

    assert "office_order_id" in meal_columns
    assert constraint_names == {
        "uq_meal_plans_user_id_delivery_date",
        "uq_plan_items_plan_id_dish_id",
        "ck_plan_items_qty_min",
        "uq_office_orders_delivery_date",
        "uq_office_order_items_office_order_id_dish_id",
        "ck_office_order_items_qty_min",
    }
    assert status_index == 1
    assert office_index == 1


@pytest.mark.migration
async def test_alembic_0006_downgrade_drops_office_tables() -> None:
    await _reset_schema()

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert {"office_orders", "office_order_items"} <= await _public_tables()

    down = _alembic("downgrade", "0005")
    assert down.returncode == 0, down.stdout + down.stderr

    tables = await _public_tables()
    async with engine.connect() as conn:
        meal_columns = set(
            (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'meal_plans'"
                    )
                )
            ).scalars()
        )

    assert "office_orders" not in tables
    assert "office_order_items" not in tables
    assert "meal_plans" in tables
    assert "plan_items" in tables
    assert "office_order_id" not in meal_columns

    reup = _alembic("upgrade", "head")
    assert reup.returncode == 0, reup.stdout + reup.stderr
    assert {"office_orders", "office_order_items"} <= await _public_tables()
