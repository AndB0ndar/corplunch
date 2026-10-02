"""create settings and catalog_sync_runs

Revision ID: 0004_settings
Revises: 0003_catalog
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_settings"
down_revision: str | None = "0003_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("cutoff_time", sa.String(length=5), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("mealty_city", sa.String(length=128), nullable=False),
        sa.Column("daily_limit_kopecks", sa.Integer(), nullable=True),
        sa.Column("catalog_sync_per_day", sa.Integer(), nullable=False),
    )
    op.execute(
        sa.text(
            "INSERT INTO settings "
            "(id, cutoff_time, timezone, mealty_city, "
            "daily_limit_kopecks, catalog_sync_per_day) "
            "VALUES (1, '16:00', 'Europe/Moscow', 'Москва', NULL, 2)"
        )
    )
    op.create_table(
        "catalog_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_catalog_sync_runs_ran_at",
        "catalog_sync_runs",
        ["ran_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalog_sync_runs_ran_at",
        table_name="catalog_sync_runs",
    )
    op.drop_table("catalog_sync_runs")
    op.drop_table("settings")
