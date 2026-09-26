from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Dish(Base):
    __tablename__ = "dishes"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "external_id",
            name="uq_dishes_source_external_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    seller_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    price_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    old_price_kopecks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proteins: Mapped[float | None] = mapped_column(
        Numeric(12, 2, asdecimal=False),
        nullable=True,
    )
    fats: Mapped[float | None] = mapped_column(
        Numeric(12, 2, asdecimal=False),
        nullable=True,
    )
    carbs: Mapped[float | None] = mapped_column(
        Numeric(12, 2, asdecimal=False),
        nullable=True,
    )
    calories: Mapped[float | None] = mapped_column(
        Numeric(12, 2, asdecimal=False),
        nullable=True,
    )
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        Index(
            "ix_price_history_dish_id_recorded_at",
            "dish_id",
            "recorded_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), nullable=False)
    price_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
