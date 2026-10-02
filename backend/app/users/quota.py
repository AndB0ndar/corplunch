"""Plan daily-limit (422) and Mealty catalog-sync quota (429) helpers.

Called by Bondar's catalog / planning layers — do not embed parser or cutoff logic here.

Quota semantics (stage 1 choice, aligned with docs/api.md + sprints):
- Count calendar-day sync attempts in `settings.timezone` (default Europe/Moscow).
- Both manual `POST /catalog/sync` and the morning job share one counter
  (they both call `sync_live_catalog` → this helper).
- A run is recorded when the gate passes (about to hit Mealty), not only on success.
- `sync-from-fixture` bypasses this helper (no live Mealty request).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import CatalogSyncRun, Settings, User
from app.users.settings_service import get_or_create_settings


async def assert_catalog_sync_allowed(session: AsyncSession) -> None:
    settings = await get_or_create_settings(session)
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    used = await session.scalar(
        select(func.count())
        .select_from(CatalogSyncRun)
        .where(CatalogSyncRun.ran_at >= day_start)
    )
    used_count = int(used or 0)

    if used_count >= settings.catalog_sync_per_day:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Sync quota exceeded",
        )

    # Commit before the live Mealty fetch so failed requests still consume quota.
    session.add(CatalogSyncRun(ran_at=now))
    await session.commit()


async def assert_plan_within_limit(
    session: AsyncSession,
    *,
    user: User,
    total_kopecks: int,
) -> None:
    """Raise 422 when plan total exceeds personal or system daily limit."""
    limit = user.daily_limit_kopecks
    if limit is None:
        settings: Settings = await get_or_create_settings(session)
        limit = settings.daily_limit_kopecks

    if limit is not None and total_kopecks > limit:
        raise HTTPException(
            status_code=422,
            detail="Daily limit exceeded",
        )
