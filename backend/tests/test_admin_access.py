"""Auth/admin access gaps: 403 for non-admin on /api/admin/*, list users CRUD."""

import pytest
from httpx import AsyncClient

ADMIN_GET_PATHS = (
    "/api/admin/users",
    "/api/admin/departments",
    "/api/admin/settings",
)


@pytest.mark.parametrize("path", ADMIN_GET_PATHS)
async def test_employee_forbidden_on_admin_get(
    client: AsyncClient,
    employee_headers: dict[str, str],
    path: str,
) -> None:
    response = await client.get(path, headers=employee_headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"


@pytest.mark.parametrize("path", ADMIN_GET_PATHS)
async def test_procurement_forbidden_on_admin_get(
    client: AsyncClient,
    procurement_headers: dict[str, str],
    path: str,
) -> None:
    response = await client.get(path, headers=procurement_headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"


async def test_employee_forbidden_on_admin_mutations(
    client: AsyncClient,
    employee_headers: dict[str, str],
) -> None:
    create_user = await client.post(
        "/api/admin/users",
        headers=employee_headers,
        json={
            "email": "nope@test.local",
            "password": "password",
            "full_name": "Nope",
            "role": "employee",
        },
    )
    assert create_user.status_code == 403

    create_dept = await client.post(
        "/api/admin/departments",
        headers=employee_headers,
        json={"name": "Forbidden Dept"},
    )
    assert create_dept.status_code == 403

    put_settings = await client.put(
        "/api/admin/settings",
        headers=employee_headers,
        json={
            "cutoff_time": "16:00",
            "timezone": "Europe/Moscow",
            "mealty_city": "Москва",
            "daily_limit_kopecks": None,
            "catalog_sync_per_day": 2,
        },
    )
    assert put_settings.status_code == 403


async def test_procurement_forbidden_on_admin_mutations(
    client: AsyncClient,
    procurement_headers: dict[str, str],
) -> None:
    create_user = await client.post(
        "/api/admin/users",
        headers=procurement_headers,
        json={
            "email": "proc-nope@test.local",
            "password": "password",
            "full_name": "Nope",
            "role": "employee",
        },
    )
    assert create_user.status_code == 403

    create_dept = await client.post(
        "/api/admin/departments",
        headers=procurement_headers,
        json={"name": "Proc Forbidden"},
    )
    assert create_dept.status_code == 403

    put_settings = await client.put(
        "/api/admin/settings",
        headers=procurement_headers,
        json={
            "cutoff_time": "15:00",
            "timezone": "Europe/Moscow",
            "mealty_city": "Москва",
            "daily_limit_kopecks": 1000,
            "catalog_sync_per_day": 1,
        },
    )
    assert put_settings.status_code == 403


async def test_admin_bearer_lists_and_gets_users(
    client: AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    """Real admin JWT (not require_admin override): list + create visible in GET."""
    headers = admin_headers

    created = await client.post(
        "/api/admin/users",
        headers=headers,
        json={
            "email": "listed@test.local",
            "password": "password",
            "full_name": "Listed User",
            "role": "employee",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert "password_hash" not in created.json()

    listed = await client.get("/api/admin/users", headers=headers)
    assert listed.status_code == 200
    rows = listed.json()
    match = next(row for row in rows if row["id"] == user_id)
    assert match["email"] == "listed@test.local"
    assert match["full_name"] == "Listed User"
    assert match["role"] == "employee"
    assert match["is_active"] is True
    assert "password_hash" not in match

    patched = await client.patch(
        f"/api/admin/users/{user_id}",
        headers=headers,
        json={"full_name": "Listed Renamed"},
    )
    assert patched.status_code == 200
    assert patched.json()["full_name"] == "Listed Renamed"

    listed_again = await client.get("/api/admin/users", headers=headers)
    again = next(row for row in listed_again.json() if row["id"] == user_id)
    assert again["full_name"] == "Listed Renamed"


async def test_employee_forbidden_on_admin_user_patch(
    client: AsyncClient,
    employee_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    created = await client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "email": "patch-deny@test.local",
            "password": "password",
            "full_name": "Target",
            "role": "employee",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]

    denied = await client.patch(
        f"/api/admin/users/{user_id}",
        headers=employee_headers,
        json={"full_name": "Hacker"},
    )
    assert denied.status_code == 403
