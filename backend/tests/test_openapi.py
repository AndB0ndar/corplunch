from httpx import AsyncClient


async def test_docs_open(client: AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200


async def test_openapi_includes_health_and_departments(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/health" in paths
    assert "get" in paths["/api/health"]
    assert "/api/admin/departments" in paths
    assert "get" in paths["/api/admin/departments"]
    assert "post" in paths["/api/admin/departments"]
    assert "/api/admin/settings" in paths
    assert "get" in paths["/api/admin/settings"]
    assert "put" in paths["/api/admin/settings"]


def _nullable_int(schema: dict) -> bool:
    variants = schema.get("anyOf") or schema.get("oneOf") or []
    types = {item.get("type") for item in variants}
    return "integer" in types and "null" in types


async def test_openapi_day_summary_and_place(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    paths = spec["paths"]
    order = "/api/orders/{delivery_date}"
    assert "get" in paths[order]
    assert "post" in paths[f"{order}/place"]
    assert "get" in paths[f"{order}/export.csv"]
    assert "get" in paths[f"{order}/export.xlsx"]
    assert "post" in paths[f"{order}/cutoff"]

    schemas = spec["components"]["schemas"]
    place = schemas["PlaceOut"]["properties"]
    assert set(place) == {
        "delivery_date",
        "status",
        "placed_at",
        "placed_by_user_id",
        "already_placed",
    }
    totals = schemas["OrderTotals"]["properties"]
    assert _nullable_int(totals["actual_kopecks"])
    assert _nullable_int(totals["delta_kopecks"])
    assert totals["planned_kopecks"]["type"] == "integer"
    employee = schemas["EmployeeRowOut"]["properties"]
    assert _nullable_int(employee["actual_total_kopecks"])
    item = schemas["OrderItemOut"]["properties"]
    assert set(item) == {
        "dish_id",
        "external_id",
        "name",
        "qty",
        "unit_price_kopecks",
        "line_total_kopecks",
    }
