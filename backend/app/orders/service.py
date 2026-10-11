"""Close a delivery day: best-effort sync → price stamp → office order."""

import enum
import logging
from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.catalog.service import EmptySnapshotError, sync_live_catalog
from app.orders.models import OfficeOrder, OfficeOrderItem, OfficeOrderStatus
from app.planning.models import MealPlan, PlanItem, PlanStatus
from app.planning.service import apply_actual_prices
from app.providers import MealtyError

logger = logging.getLogger(__name__)

SyncState = Literal["ok", "skipped"]

SYNC_OK: SyncState = "ok"
SYNC_SKIPPED: SyncState = "skipped"


class CutoffOutcome(enum.StrEnum):
    CLOSED = "closed"
    ALREADY_CLOSED = "already_closed"
    NOTHING_TO_CLOSE = "nothing_to_close"


@dataclass(frozen=True, slots=True)
class CutoffResult:
    outcome: CutoffOutcome
    delivery_date: date
    sync: SyncState
    plans_closed: int = 0
    items_unavailable: int = 0
    order_status: OfficeOrderStatus | None = None

    @property
    def already_closed(self) -> bool:
        return self.outcome == CutoffOutcome.ALREADY_CLOSED


async def find_office_order(
    session: AsyncSession,
    delivery_date: date,
) -> OfficeOrder | None:
    return await session.scalar(
        select(OfficeOrder).where(OfficeOrder.delivery_date == delivery_date)
    )


async def _date_plan_item_count(
    session: AsyncSession,
    delivery_date: date,
) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(PlanItem)
        .join(MealPlan, MealPlan.id == PlanItem.plan_id)
        .where(MealPlan.delivery_date == delivery_date)
    )
    return int(count or 0)


async def _count_unavailable_items(
    session: AsyncSession,
    delivery_date: date,
) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(PlanItem)
        .join(MealPlan, MealPlan.id == PlanItem.plan_id)
        .where(
            MealPlan.delivery_date == delivery_date,
            PlanItem.unavailable.is_(True),
        )
    )
    return int(count or 0)


async def _sync_catalog_best_effort(session: AsyncSession) -> SyncState:
    try:
        await sync_live_catalog(session, enforce_quota=False)
    except (MealtyError, EmptySnapshotError) as exc:
        logger.warning(
            "Cutoff sync skipped, closing on the stored snapshot: %s",
            exc,
        )
        return SYNC_SKIPPED
    return SYNC_OK


async def run_cutoff(session: AsyncSession, delivery_date: date) -> CutoffResult:
    """The single cutoff algorithm for the poll job and the manual endpoint.

    Steps: idempotency check → best-effort live sync → price stamp
    (`apply_actual_prices`, own commit) → office order in `locked` with an
    item snapshot and plans moved to `included_in_order` in one commit.
    """
    existing = await find_office_order(session, delivery_date)
    if existing is not None:
        # Idempotent no-op: no new sync attempt, no stored changes.
        return CutoffResult(
            outcome=CutoffOutcome.ALREADY_CLOSED,
            delivery_date=delivery_date,
            sync=SYNC_SKIPPED,
            order_status=existing.status,
        )

    if await _date_plan_item_count(session, delivery_date) == 0:
        # Empty day: "пустой состав при lock". The router maps this to 400,
        # the poll job silently skips the date.
        return CutoffResult(
            outcome=CutoffOutcome.NOTHING_TO_CLOSE,
            delivery_date=delivery_date,
            sync=SYNC_SKIPPED,
        )

    sync_state = await _sync_catalog_best_effort(session)

    await apply_actual_prices(session, delivery_date)

    create_order = (
        insert(OfficeOrder)
        .values(
            delivery_date=delivery_date,
            status=OfficeOrderStatus.LOCKED,
        )
        .on_conflict_do_nothing(index_elements=["delivery_date"])
        .returning(OfficeOrder.id)
    )
    inserted = (await session.execute(create_order)).first()
    if inserted is None:
        # A concurrent cutoff won the race; this call changed nothing.
        winner = await find_office_order(session, delivery_date)
        return CutoffResult(
            outcome=CutoffOutcome.ALREADY_CLOSED,
            delivery_date=delivery_date,
            sync=sync_state,
            order_status=winner.status if winner is not None else None,
        )
    order_id = inserted.id

    plans = list(
        (
            await session.scalars(
                select(MealPlan)
                .where(
                    MealPlan.delivery_date == delivery_date,
                    MealPlan.status.in_(
                        (PlanStatus.PRICED, PlanStatus.INCLUDED_IN_ORDER)
                    ),
                )
                .options(selectinload(MealPlan.items))
                .execution_options(populate_existing=True)
            )
        ).all()
    )

    # Snapshot: one row per dish, only positions with unavailable=false.
    # `priced` + `included_in_order` keeps a retry after a partial failure
    # from double-counting anything already aggregated.
    per_dish: dict[int, dict[str, int]] = {}
    for plan in plans:
        for item in plan.items:
            if item.unavailable or item.actual_price_kopecks is None:
                continue
            bucket = per_dish.setdefault(
                item.dish_id,
                {
                    "qty": 0,
                    "unit_price_kopecks": item.actual_price_kopecks,
                },
            )
            bucket["qty"] += item.qty
    for dish_id, bucket in per_dish.items():
        unit_price = bucket["unit_price_kopecks"]
        session.add(
            OfficeOrderItem(
                office_order_id=order_id,
                dish_id=dish_id,
                qty=bucket["qty"],
                unit_price_kopecks=unit_price,
                line_total_kopecks=unit_price * bucket["qty"],
            )
        )

    plans_closed = 0
    for plan in plans:
        plan.office_order_id = order_id
        if plan.status == PlanStatus.PRICED:
            plans_closed += 1
        plan.status = PlanStatus.INCLUDED_IN_ORDER

    items_unavailable = await _count_unavailable_items(session, delivery_date)

    await session.commit()

    return CutoffResult(
        outcome=CutoffOutcome.CLOSED,
        delivery_date=delivery_date,
        sync=sync_state,
        plans_closed=plans_closed,
        items_unavailable=items_unavailable,
        order_status=OfficeOrderStatus.LOCKED,
    )
