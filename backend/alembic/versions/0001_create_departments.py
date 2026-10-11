"""create departments table

Revision ID: 0001_departments
Revises:
Create Date: 2026-09-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_departments"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("departments")
