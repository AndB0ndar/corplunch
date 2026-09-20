import bcrypt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.db import get_session
from app.users.models import Department, User, UserRole
from app.users.schemas import (
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(
    session: AsyncSession = Depends(get_session),
) -> list[Department]:
    result = await session.execute(
        select(Department).order_by(Department.id)
    )

    return list(result.scalars().all())


@router.post(
    "/departments",
    response_model=DepartmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_department(
    payload: DepartmentCreate,
    session: AsyncSession = Depends(get_session),
) -> Department:
    department = Department(
        name=payload.name,
    )

    session.add(department)

    await session.commit()
    await session.refresh(department)

    return department


@router.patch("/departments/{department_id}", response_model=DepartmentOut)
async def update_department(
    department_id: int,
    payload: DepartmentUpdate,
    session: AsyncSession = Depends(get_session),
) -> Department:
    department = await session.get(
        Department,
        department_id,
    )

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    department.name = payload.name

    await session.commit()
    await session.refresh(department)

    return department


@router.get("/users", response_model=list[UserOut])
async def list_users(
    session: AsyncSession = Depends(get_session),
) -> list[User]:
    result = await session.execute(
        select(User).order_by(User.id)
    )

    return list(result.scalars().all())


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> User:
    email = payload.email.strip().lower()

    existing = await session.scalar(
        select(User).where(User.email == email)
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    if payload.department_id is not None:
        department = await session.get(
            Department,
            payload.department_id,
        )

        if department is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found",
            )

    password_hash = bcrypt.hashpw(
        payload.password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    user = User(
        email=email,
        password_hash=password_hash,
        full_name=payload.full_name,
        role=UserRole(payload.role),
        department_id=payload.department_id,
        daily_limit_kopecks=payload.daily_limit_kopecks,
        is_active=payload.is_active,
    )

    session.add(user)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        ) from None

    await session.refresh(user)

    return user


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await session.get(
        User,
        user_id,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    fields = payload.model_fields_set

    if "full_name" in fields:
        user.full_name = payload.full_name

    if "role" in fields and payload.role is not None:
        user.role = UserRole(payload.role)

    if "department_id" in fields:
        if payload.department_id is not None:
            department = await session.get(
                Department,
                payload.department_id,
            )

            if department is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Department not found",
                )

        user.department_id = payload.department_id

    if "daily_limit_kopecks" in fields:
        user.daily_limit_kopecks = payload.daily_limit_kopecks

    if "is_active" in fields and payload.is_active is not None:
        user.is_active = payload.is_active

    if "password" in fields and payload.password is not None:
        user.password_hash = bcrypt.hashpw(
            payload.password.encode("utf-8"),
            bcrypt.gensalt(),
        ).decode("utf-8")

    await session.commit()
    await session.refresh(user)

    return user
