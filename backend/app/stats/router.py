from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_procurement
from app.db import get_session
from app.stats.schemas import StatsSummary
from app.stats.service import build_summary
from app.users.models import User

router = APIRouter(prefix="/stats", tags=["stats"])

INVERTED_RANGE_DETAIL = "from is later than to"


@router.get("/summary", response_model=StatsSummary)
async def get_summary(
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
    _user: Annotated[User, Depends(require_procurement)],
    session: Annotated[AsyncSession, Depends(get_session)],
    department_id: int | None = None,
) -> StatsSummary:
    if from_date > to_date:
        raise HTTPException(status_code=422, detail=INVERTED_RANGE_DETAIL)
    return await build_summary(
        session,
        period_from=from_date,
        period_to=to_date,
        department_id=department_id,
    )
