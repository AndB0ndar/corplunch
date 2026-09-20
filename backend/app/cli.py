import asyncio

import bcrypt
from sqlalchemy import select

from app.db import SessionLocal
from app.users.models import Department, User, UserRole


DEPARTMENTS = [
    "Разработка",
    "Закупки",
    "Администрация",
]


USERS = [
    {
        "email": "employee@kis.local",
        "password": "employee",
        "full_name": "Иван Сотрудник",
        "role": UserRole.EMPLOYEE,
        "department": "Разработка",
    },
    {
        "email": "employee2@kis.local",
        "password": "employee2",
        "full_name": "Пётр Сотрудник",
        "role": UserRole.EMPLOYEE,
        "department": "Разработка",
    },
    {
        "email": "procurement@kis.local",
        "password": "procurement",
        "full_name": "Анна Закупки",
        "role": UserRole.PROCUREMENT,
        "department": "Закупки",
    },
    {
        "email": "admin@kis.local",
        "password": "admin",
        "full_name": "Администратор",
        "role": UserRole.ADMIN,
        "department": "Администрация",
    },
]


async def seed_users() -> None:
    async with SessionLocal() as session:
        departments: dict[str, Department] = {}

        for name in DEPARTMENTS:
            department = await session.scalar(
                select(Department).where(
                    Department.name == name
                )
            )

            if department is None:
                department = Department(
                    name=name,
                )
                session.add(department)
                await session.flush()

            departments[name] = department

        for data in USERS:
            user = await session.scalar(
                select(User).where(
                    User.email == data["email"]
                )
            )

            if user is not None:
                continue

            password_hash = bcrypt.hashpw(
                data["password"].encode("utf-8"),
                bcrypt.gensalt(),
            ).decode("utf-8")

            user = User(
                email=data["email"],
                password_hash=password_hash,
                full_name=data["full_name"],
                role=data["role"],
                department_id=departments[
                    data["department"]
                ].id,
                daily_limit_kopecks=None,
                is_active=True,
            )

            session.add(user)

        await session.commit()

    print("seed-users: done")


def main() -> None:
    asyncio.run(seed_users())


if __name__ == "__main__":
    main()
