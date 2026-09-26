from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.catalog.models import Dish, PriceHistory
from app.catalog.service import EmptySnapshotError, upsert_catalog
from app.db import SessionLocal
from app.providers import NormalizedDish, parse_html

FIXTURE = Path(__file__).parent / "fixtures" / "mealty_catalog.html"


def _fixture_dishes() -> dict[str, NormalizedDish]:
    return {
        dish.external_id: dish
        for dish in parse_html(FIXTURE.read_text(encoding="utf-8"))
    }


def _pair() -> list[NormalizedDish]:
    dishes = _fixture_dishes()
    return [dishes["875"], dishes["880"]]


async def _history(session, dish_id: int) -> list[PriceHistory]:
    result = await session.scalars(
        select(PriceHistory)
        .where(PriceHistory.dish_id == dish_id)
        .order_by(PriceHistory.id)
    )
    return list(result.all())


async def test_first_snapshot_inserts_cards_with_one_clock() -> None:
    dishes = _pair()
    async with SessionLocal() as session:
        result = await upsert_catalog(session, "mealty", dishes)
        rows = list((await session.scalars(select(Dish).order_by(Dish.id))).all())

    by_external = {row.external_id: row for row in rows}
    assert set(by_external) == {"875", "880"}
    assert result.upserted == 2
    assert result.unavailable == 0
    for dish in dishes:
        row = by_external[dish.external_id]
        assert row.source == "mealty"
        assert row.available is True
        assert row.price_kopecks == dish.price_kopecks
        assert isinstance(row.price_kopecks, int)
        assert row.name == dish.name

    async with SessionLocal() as session:
        history = list((await session.scalars(select(PriceHistory))).all())
    assert len(history) == 2
    assert {row.recorded_at for row in history} == {result.recorded_at}
    assert result.recorded_at.tzinfo is not None
    assert result.recorded_at.isoformat().endswith("+03:00") or (
        "+03:00" in result.recorded_at.isoformat()
    )


async def test_repeat_snapshot_updates_the_same_row() -> None:
    dishes = _fixture_dishes()
    original = dishes["875"]
    async with SessionLocal() as session:
        await upsert_catalog(session, "mealty", [original])
        updated = original.model_copy(
            update={"name": "Новое имя", "price_kopecks": 42000},
        )
        await upsert_catalog(session, "mealty", [updated])
        rows = list(
            (await session.scalars(select(Dish).where(Dish.external_id == "875"))).all()
        )
        assert len(rows) == 1
        assert rows[0].name == "Новое имя"
        assert rows[0].price_kopecks == 42000
        assert rows[0].available is True


async def test_unchanged_price_still_records_history() -> None:
    dish = _fixture_dishes()["875"]
    assert dish.price_kopecks == 41000
    async with SessionLocal() as session:
        await upsert_catalog(session, "mealty", [dish])
        await upsert_catalog(session, "mealty", [dish])
        row = await session.scalar(select(Dish).where(Dish.external_id == "875"))
        assert row is not None
        assert row.price_kopecks == 41000
        history = await _history(session, row.id)
    assert [item.price_kopecks for item in history] == [41000, 41000]
    assert history[0].recorded_at != history[1].recorded_at


async def test_absent_dish_stays_priced_and_repeat_count_is_stable() -> None:
    dishes = _fixture_dishes()
    kept = dishes["875"]
    missing = dishes["880"]
    async with SessionLocal() as session:
        await upsert_catalog(session, "mealty", [kept, missing])
        first = await upsert_catalog(session, "mealty", [kept])
        absent = await session.scalar(select(Dish).where(Dish.external_id == "880"))
        assert absent is not None
        assert first.unavailable == 1
        assert first.upserted == 1
        assert absent.available is False
        assert absent.price_kopecks == missing.price_kopecks
        assert len(await _history(session, absent.id)) == 1

        second = await upsert_catalog(session, "mealty", [kept])
        absent_again = await session.scalar(
            select(Dish).where(Dish.external_id == "880")
        )
        assert absent_again is not None
        assert second.unavailable == 1
        assert absent_again.available is False
        assert absent_again.price_kopecks == missing.price_kopecks
        assert len(await _history(session, absent_again.id)) == 1

        returned = await upsert_catalog(session, "mealty", [kept, missing])

    assert returned.unavailable == 0
    async with SessionLocal() as session:
        back = await session.scalar(select(Dish).where(Dish.external_id == "880"))
        assert back is not None
        assert back.available is True
        assert back.price_kopecks == missing.price_kopecks
        assert len(await _history(session, back.id)) == 2


async def test_empty_snapshot_writes_nothing() -> None:
    dish = _fixture_dishes()["875"]
    async with SessionLocal() as session:
        await upsert_catalog(session, "mealty", [dish])
        with pytest.raises(EmptySnapshotError):
            await upsert_catalog(session, "mealty", [])
        row = await session.scalar(select(Dish).where(Dish.external_id == "875"))
        assert row is not None
        assert row.available is True
        assert row.price_kopecks == dish.price_kopecks
        assert len(await _history(session, row.id)) == 1
        total = await session.scalar(select(func.count()).select_from(Dish))
        assert total == 1


async def test_other_source_is_not_updated_or_counted() -> None:
    async with SessionLocal() as session:
        session.add(
            Dish(
                source="other",
                external_id="9",
                name="Чужое",
                subtitle="",
                category="salad",
                price_kopecks=111,
                available=True,
            )
        )
        session.add(
            Dish(
                source="mealty",
                external_id="999",
                name="Старое",
                subtitle="",
                category="soup",
                price_kopecks=222,
                available=True,
            )
        )
        await session.commit()
        result = await upsert_catalog(session, "mealty", _pair())
        other = await session.scalar(select(Dish).where(Dish.source == "other"))
        stale = await session.scalar(select(Dish).where(Dish.external_id == "999"))
        assert other is not None
        assert stale is not None
        assert result.upserted == 2
        assert result.unavailable == 1
        assert other.available is True
        assert other.price_kopecks == 111
        assert stale.available is False
        assert stale.price_kopecks == 222
        assert await _history(session, other.id) == []
        assert await _history(session, stale.id) == []
