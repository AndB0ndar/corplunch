from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select

from app.catalog.models import Dish, PriceHistory
from app.db import SessionLocal
from app.jobs.catalog import run_catalog_sync
from app.jobs.scheduler import CATALOG_SYNC_JOB_ID, create_scheduler
from app.providers import MealtyError, NormalizedDish, parse_html

FIXTURE = Path(__file__).parent / "fixtures" / "mealty_catalog.html"
MOSCOW = ZoneInfo("Europe/Moscow")


def _parsed_fixture() -> list[NormalizedDish]:
    return parse_html(FIXTURE.read_text(encoding="utf-8"))


def _next_eight_moscow(now: datetime) -> datetime:
    local = now.astimezone(MOSCOW)
    candidate = local.replace(hour=8, minute=0, second=0, microsecond=0)
    if local >= candidate:
        candidate += timedelta(days=1)
    return candidate


class _StubProvider:
    source = "mealty"
    fetches = 0

    async def fetch_catalog(self) -> list[NormalizedDish]:
        type(self).fetches += 1
        return _parsed_fixture()


class _FailingProvider:
    source = "mealty"
    fetches = 0

    async def fetch_catalog(self) -> list[NormalizedDish]:
        type(self).fetches += 1
        raise MealtyError("Mealty request failed")


async def _add_dish(**overrides: object) -> None:
    values: dict[str, object] = {
        "source": "mealty",
        "external_id": "875",
        "seller_product_id": "1001",
        "name": "Картофельные ньокки",
        "subtitle": "заметка",
        "description": None,
        "category": "main_dish",
        "price_kopecks": 41000,
        "old_price_kopecks": None,
        "weight_g": 300,
        "proteins": 8.1,
        "fats": 12.0,
        "carbs": 42.0,
        "calories": 310.0,
        "image_url": "https://www.mealty.ru/upload/example.jpg",
        "available": True,
    }
    values.update(overrides)
    async with SessionLocal() as session:
        session.add(Dish(**values))
        await session.commit()


async def _dish_count() -> int:
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(Dish))
    return int(count or 0)


async def _history_count() -> int:
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(PriceHistory))
    return int(count or 0)


async def test_scheduler_next_run_is_upcoming_eight_moscow() -> None:
    _StubProvider.fetches = 0
    scheduler = create_scheduler()
    with patch("app.catalog.service.MealtyProvider", _StubProvider):
        scheduler.start()
        try:
            jobs = scheduler.get_jobs()
            assert len(jobs) == 1
            job = jobs[0]
            assert job.id == CATALOG_SYNC_JOB_ID
            assert job.next_run_time is not None
            actual = job.next_run_time.astimezone(MOSCOW)
            expected = _next_eight_moscow(datetime.now(MOSCOW))
            assert actual == expected
            assert _StubProvider.fetches == 0
        finally:
            scheduler.shutdown(wait=False)


async def test_job_upserts_patched_snapshot_once() -> None:
    _StubProvider.fetches = 0
    snapshot = _parsed_fixture()
    with patch("app.catalog.service.MealtyProvider", _StubProvider):
        await run_catalog_sync()

    assert _StubProvider.fetches == 1
    async with SessionLocal() as session:
        rows = list(
            (await session.scalars(select(Dish).order_by(Dish.external_id))).all()
        )
        history = list((await session.scalars(select(PriceHistory))).all())

    by_external = {row.external_id: row for row in rows}
    assert set(by_external) == {dish.external_id for dish in snapshot}
    for dish in snapshot:
        row = by_external[dish.external_id]
        assert row.source == "mealty"
        assert row.available is True
        assert row.price_kopecks == dish.price_kopecks
        assert row.name == dish.name
    assert len(history) == len(snapshot)
    assert len({row.recorded_at for row in history}) == 1


async def _deny_quota() -> None:
    raise HTTPException(status_code=429, detail="Sync quota exceeded")


async def test_quota_refusal_skips_fetch_and_writes_nothing() -> None:
    _StubProvider.fetches = 0
    with (
        patch("app.catalog.service.assert_catalog_sync_allowed", _deny_quota),
        patch("app.catalog.service.MealtyProvider", _StubProvider),
    ):
        await run_catalog_sync()

    assert _StubProvider.fetches == 0
    assert await _dish_count() == 0
    assert await _history_count() == 0


async def test_mealty_error_leaves_existing_dishes() -> None:
    await _add_dish(price_kopecks=41000, available=True)
    _FailingProvider.fetches = 0
    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        await run_catalog_sync()

    assert _FailingProvider.fetches == 1
    async with SessionLocal() as session:
        row = await session.scalar(select(Dish).where(Dish.external_id == "875"))
        assert row is not None
        assert row.available is True
        assert row.price_kopecks == 41000
    assert await _history_count() == 0
