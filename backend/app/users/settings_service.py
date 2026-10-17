"""Singleton settings row helpers."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import Settings

SETTINGS_ROW_ID = 1

DEFAULT_CUTOFF_TIME = "16:00"
DEFAULT_TIMEZONE = "Europe/Moscow"
DEFAULT_MEALTY_CITY = "Москва"
DEFAULT_CATALOG_SYNC_PER_DAY = 2


def default_settings() -> Settings:
    return Settings(
        id=SETTINGS_ROW_ID,
        cutoff_time=DEFAULT_CUTOFF_TIME,
        timezone=DEFAULT_TIMEZONE,
        mealty_city=DEFAULT_MEALTY_CITY,
        daily_limit_kopecks=None,
        catalog_sync_per_day=DEFAULT_CATALOG_SYNC_PER_DAY,
    )


async def get_or_create_settings(session: AsyncSession) -> Settings:
    """Return the singleton settings row, creating defaults if missing.

    Concurrent first-time creates are safe: INSERT … ON CONFLICT DO NOTHING
    on primary key id=1, then re-select (avoids settings_pkey races).
    """
    row = await session.get(Settings, SETTINGS_ROW_ID)
    if row is not None:
        return row

    stmt = (
        insert(Settings)
        .values(
            id=SETTINGS_ROW_ID,
            cutoff_time=DEFAULT_CUTOFF_TIME,
            timezone=DEFAULT_TIMEZONE,
            mealty_city=DEFAULT_MEALTY_CITY,
            daily_limit_kopecks=None,
            catalog_sync_per_day=DEFAULT_CATALOG_SYNC_PER_DAY,
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    await session.execute(stmt)
    await session.flush()

    row = await session.get(Settings, SETTINGS_ROW_ID)
    if row is None:
        raise RuntimeError("settings singleton missing after get-or-create")
    return row
