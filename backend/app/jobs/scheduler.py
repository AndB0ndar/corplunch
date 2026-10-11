"""In-process scheduler for the catalog sync and the day-cutoff poll."""

from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.jobs.catalog import run_catalog_sync
from app.jobs.cutoff import run_day_cutoff_tick

MOSCOW = ZoneInfo("Europe/Moscow")
CATALOG_SYNC_JOB_ID = "catalog-sync"
CUTOFF_JOB_ID = "day-cutoff"
CUTOFF_INTERVAL_MINUTES = 10
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
    scheduler.add_job(
        run_day_cutoff_tick,
        IntervalTrigger(minutes=CUTOFF_INTERVAL_MINUTES, timezone=MOSCOW),
        id=CUTOFF_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )
    return scheduler
