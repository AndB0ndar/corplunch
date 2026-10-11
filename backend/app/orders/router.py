from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_procurement
from app.db import get_session
from app.orders.models import OfficeOrderStatus
from app.orders.schemas import CutoffOut
from app.orders.service import CutoffOutcome, run_cutoff
from app.users.models import User

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/{delivery_date}/cutoff", response_model=CutoffOut)
async def cutoff_day(
    delivery_date: date,
    _user: Annotated[User, Depends(require_procurement)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CutoffOut:
    result = await run_cutoff(session, delivery_date)
    if result.outcome == CutoffOutcome.NOTHING_TO_CLOSE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty day",
        )
    return CutoffOut(
        delivery_date=result.delivery_date,
        # Fallback is unreachable: both remaining outcomes carry a status.
        status=result.order_status or OfficeOrderStatus.LOCKED,
        already_closed=result.already_closed,
        sync=result.sync,
        plans_closed=result.plans_closed,
        items_unavailable=result.items_unavailable,
    )
