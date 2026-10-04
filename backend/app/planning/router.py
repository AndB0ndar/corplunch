from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.db import get_session
from app.planning.schemas import PlanOut, PlanReplace
from app.planning.service import (
    EditablePlan,
    get_plan,
    load_editable_employee_plan,
    replace_plan,
)

router = APIRouter(prefix="/plans", tags=["plans"])


async def editable_employee_plan(
    delivery_date: date,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EditablePlan:
    return await load_editable_employee_plan(
        session,
        user=user,
        delivery_date=delivery_date,
    )


@router.get("/{delivery_date}", response_model=PlanOut)
async def read_plan(
    delivery_date: date,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: int | None = None,
) -> PlanOut:
    return await get_plan(session, user, delivery_date, user_id)


@router.put("/{delivery_date}", response_model=PlanOut)
async def put_plan(
    ctx: Annotated[EditablePlan, Depends(editable_employee_plan)],
    body: PlanReplace,
) -> PlanOut:
    return await replace_plan(ctx, body)
