"""In-process scheduler for the morning catalog sync."""

from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.jobs.catalog import run_catalog_sync

MOSCOW = ZoneInfo("Europe/Moscow")
CATALOG_SYNC_JOB_ID = "catalog-sync"
MISFIRE_GRACE_SECONDS = 3600


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=MOSCOW)
    scheduler.add_job(
        run_catalog_sync,
        CronTrigger(hour=8, minute=0, timezone=MOSCOW),
        id=CATALOG_SYNC_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )
    return scheduler
