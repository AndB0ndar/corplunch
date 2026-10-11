from __future__ import annotations

from datetime import date
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
