"""Persist a provider snapshot into dishes and price_history."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Dish, PriceHistory
from app.providers.base import NormalizedDish

MOSCOW = ZoneInfo("Europe/Moscow")


class EmptySnapshotError(Exception):
    """An empty snapshot must not change the menu."""


@dataclass(frozen=True, slots=True)
class CatalogSyncResult:
    upserted: int
    unavailable: int
    recorded_at: datetime


async def upsert_catalog(
    session: AsyncSession,
    source: str,
    dishes: list[NormalizedDish],
) -> CatalogSyncResult:
    if not dishes:
        raise EmptySnapshotError("Empty catalog snapshot")

    recorded_at = datetime.now(MOSCOW)
    external_ids = [dish.external_id for dish in dishes]
    try:
        id_by_external = await _upsert_dishes(session, source, dishes)
        await _append_history(session, dishes, id_by_external, recorded_at)
        await _mark_absent(session, source, external_ids)
        unavailable = await _count_absent(session, source, external_ids)
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return CatalogSyncResult(
        upserted=len(dishes),
        unavailable=int(unavailable or 0),
        recorded_at=recorded_at,
    )


async def _upsert_dishes(
    session: AsyncSession,
    source: str,
    dishes: list[NormalizedDish],
) -> dict[str, int]:
    stmt = insert(Dish).values(
        [_dish_values(source, dish) for dish in dishes],
    )
    excluded = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        constraint="uq_dishes_source_external_id",
        set_={
            "seller_product_id": excluded.seller_product_id,
            "name": excluded.name,
            "subtitle": excluded.subtitle,
            "description": excluded.description,
            "category": excluded.category,
            "price_kopecks": excluded.price_kopecks,
            "old_price_kopecks": excluded.old_price_kopecks,
            "weight_g": excluded.weight_g,
            "proteins": excluded.proteins,
            "fats": excluded.fats,
            "carbs": excluded.carbs,
            "calories": excluded.calories,
            "image_url": excluded.image_url,
            "available": True,
        },
    ).returning(Dish.id, Dish.external_id)
    result = await session.execute(stmt)
    return {external_id: dish_id for dish_id, external_id in result.all()}


def _dish_values(source: str, dish: NormalizedDish) -> dict[str, object]:
    return {
        "source": source,
        "external_id": dish.external_id,
        "seller_product_id": dish.seller_product_id,
        "name": dish.name,
        "subtitle": dish.subtitle,
        "description": dish.description,
        "category": dish.category,
        "price_kopecks": dish.price_kopecks,
        "old_price_kopecks": dish.old_price_kopecks,
        "weight_g": dish.weight_g,
        "proteins": dish.proteins,
        "fats": dish.fats,
        "carbs": dish.carbs,
        "calories": dish.calories,
        "image_url": dish.image_url,
        "available": True,
    }


async def _append_history(
    session: AsyncSession,
    dishes: list[NormalizedDish],
    id_by_external: dict[str, int],
    recorded_at: datetime,
) -> None:
    await session.execute(
        insert(PriceHistory).values(
            [
                {
                    "dish_id": id_by_external[dish.external_id],
                    "price_kopecks": dish.price_kopecks,
                    "recorded_at": recorded_at,
                }
                for dish in dishes
            ]
        )
    )


async def _mark_absent(
    session: AsyncSession,
    source: str,
    external_ids: list[str],
) -> None:
    await session.execute(
        update(Dish)
        .where(
            Dish.source == source,
            Dish.external_id.not_in(external_ids),
        )
        .values(available=False)
    )


async def _count_absent(
    session: AsyncSession,
    source: str,
    external_ids: list[str],
) -> int | None:
    return await session.scalar(
        select(func.count())
        .select_from(Dish)
        .where(
            Dish.source == source,
            Dish.external_id.not_in(external_ids),
        )
    )
