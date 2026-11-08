from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class DepartmentStats(BaseModel):
    department_id: int
    name: str
    actual_kopecks: int
    order_count: int


class EmployeeStats(BaseModel):
    user_id: int
    full_name: str
    actual_kopecks: int
    order_count: int


class TopDish(BaseModel):
    dish_id: int
    name: str
    qty: int
    actual_kopecks: int


class PriceChange(BaseModel):
    dish_id: int
    name: str
    planned_price_kopecks: int
    actual_price_kopecks: int


class StatsSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    period_from: date = Field(alias="from")
    to: date
    total_planned_kopecks: int
    total_actual_kopecks: int
    delta_kopecks: int
    unavailable_count: int
    by_department: list[DepartmentStats]
    by_employee: list[EmployeeStats]
    top_dishes: list[TopDish]
    price_changes: list[PriceChange]
