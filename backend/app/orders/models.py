from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class OfficeOrderStatus(enum.StrEnum):
    COLLECTING = "collecting"
    LOCKED = "locked"
    EXPORTED = "exported"
    PLACED = "placed"


class OfficeOrder(Base):
    __tablename__ = "office_orders"
    __table_args__ = (
        UniqueConstraint(
            "delivery_date",
            name="uq_office_orders_delivery_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[OfficeOrderStatus] = mapped_column(
        Enum(
            OfficeOrderStatus,
            name="office_order_status",
            native_enum=False,
        ),
        nullable=False,
    )
    placed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    placed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    items: Mapped[list[OfficeOrderItem]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OfficeOrderItem.id",
        lazy="selectin",
    )


class OfficeOrderItem(Base):
    __tablename__ = "office_order_items"
    __table_args__ = (
        UniqueConstraint(
            "office_order_id",
            "dish_id",
            name="uq_office_order_items_office_order_id_dish_id",
        ),
        CheckConstraint("qty >= 1", name="ck_office_order_items_qty_min"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    office_order_id: Mapped[int] = mapped_column(
        ForeignKey("office_orders.id"),
        nullable=False,
    )
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped[OfficeOrder] = relationship(back_populates="items")
