from __future__ import annotations

import enum
from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.catalog.models import Dish
from app.db import Base


class PlanStatus(enum.StrEnum):
    DRAFT = "draft"
    LOCKED = "locked"
    PRICED = "priced"
    INCLUDED_IN_ORDER = "included_in_order"


class MealPlan(Base):
    __tablename__ = "meal_plans"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "delivery_date",
            name="uq_meal_plans_user_id_delivery_date",
        ),
        Index(
            "ix_meal_plans_delivery_date_status",
            "delivery_date",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PlanStatus] = mapped_column(
        Enum(
            PlanStatus,
            name="plan_status",
            native_enum=False,
        ),
        nullable=False,
    )

    items: Mapped[list[PlanItem]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="PlanItem.id",
        lazy="selectin",
    )


class PlanItem(Base):
    __tablename__ = "plan_items"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "dish_id",
            name="uq_plan_items_plan_id_dish_id",
        ),
        CheckConstraint("qty >= 1", name="ck_plan_items_qty_min"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("meal_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_price_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_price_kopecks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unavailable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    plan: Mapped[MealPlan] = relationship(back_populates="items")
    dish: Mapped[Dish] = relationship(Dish, lazy="selectin")
