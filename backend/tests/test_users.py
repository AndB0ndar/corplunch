from httpx import AsyncClient

from app.db import SessionLocal
from app.main import app
from app.users.models import User, UserRole


async def test_admin_users_requires_auth(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/admin/users"
    )

    assert response.status_code == 401


async def test_admin_can_create_user(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.post(
        "/api/admin/users",
        json={
            "email": "new@test.local",
            "password": "password",
            "full_name": "New User",
            "role": "employee",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["email"] == "new@test.local"
    assert body["role"] == "employee"
    assert "password_hash" not in body


async def test_admin_can_update_user(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.post(
        "/api/admin/users",
        json={
            "email": "update@test.local",
            "password": "password",
            "full_name": "Old Name",
            "role": "employee",
        },
    )

    assert response.status_code == 201

    user_id = response.json()["id"]

    response = await admin_client.patch(
        f"/api/admin/users/{user_id}",
        json={
            "full_name": "New Name",
            "role": "procurement",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["full_name"] == "New Name"
    assert body["role"] == "procurement"


async def test_admin_can_update_department(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.post(
        "/api/admin/departments",
        json={
            "name": "Old Department",
        },
    )

    assert response.status_code == 201

    department_id = response.json()["id"]

    response = await admin_client.patch(
        f"/api/admin/departments/{department_id}",
        json={
            "name": "New Department",
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "New Department"
