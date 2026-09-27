"""Morning Mealty catalog sync."""

import logging

from fastapi import HTTPException, status

from app.catalog.service import EmptySnapshotError, sync_live_catalog
from app.db import SessionLocal
from app.providers import MealtyError

logger = logging.getLogger(__name__)


async def run_catalog_sync() -> None:
    try:
        async with SessionLocal() as session:
            result = await sync_live_catalog(session)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_429_TOO_MANY_REQUESTS:
            raise
        logger.warning("Catalog sync skipped: %s", exc.detail)
        return
    except MealtyError as exc:
        logger.warning("Catalog sync skipped: %s", exc)
        return
    except EmptySnapshotError as exc:
        logger.warning("Catalog sync skipped: %s", exc)
        return

    logger.info(
        "Catalog sync finished: upserted=%s unavailable=%s",
        result.upserted,
        result.unavailable,
    )
