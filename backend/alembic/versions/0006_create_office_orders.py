"""create office_orders and office_order_items

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    order_status = sa.Enum(
        "collecting",
        "locked",
        "exported",
        "placed",
        name="office_order_status",
        native_enum=False,
    )
    op.create_table(
        "office_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("status", order_status, nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "placed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "delivery_date",
            name="uq_office_orders_delivery_date",
        ),
    )
    op.create_table(
        "office_order_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "office_order_id",
            sa.Integer(),
            sa.ForeignKey("office_orders.id"),
            nullable=False,
        ),
        sa.Column("dish_id", sa.Integer(), sa.ForeignKey("dishes.id"), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("unit_price_kopecks", sa.Integer(), nullable=False),
        sa.Column("line_total_kopecks", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "office_order_id",
            "dish_id",
            name="uq_office_order_items_office_order_id_dish_id",
        ),
        sa.CheckConstraint("qty >= 1", name="ck_office_order_items_qty_min"),
    )
    op.add_column(
        "meal_plans",
        sa.Column("office_order_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_meal_plans_office_order_id_office_orders",
        "meal_plans",
        "office_orders",
        ["office_order_id"],
        ["id"],
    )
    op.create_index(
        "ix_meal_plans_office_order_id",
        "meal_plans",
        ["office_order_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_meal_plans_office_order_id", table_name="meal_plans")
    op.drop_constraint(
        "fk_meal_plans_office_order_id_office_orders",
        "meal_plans",
        type_="foreignkey",
    )
    op.drop_column("meal_plans", "office_order_id")
    op.drop_table("office_order_items")
    op.drop_table("office_orders")
