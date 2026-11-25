"""Offline defense stand: real API/DB, two local HTML snapshots of Mealty."""

import asyncio
from unittest.mock import patch

import uvicorn
from alembic import command
from alembic.config import Config

from app.catalog.service import upsert_catalog
from app.cli import FIXTURE_PATH, seed_users
from app.db import SessionLocal, engine
from app.main import app
from app.providers import MealtyProvider, NormalizedDish, parse_html


def snapshot(name: str) -> list[NormalizedDish]:
    html = FIXTURE_PATH.with_name(name).read_text(encoding="utf-8")
    # The frontend looks up its bundled Mealty photo by external_id.
    return [dish.model_copy(update={"image_url": None}) for dish in parse_html(html)]


async def cutoff_snapshot(_provider: MealtyProvider) -> list[NormalizedDish]:
    dishes = snapshot("mealty_catalog_missing.html")
    for dish in dishes:
        if dish.external_id == "721":
            dish.price_kopecks += 1500
    return dishes


async def prepare() -> None:
    await seed_users()
    async with SessionLocal() as session:
        await upsert_catalog(session, "mealty", snapshot("mealty_catalog_qa.html"))
    await engine.dispose()


if __name__ == "__main__":
    @app.get("/api/qa/defense", include_in_schema=False)
    def fixture_mode() -> dict[str, str]:
        return {"provider": "local-html"}

    command.upgrade(Config("alembic.ini"), "head")
    asyncio.run(prepare())
    # Only the manual cutoff runs during the presentation.
    with patch.object(MealtyProvider, "fetch_catalog", cutoff_snapshot):
        uvicorn.run(app, host="0.0.0.0", port=8000, lifespan="off")
