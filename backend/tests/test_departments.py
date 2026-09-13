from httpx import AsyncClient


async def test_departments_unauthorized(client: AsyncClient) -> None:
    response = await client.get("/api/admin/departments")
    assert response.status_code == 401
    body = response.json()
    assert "detail" in body


async def test_create_and_list_departments(admin_client: AsyncClient) -> None:
    created = await admin_client.post(
        "/api/admin/departments",
        json={"name": "Разработка"},
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["name"] == "Разработка"
    assert isinstance(payload["id"], int)

    listed = await admin_client.get("/api/admin/departments")
    assert listed.status_code == 200
    names = [row["name"] for row in listed.json()]
    assert "Разработка" in names
