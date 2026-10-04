from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.planning.models import PlanStatus


class PlanItemIn(BaseModel):
    dish_id: int
    qty: int = Field(ge=1)


class PlanReplace(BaseModel):
    items: list[PlanItemIn]

    @model_validator(mode="after")
    def unique_dish_ids(self) -> PlanReplace:
        dish_ids = [item.dish_id for item in self.items]
        if len(dish_ids) != len(set(dish_ids)):
            raise ValueError("duplicate dish_id")
        return self


class PlanItemOut(BaseModel):
    dish_id: int
    name: str
    qty: int
    planned_price_kopecks: int
    actual_price_kopecks: int | None
    unavailable: bool


class PlanOut(BaseModel):
    id: int | None
    user_id: int
    delivery_date: date
    status: PlanStatus
    editable: bool
    planned_total_kopecks: int
    actual_total_kopecks: int | None
    items: list[PlanItemOut]
