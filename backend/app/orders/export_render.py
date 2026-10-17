"""Render office-order summary DTO to CSV / XLSX (no DB, no status changes).

Bondar's export router (stage 3) will call these helpers on a live summary DTO
and then flip `locked → exported`. This module only formats bytes.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from typing import Any

from openpyxl import Workbook

CSV_COLUMNS = (
    "external_id",
    "name",
    "qty",
    "unit_price_kopecks",
    "line_total_kopecks",
)

EMPLOYEE_SHEET_NAME = "По сотрудникам"
EMPLOYEE_COLUMNS = (
    "user_id",
    "full_name",
    "department_id",
    "department_name",
    "actual_total_kopecks",
    "unavailable_count",
)


def _items(summary: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    items = summary.get("items") or []
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise TypeError("summary['items'] must be a sequence of row mappings")
    return items  # type: ignore[return-value]


def _by_employee(summary: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    rows = summary.get("by_employee") or []
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise TypeError("summary['by_employee'] must be a sequence of row mappings")
    return rows  # type: ignore[return-value]


def render_summary_csv(summary: Mapping[str, Any]) -> bytes:
    """DTO → UTF-8 CSV with columns from docs/api.md export.csv."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(CSV_COLUMNS), extrasaction="ignore")
    writer.writeheader()
    for row in _items(summary):
        writer.writerow({column: row.get(column, "") for column in CSV_COLUMNS})
    # utf-8-sig helps Excel open Cyrillic; API can strip BOM if unwanted
    return buffer.getvalue().encode("utf-8-sig")


def render_summary_xlsx(summary: Mapping[str, Any]) -> bytes:
    """DTO → XLSX: dish sheet (same columns as CSV) + «По сотрудникам»."""
    workbook = Workbook()
    dishes = workbook.active
    dishes.title = "Блюда"
    dishes.append(list(CSV_COLUMNS))
    for row in _items(summary):
        dishes.append([row.get(column) for column in CSV_COLUMNS])

    people = workbook.create_sheet(EMPLOYEE_SHEET_NAME)
    people.append(list(EMPLOYEE_COLUMNS))
    for row in _by_employee(summary):
        people.append([row.get(column) for column in EMPLOYEE_COLUMNS])

    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()
