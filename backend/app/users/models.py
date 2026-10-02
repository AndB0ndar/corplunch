import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UserRole(enum.StrEnum):
    EMPLOYEE = "employee"
    PROCUREMENT = "procurement"
    ADMIN = "admin"


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
        ),
        nullable=False,
    )

    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id"),
        nullable=True,
    )

    daily_limit_kopecks: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    department: Mapped[Department | None] = relationship(
        lazy="selectin",
    )


class Settings(Base):
    """Singleton app settings row (id=1)."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)

    cutoff_time: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="16:00",
    )

    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Europe/Moscow",
    )

    mealty_city: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="Москва",
    )

    daily_limit_kopecks: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )

    catalog_sync_per_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
    )


class CatalogSyncRun(Base):
    """One row per live Mealty sync attempt that passed the quota gate."""

    __tablename__ = "catalog_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
