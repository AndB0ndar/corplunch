"""Poll job: close delivery dates whose cutoff deadline has passed."""

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.db import SessionLocal
from app.orders.service import CutoffOutcome, find_office_order, run_cutoff
from app.planning.service import cutoff_deadline
from app.users.settings_service import get_or_create_settings

logger = logging.getLogger(__name__)

# [today − 2 days, tomorrow]: older deadlines are left to the manual cutoff.
LOOKBACK_DAYS = 2
SCAN_AHEAD_DAYS = 1


def _now(tz: ZoneInfo) -> datetime:
    return datetime.now(tz)


def scan_delivery_dates(today: date) -> list[date]:
    offsets = range(-LOOKBACK_DAYS, SCAN_AHEAD_DAYS + 1)
    return [today + timedelta(days=offset) for offset in offsets]


async def run_day_cutoff_tick() -> None:
    """One poll: read settings fresh, close every past-deadline open date."""
    async with SessionLocal() as session:
        settings = await get_or_create_settings(session)
        tz = ZoneInfo(settings.timezone)
        now = _now(tz)
        for delivery_date in scan_delivery_dates(now.date()):
            if now < cutoff_deadline(delivery_date, settings):
                continue
            if await find_office_order(session, delivery_date) is not None:
                continue
            try:
                result = await run_cutoff(session, delivery_date)
            except Exception:
                logger.exception(
                    "Cutoff job failed for %s, skipping this date",
                    delivery_date,
                )
                continue
            if result.outcome == CutoffOutcome.NOTHING_TO_CLOSE:
                logger.info(
                    "Cutoff job skipped %s: no plan items",
                    delivery_date,
                )
