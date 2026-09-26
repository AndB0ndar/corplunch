"""create dishes and price_history

Revision ID: 0003_catalog
Revises: 0002_users
Create Date: 2026-09-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_catalog"
down_revision: str | None = "0002_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dishes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("seller_product_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("price_kopecks", sa.Integer(), nullable=False),
        sa.Column("old_price_kopecks", sa.Integer(), nullable=True),
        sa.Column("weight_g", sa.Integer(), nullable=True),
        sa.Column("proteins", sa.Numeric(12, 2), nullable=True),
        sa.Column("fats", sa.Numeric(12, 2), nullable=True),
        sa.Column("carbs", sa.Numeric(12, 2), nullable=True),
        sa.Column("calories", sa.Numeric(12, 2), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.UniqueConstraint(
            "source",
            "external_id",
            name="uq_dishes_source_external_id",
        ),
    )
    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "dish_id",
            sa.Integer(),
            sa.ForeignKey("dishes.id"),
            nullable=False,
        ),
        sa.Column("price_kopecks", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_price_history_dish_id_recorded_at",
        "price_history",
        ["dish_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_price_history_dish_id_recorded_at",
        table_name="price_history",
    )
    op.drop_table("price_history")
    op.drop_table("dishes")
