"""Live OrderSummary DTO → CSV/XLSX (Bondar aggregate shape, no Mealty network)."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from unittest.mock import patch

import bcrypt
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy import select

from app.catalog.models import Dish
from app.db import SessionLocal
from app.orders.export_render import (
    CSV_COLUMNS,
    EMPLOYEE_COLUMNS,
    EMPLOYEE_SHEET_NAME,
    render_order_summary_csv,
    render_order_summary_xlsx,
    summary_payload,
)
from app.orders.models import OfficeOrder, OfficeOrderStatus
from app.orders.schemas import (
    EmployeeRowOut,
    OrderItemOut,
    OrderSummary,
    OrderTotals,
)
from app.orders.service import build_export, build_order_summary
from app.providers import MealtyError, NormalizedDish
from app.users.models import Department, User, UserRole
from tests.conftest import BearerAuth

DAY = date.today() + timedelta(days=27)


class _FailingProvider:
    source = "mealty"

    async def fetch_catalog(self) -> list[NormalizedDish]:
        raise MealtyError("Mealty request failed")


def _live_summary() -> OrderSummary:
    """Same field set as GET /api/orders/{date} after cutoff."""
    return OrderSummary(
        delivery_date=date(2026, 10, 20),
        status=OfficeOrderStatus.LOCKED,
        totals=OrderTotals(
            planned_kopecks=255000,
            actual_kopecks=255000,
            delta_kopecks=0,
            unavailable_count=0,
        ),
        items=[
            OrderItemOut(
                dish_id=12,
                external_id="875",
                name="Картофельные ньокки с грибами",
                qty=4,
                unit_price_kopecks=42500,
                line_total_kopecks=170000,
            ),
            OrderItemOut(
                dish_id=15,
                external_id="902",
                name="Куриный суп с лапшой",
                qty=2,
                unit_price_kopecks=42500,
                line_total_kopecks=85000,
            ),
        ],
        by_employee=[
            EmployeeRowOut(
                user_id=1,
                full_name="Иван Сотрудник",
                department_id=1,
                department_name="Разработка",
                actual_total_kopecks=85000,
                unavailable_count=0,
            ),
            EmployeeRowOut(
                user_id=2,
                full_name="Мария Сотрудница",
                department_id=2,
                department_name="Закупки",
                actual_total_kopecks=170000,
                unavailable_count=0,
            ),
        ],
    )


def test_summary_payload_matches_api_shape() -> None:
    payload = summary_payload(_live_summary())
    assert payload["delivery_date"] == "2026-10-20"
    assert payload["status"] == "locked"
    assert set(CSV_COLUMNS).issubset(payload["items"][0].keys())
    assert "dish_id" in payload["items"][0]
    assert payload["by_employee"][0]["full_name"] == "Иван Сотрудник"


def test_live_order_summary_csv_columns() -> None:
    raw = render_order_summary_csv(_live_summary())
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert list(rows[0].keys()) == list(CSV_COLUMNS)
    assert rows[0]["external_id"] == "875"
    assert rows[0]["qty"] == "4"
    assert rows[0]["line_total_kopecks"] == "170000"
    assert rows[1]["external_id"] == "902"
    # dish_id is on the DTO but must not appear as a CSV column
    assert "dish_id" not in rows[0]


def test_live_order_summary_xlsx_opens() -> None:
    raw = render_order_summary_xlsx(_live_summary())
    workbook = load_workbook(io.BytesIO(raw))
    assert workbook.sheetnames[0] == "Блюда"
    assert EMPLOYEE_SHEET_NAME in workbook.sheetnames
    dishes = workbook["Блюда"]
    assert [cell.value for cell in dishes[1]] == list(CSV_COLUMNS)
    assert dishes["A2"].value == "875"
    assert dishes["C2"].value == 4
    people = workbook[EMPLOYEE_SHEET_NAME]
    assert [cell.value for cell in people[1]] == list(EMPLOYEE_COLUMNS)
    assert people["B2"].value == "Иван Сотрудник"
    assert people["E2"].value == 85000


def test_live_dto_null_actuals_still_render() -> None:
    """Collecting-day rows may have null actual totals — export must not crash."""
    summary = OrderSummary(
        delivery_date=DAY,
        status=OfficeOrderStatus.COLLECTING,
        totals=OrderTotals(
            planned_kopecks=41000,
            actual_kopecks=None,
            delta_kopecks=None,
            unavailable_count=0,
        ),
        items=[],
        by_employee=[
            EmployeeRowOut(
                user_id=9,
                full_name="Черновик",
                department_id=None,
                department_name=None,
                actual_total_kopecks=None,
                unavailable_count=0,
            )
        ],
    )
    csv_raw = render_order_summary_csv(summary)
    assert csv_raw.decode("utf-8-sig").strip() == ",".join(CSV_COLUMNS)
    book = load_workbook(io.BytesIO(render_order_summary_xlsx(summary)))
    assert book[EMPLOYEE_SHEET_NAME]["B2"].value == "Черновик"
    assert book[EMPLOYEE_SHEET_NAME]["E2"].value is None


async def _add_dish(external_id: str, **overrides: object) -> int:
    values: dict[str, object] = {
        "source": "mealty",
        "external_id": external_id,
        "seller_product_id": None,
        "name": f"Блюдо {external_id}",
        "subtitle": "",
        "description": None,
        "category": "main_dish",
        "price_kopecks": 41000,
        "old_price_kopecks": None,
        "weight_g": 300,
        "proteins": None,
        "fats": None,
        "carbs": None,
        "calories": None,
        "image_url": None,
        "available": True,
    }
    values.update(overrides)
    async with SessionLocal() as session:
        dish = Dish(**values)
        session.add(dish)
        await session.commit()
        await session.refresh(dish)
        return dish.id


async def _employee(client: AsyncClient, email: str, full_name: str) -> BearerAuth:
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    async with SessionLocal() as session:
        department = Department(name=f"Dept {email}")
        session.add(department)
        await session.flush()
        user = User(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            role=UserRole.EMPLOYEE,
            department_id=department.id,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id
    response = await client.post(
        "/api/auth/login",
        json={"email": email, "password": "secret"},
    )
    assert response.status_code == 200, response.text
    return BearerAuth(
        token=response.json()["access_token"],
        user_id=user_id,
        role=UserRole.EMPLOYEE,
        email=email,
    )


async def test_build_export_feeds_live_aggregate_dto(
    client: AsyncClient,
    procurement_auth: BearerAuth,
) -> None:
    """Cutoff → Bondar summary → typed render → bytes Excel can open."""
    dish_id = await _add_dish("live-export-875", name="Ньокки live")
    ivan = await _employee(client, "live-export-ivan@test.local", "Иван Live")
    put = await client.put(
        f"/api/plans/{DAY.isoformat()}",
        headers=ivan.headers,
        json={"items": [{"dish_id": dish_id, "qty": 2}]},
    )
    assert put.status_code == 200, put.text

    with patch("app.catalog.service.MealtyProvider", _FailingProvider):
        cutoff = await client.post(
            f"/api/orders/{DAY.isoformat()}/cutoff",
            headers=procurement_auth.headers,
        )
    assert cutoff.status_code == 200, cutoff.text

    async with SessionLocal() as session:
        summary = await build_order_summary(session, DAY)
        assert summary.status == OfficeOrderStatus.LOCKED
        assert summary.items
        csv_bytes = render_order_summary_csv(summary)
        xlsx_bytes = render_order_summary_xlsx(summary)
        exported = await build_export(session, DAY, "csv")

    rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
    assert list(rows[0].keys()) == list(CSV_COLUMNS)
    assert rows[0]["external_id"] == "live-export-875"
    assert rows[0]["qty"] == "2"

    book = load_workbook(io.BytesIO(xlsx_bytes))
    assert book.sheetnames[0] == "Блюда"
    assert EMPLOYEE_SHEET_NAME in book.sheetnames
    assert book["Блюда"]["A2"].value == "live-export-875"

    assert exported.body.startswith(b"\xef\xbb\xbf")
    async with SessionLocal() as session:
        order = await session.scalar(
            select(OfficeOrder).where(OfficeOrder.delivery_date == DAY)
        )
        assert order is not None
        assert order.status == OfficeOrderStatus.EXPORTED
