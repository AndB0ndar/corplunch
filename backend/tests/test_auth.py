import bcrypt
from httpx import AsyncClient

from app.db import SessionLocal
from app.users.models import User, UserRole


async def create_user(
    email: str = "employee@test.local",
    password: str = "secret",
    role: UserRole = UserRole.EMPLOYEE,
) -> None:
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    async with SessionLocal() as session:
        session.add(
            User(
                email=email,
                password_hash=password_hash,
                full_name="Test User",
                role=role,
                is_active=True,
            )
        )
        await session.commit()


async def test_login_success(client: AsyncClient) -> None:
    await create_user()

    response = await client.post(
        "/api/auth/login",
        json={
            "email": "employee@test.local",
            "password": "secret",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_wrong_password(
    client: AsyncClient,
) -> None:
    await create_user()

    response = await client.post(
        "/api/auth/login",
        json={
            "email": "employee@test.local",
            "password": "wrong",
        },
    )

    assert response.status_code == 401


async def test_me_requires_token(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/me")

    assert response.status_code == 401


async def test_me_returns_current_user(
    client: AsyncClient,
) -> None:
    await create_user()

    login = await client.post(
        "/api/auth/login",
        json={
            "email": "employee@test.local",
            "password": "secret",
        },
    )

    token = login.json()["access_token"]

    response = await client.get(
        "/api/me",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["email"] == "employee@test.local"
    assert body["full_name"] == "Test User"
    assert body["role"] == "employee"
    assert "password_hash" not in body
