import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.migration
async def test_alembic_creates_required_tables() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr

    async with engine.connect() as conn:
        tables = set(
            (
                await conn.execute(
                    text(
                        "SELECT tablename FROM pg_catalog.pg_tables "
                        "WHERE schemaname = 'public'"
                    )
                )
            ).scalars()
        )

    assert "departments" in tables
    assert "users" in tables
    assert "dishes" in tables
    assert "price_history" in tables
    assert "settings" in tables
    assert "catalog_sync_runs" in tables
    assert "meal_plans" in tables
    assert "plan_items" in tables
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
                        "'ck_plan_items_qty_min')"
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

    assert "office_order_id" not in meal_columns
    assert constraint_names == {
        "uq_meal_plans_user_id_delivery_date",
        "uq_plan_items_plan_id_dish_id",
        "ck_plan_items_qty_min",
    }
    assert status_index == 1
