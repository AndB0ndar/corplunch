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
    assert "alembic_version" in tables
