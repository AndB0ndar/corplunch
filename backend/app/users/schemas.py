from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Role = Literal["employee", "procurement", "admin"]


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
