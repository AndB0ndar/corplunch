from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_procurement
from app.db import get_session
from app.orders.models import OfficeOrderStatus
from app.orders.schemas import CutoffOut, OrderSummary, PlaceOut
from app.orders.service import (
    DAY_STILL_COLLECTING_DETAIL,
    CutoffOutcome,
    DayStillCollecting,
    ExportKind,
    build_export,
    build_order_summary,
    place_order,
    run_cutoff,
)
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


@router.get("/{delivery_date}", response_model=OrderSummary)
async def get_order(
    delivery_date: date,
    _user: Annotated[User, Depends(require_procurement)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderSummary:
    return await build_order_summary(session, delivery_date)


@router.post("/{delivery_date}/place", response_model=PlaceOut)
async def place_day(
    delivery_date: date,
    user: Annotated[User, Depends(require_procurement)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlaceOut:
    try:
        return await place_order(session, delivery_date, user.id)
    except DayStillCollecting:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=DAY_STILL_COLLECTING_DETAIL,
        ) from None


@router.get("/{delivery_date}/export.csv")
async def export_csv(
    delivery_date: date,
    _user: Annotated[User, Depends(require_procurement)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    return await _export_file(delivery_date, "csv", session)


@router.get("/{delivery_date}/export.xlsx")
async def export_xlsx(
    delivery_date: date,
    _user: Annotated[User, Depends(require_procurement)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    return await _export_file(delivery_date, "xlsx", session)


async def _export_file(
    delivery_date: date,
    kind: ExportKind,
    session: AsyncSession,
) -> Response:
    try:
        exported = await build_export(session, delivery_date, kind)
    except DayStillCollecting:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=DAY_STILL_COLLECTING_DETAIL,
        ) from None
    return Response(
        content=exported.body,
        media_type=exported.media_type,
        headers={
            "Content-Disposition": (f'attachment; filename="{exported.filename}"'),
        },
    )
