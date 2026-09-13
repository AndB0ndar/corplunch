from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.db import get_session
from app.users.models import Department
from app.users.schemas import DepartmentCreate, DepartmentOut

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(
    session: AsyncSession = Depends(get_session),
) -> list[Department]:
    result = await session.execute(select(Department).order_by(Department.id))
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
    department = Department(name=payload.name)
    session.add(department)
    await session.commit()
    await session.refresh(department)
    return department
