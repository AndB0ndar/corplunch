"""create meal_plans and plan_items

Revision ID: 0005
Revises: 0004_settings
Create Date: 2026-10-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    plan_status = sa.Enum(
        "draft",
        "locked",
        "priced",
        "included_in_order",
        name="plan_status",
        native_enum=False,
    )
    op.create_table(
        "meal_plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("status", plan_status, nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "delivery_date",
            name="uq_meal_plans_user_id_delivery_date",
        ),
    )
    op.create_index(
        "ix_meal_plans_delivery_date_status",
        "meal_plans",
        ["delivery_date", "status"],
    )
    op.create_table(
        "plan_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("meal_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dish_id", sa.Integer(), sa.ForeignKey("dishes.id"), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("planned_price_kopecks", sa.Integer(), nullable=False),
        sa.Column("actual_price_kopecks", sa.Integer(), nullable=True),
        sa.Column(
            "unavailable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.UniqueConstraint(
            "plan_id",
            "dish_id",
            name="uq_plan_items_plan_id_dish_id",
        ),
        sa.CheckConstraint("qty >= 1", name="ck_plan_items_qty_min"),
    )


def downgrade() -> None:
    op.drop_table("plan_items")
    op.drop_table("meal_plans")
