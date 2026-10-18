"""Close a delivery day and serve the procurement summary.

Cutoff stays the single writer of the snapshot. The summary builder only reads:
closed days take `items` from that snapshot, collecting days preview live drafts.
"""

import enum
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.catalog.models import Dish
from app.catalog.service import EmptySnapshotError, sync_live_catalog
from app.orders.export_render import render_summary_csv, render_summary_xlsx
from app.orders.models import OfficeOrder, OfficeOrderItem, OfficeOrderStatus
from app.orders.schemas import (
    EmployeeRowOut,
    OrderItemOut,
    OrderSummary,
    OrderTotals,
    PlaceOut,
)
from app.planning.models import MealPlan, PlanItem, PlanStatus
from app.planning.service import apply_actual_prices
from app.providers import MealtyError
from app.users.models import User

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


DAY_STILL_COLLECTING_DETAIL = "день ещё собирается"

CSV_MEDIA_TYPE = "text/csv; charset=utf-8"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

ExportKind = Literal["csv", "xlsx"]


class DayStillCollecting(Exception):
    """No office order for the date: place and export are forbidden."""


@dataclass(frozen=True, slots=True)
class ExportFile:
    body: bytes
    media_type: str
    filename: str


@dataclass(slots=True)
class _DishPreview:
    dish_id: int
    external_id: str
    name: str
    qty: int
    unit_price_kopecks: int


async def build_order_summary(
    session: AsyncSession,
    delivery_date: date,
) -> OrderSummary:
    """Read-only summary. No office-order row means collecting, not 404."""
    order = await find_office_order(session, delivery_date)
    if order is None:
        return await _collecting_summary(session, delivery_date)
    return await _closed_summary(session, delivery_date, order)


async def place_order(
    session: AsyncSession,
    delivery_date: date,
    user_id: int,
) -> PlaceOut:
    """First `place` wins. A repeat returns the original who/when.

    `UPDATE … WHERE status <> 'placed'` so concurrent calls do not overwrite
    `placed_at` / `placed_by_user_id`. No row → `DayStillCollecting`.
    """
    now = datetime.now(UTC)
    placed = (
        await session.execute(
            update(OfficeOrder)
            .where(
                OfficeOrder.delivery_date == delivery_date,
                OfficeOrder.status != OfficeOrderStatus.PLACED,
            )
            .values(
                status=OfficeOrderStatus.PLACED,
                placed_at=now,
                placed_by_user_id=user_id,
            )
            .returning(
                OfficeOrder.placed_at,
                OfficeOrder.placed_by_user_id,
            )
        )
    ).first()
    if placed is not None:
        await session.commit()
        return PlaceOut(
            delivery_date=delivery_date,
            status=OfficeOrderStatus.PLACED,
            placed_at=placed.placed_at,
            placed_by_user_id=placed.placed_by_user_id,
            already_placed=False,
        )

    current = await session.scalar(
        select(OfficeOrder)
        .where(OfficeOrder.delivery_date == delivery_date)
        .execution_options(populate_existing=True)
    )
    if (
        current is None
        or current.status != OfficeOrderStatus.PLACED
        or current.placed_at is None
        or current.placed_by_user_id is None
    ):
        raise DayStillCollecting(DAY_STILL_COLLECTING_DETAIL)
    return PlaceOut(
        delivery_date=delivery_date,
        status=OfficeOrderStatus.PLACED,
        placed_at=current.placed_at,
        placed_by_user_id=current.placed_by_user_id,
        already_placed=True,
    )


async def build_export(
    session: AsyncSession,
    delivery_date: date,
    kind: ExportKind,
) -> ExportFile:
    """Render the live summary, then `locked → exported` in the same commit.

    `placed` is left alone. No office order → `DayStillCollecting` (no file).
    """
    order = await find_office_order(session, delivery_date)
    if order is None:
        raise DayStillCollecting(DAY_STILL_COLLECTING_DETAIL)

    summary = await build_order_summary(session, delivery_date)
    payload = summary.model_dump(mode="json")
    if kind == "csv":
        body = render_summary_csv(payload)
        media_type = CSV_MEDIA_TYPE
        extension = "csv"
    elif kind == "xlsx":
        body = render_summary_xlsx(payload)
        media_type = XLSX_MEDIA_TYPE
        extension = "xlsx"
    else:
        raise ValueError(f"unsupported export kind: {kind}")

    if order.status == OfficeOrderStatus.LOCKED:
        await session.execute(
            update(OfficeOrder)
            .where(
                OfficeOrder.id == order.id,
                OfficeOrder.status == OfficeOrderStatus.LOCKED,
            )
            .values(status=OfficeOrderStatus.EXPORTED)
        )
        await session.commit()

    return ExportFile(
        body=body,
        media_type=media_type,
        filename=f"corplunch-{delivery_date.isoformat()}.{extension}",
    )


async def _closed_summary(
    session: AsyncSession,
    delivery_date: date,
    order: OfficeOrder,
) -> OrderSummary:
    item_rows = (
        await session.execute(
            select(
                OfficeOrderItem.dish_id,
                Dish.external_id,
                Dish.name,
                OfficeOrderItem.qty,
                OfficeOrderItem.unit_price_kopecks,
                OfficeOrderItem.line_total_kopecks,
            )
            .join(Dish, Dish.id == OfficeOrderItem.dish_id)
            .where(OfficeOrderItem.office_order_id == order.id)
            .order_by(Dish.name, OfficeOrderItem.dish_id)
        )
    ).all()
    items = [
        OrderItemOut(
            dish_id=row.dish_id,
            external_id=row.external_id,
            name=row.name,
            qty=row.qty,
            unit_price_kopecks=row.unit_price_kopecks,
            line_total_kopecks=row.line_total_kopecks,
        )
        for row in item_rows
    ]
    items.sort(key=lambda item: (item.name, item.dish_id))

    plans = await _plans_for(
        session,
        delivery_date,
        PlanStatus.INCLUDED_IN_ORDER,
        with_dishes=False,
    )
    employees, planned, unavailable_count = await _employee_rows(
        session,
        plans,
        priced=True,
    )
    actual = sum(item.line_total_kopecks for item in items)
    return OrderSummary(
        delivery_date=delivery_date,
        status=order.status,
        totals=OrderTotals(
            planned_kopecks=planned,
            actual_kopecks=actual,
            delta_kopecks=actual - planned,
            unavailable_count=unavailable_count,
        ),
        items=items,
        by_employee=employees,
    )


async def _collecting_summary(
    session: AsyncSession,
    delivery_date: date,
) -> OrderSummary:
    plans = await _plans_for(
        session,
        delivery_date,
        PlanStatus.DRAFT,
        with_dishes=True,
    )
    employees, planned, unavailable_count = await _employee_rows(
        session,
        plans,
        priced=False,
    )
    return OrderSummary(
        delivery_date=delivery_date,
        status=OfficeOrderStatus.COLLECTING,
        totals=OrderTotals(
            planned_kopecks=planned,
            actual_kopecks=None,
            delta_kopecks=None,
            unavailable_count=unavailable_count,
        ),
        items=_preview_items(plans),
        by_employee=employees,
    )


async def _plans_for(
    session: AsyncSession,
    delivery_date: date,
    status: PlanStatus,
    *,
    with_dishes: bool,
) -> list[MealPlan]:
    item_load = selectinload(MealPlan.items)
    if with_dishes:
        item_load = item_load.selectinload(PlanItem.dish)
    return list(
        (
            await session.scalars(
                select(MealPlan)
                .where(
                    MealPlan.delivery_date == delivery_date,
                    MealPlan.status == status,
                )
                .options(item_load)
            )
        ).all()
    )


async def _employee_rows(
    session: AsyncSession,
    plans: list[MealPlan],
    *,
    priced: bool,
) -> tuple[list[EmployeeRowOut], int, int]:
    """One row per plan, including a plan whose every item is unavailable."""
    users = await _users_by_id(session, [plan.user_id for plan in plans])
    planned = 0
    unavailable_count = 0
    rows: list[EmployeeRowOut] = []
    for plan in plans:
        user = users[plan.user_id]
        department = user.department
        person_unavailable = 0
        person_actual = 0
        for item in plan.items:
            if item.unavailable:
                person_unavailable += 1
                unavailable_count += 1
                continue
            planned += item.planned_price_kopecks * item.qty
            if priced and item.actual_price_kopecks is not None:
                person_actual += item.actual_price_kopecks * item.qty
        rows.append(
            EmployeeRowOut(
                user_id=user.id,
                full_name=user.full_name,
                department_id=user.department_id,
                department_name=(department.name if department is not None else None),
                actual_total_kopecks=person_actual if priced else None,
                unavailable_count=person_unavailable,
            )
        )
    rows.sort(key=lambda row: (row.full_name, row.user_id))
    return rows, planned, unavailable_count


async def _users_by_id(
    session: AsyncSession,
    user_ids: list[int],
) -> dict[int, User]:
    if not user_ids:
        return {}
    rows = (
        await session.scalars(
            select(User)
            .where(User.id.in_(user_ids))
            .options(selectinload(User.department))
        )
    ).all()
    return {user.id: user for user in rows}


def _preview_items(plans: list[MealPlan]) -> list[OrderItemOut]:
    """Collecting preview: current catalog price, unavailable rows omitted."""
    buckets: dict[int, _DishPreview] = {}
    for plan in plans:
        for item in plan.items:
            if item.unavailable:
                continue
            dish = item.dish
            bucket = buckets.get(item.dish_id)
            if bucket is None:
                buckets[item.dish_id] = _DishPreview(
                    dish_id=item.dish_id,
                    external_id=dish.external_id,
                    name=dish.name,
                    qty=item.qty,
                    unit_price_kopecks=dish.price_kopecks,
                )
            else:
                bucket.qty += item.qty
    items = [
        OrderItemOut(
            dish_id=bucket.dish_id,
            external_id=bucket.external_id,
            name=bucket.name,
            qty=bucket.qty,
            unit_price_kopecks=bucket.unit_price_kopecks,
            line_total_kopecks=bucket.unit_price_kopecks * bucket.qty,
        )
        for bucket in buckets.values()
    ]
    items.sort(key=lambda item: (item.name, item.dish_id))
    return items
