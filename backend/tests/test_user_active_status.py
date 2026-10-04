import pytest
from httpx import AsyncClient


@pytest.mark.parametrize("is_active", [True, False])
async def test_user_active_status_survives_name_edit(
    admin_client: AsyncClient, is_active: bool
) -> None:
    credentials = {"email": "status@test.local", "password": "test-password"}
    created = await admin_client.post(
        "/api/admin/users",
        json={
            **credentials,
            "full_name": "Status Test",
            "role": "employee",
            "is_active": is_active,
        },
    )
    assert created.status_code == 201
    assert created.json()["is_active"] is is_active
    user_id = created.json()["id"]

    updated = await admin_client.patch(
        f"/api/admin/users/{user_id}", json={"full_name": "Renamed"}
    )
    assert updated.status_code == 200
    assert updated.json()["is_active"] is is_active

    listed = await admin_client.get("/api/admin/users")
    assert listed.status_code == 200
    user = next(user for user in listed.json() if user["id"] == user_id)
    assert user["is_active"] is is_active
    assert "password_hash" not in user

    login = await admin_client.post("/api/auth/login", json=credentials)
    assert login.status_code == (200 if is_active else 401)
    if is_active:
        profile = await admin_client.get(
            "/api/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert profile.status_code == 200
        assert profile.json()["is_active"] is True

    changed = await admin_client.patch(
        f"/api/admin/users/{user_id}", json={"is_active": not is_active}
    )
    assert changed.status_code == 200
    assert changed.json()["is_active"] is not is_active
    listed = await admin_client.get("/api/admin/users")
    user = next(user for user in listed.json() if user["id"] == user_id)
    assert user["is_active"] is not is_active
    login = await admin_client.post("/api/auth/login", json=credentials)
    assert login.status_code == (401 if is_active else 200)


async def test_openapi_requires_boolean_active_status(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    for name in ("UserOut", "MeResponse"):
        assert schemas[name]["properties"]["is_active"]["type"] == "boolean"
        assert "is_active" in schemas[name]["required"]
