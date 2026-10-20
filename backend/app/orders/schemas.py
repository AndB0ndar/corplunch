from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.orders.models import OfficeOrderStatus


class CutoffOut(BaseModel):
    delivery_date: date
    status: OfficeOrderStatus
    already_closed: bool
    sync: Literal["ok", "skipped"]
    plans_closed: int
    items_unavailable: int


class OrderTotals(BaseModel):
    planned_kopecks: int
    actual_kopecks: int | None
    delta_kopecks: int | None
    unavailable_count: int


class OrderItemOut(BaseModel):
    dish_id: int
    external_id: str
    name: str
    qty: int
    unit_price_kopecks: int
    line_total_kopecks: int


class EmployeeRowOut(BaseModel):
    user_id: int
    full_name: str
    department_id: int | None
    department_name: str | None
    actual_total_kopecks: int | None
    unavailable_count: int


class OrderSummary(BaseModel):
    delivery_date: date
    status: OfficeOrderStatus
    totals: OrderTotals
    items: list[OrderItemOut]
    by_employee: list[EmployeeRowOut]


class PlaceOut(BaseModel):
    delivery_date: date
    status: OfficeOrderStatus
    placed_at: datetime
    placed_by_user_id: int
    already_placed: bool
