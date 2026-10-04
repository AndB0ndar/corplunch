import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["employee", "procurement", "admin"]

_CUTOFF_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class DepartmentCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=255,
    )


class DepartmentUpdate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=255,
    )


class DepartmentOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    email: str
    full_name: str
    role: Role
    department: DepartmentOut | None
    daily_limit_kopecks: int | None
    is_active: bool


class UserCreate(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=320,
    )

    password: str = Field(
        min_length=1,
        max_length=128,
    )

    full_name: str = Field(
        min_length=1,
        max_length=255,
    )

    role: Role

    department_id: int | None = None

    daily_limit_kopecks: int | None = Field(
        default=None,
        ge=0,
    )

    is_active: bool = True


class UserUpdate(BaseModel):
    password: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )

    full_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    role: Role | None = None

    department_id: int | None = None

    daily_limit_kopecks: int | None = Field(
        default=None,
        ge=0,
    )

    is_active: bool | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class MeResponse(UserOut):
    pass


class SettingsOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    cutoff_time: str
    timezone: str
    mealty_city: str
    daily_limit_kopecks: int | None
    catalog_sync_per_day: int


class SettingsUpdate(BaseModel):
    cutoff_time: str
    timezone: str = Field(min_length=1, max_length=64)
    mealty_city: str = Field(min_length=1, max_length=128)
    daily_limit_kopecks: int | None = Field(default=None, ge=0)
    catalog_sync_per_day: int = Field(ge=0, le=100)

    @field_validator("cutoff_time")
    @classmethod
    def validate_cutoff_time(cls, value: str) -> str:
        if not _CUTOFF_RE.match(value):
            raise ValueError("cutoff_time must be HH:MM (24h)")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value
