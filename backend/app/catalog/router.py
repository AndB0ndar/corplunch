from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, require_procurement
from app.catalog.models import Dish
from app.catalog.schemas import CatalogSyncOut, DishOut
from app.catalog.service import upsert_catalog
from app.db import get_session
from app.providers.mealty import MealtyError, MealtyProvider
from app.users.models import User
from app.users.quota import assert_catalog_sync_allowed

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _like_contains(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("", response_model=list[DishOut])
async def list_catalog(
    _user: CurrentUser,
    category: str | None = None,
    q: str | None = None,
    available_only: bool = True,
    session: AsyncSession = Depends(get_session),
) -> list[Dish]:
    stmt = select(Dish).order_by(Dish.id)
    if category is not None:
        stmt = stmt.where(Dish.category == category)
    if q:
        stmt = stmt.where(Dish.name.ilike(_like_contains(q), escape="\\"))
    if available_only:
        stmt = stmt.where(Dish.available.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("/sync", response_model=CatalogSyncOut)
async def sync_catalog(
    _user: Annotated[User, Depends(require_procurement)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CatalogSyncOut:
    await assert_catalog_sync_allowed()
    provider = MealtyProvider()
    try:
        dishes = await provider.fetch_catalog()
    except MealtyError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    result = await upsert_catalog(session, provider.source, dishes)
    return CatalogSyncOut(
        upserted=result.upserted,
        unavailable=result.unavailable,
        recorded_at=result.recorded_at,
    )
