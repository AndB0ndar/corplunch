import argparse
import asyncio
from pathlib import Path

import bcrypt
from sqlalchemy import select

from app.catalog.service import upsert_catalog
from app.db import SessionLocal
from app.providers import parse_html
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

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "mealty_catalog.html"
)


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


async def sync_from_fixture() -> None:
    if not FIXTURE_PATH.is_file():
        raise SystemExit(f"Fixture not found: {FIXTURE_PATH}")

    dishes = parse_html(FIXTURE_PATH.read_text(encoding="utf-8"))
    if not dishes:
        raise SystemExit("Fixture produced an empty catalog")

    async with SessionLocal() as session:
        result = await upsert_catalog(session, "mealty", dishes)

    print(
        "sync-from-fixture: "
        f"upserted={result.upserted} "
        f"unavailable={result.unavailable} "
        f"recorded_at={result.recorded_at.isoformat()}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="CorpLunch backend CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "seed-users",
        help="Create demo departments and users",
    )
    sub.add_parser(
        "sync-from-fixture",
        help="Upsert catalog from mealty_catalog.html fixture",
    )

    args = parser.parse_args()

    if args.command == "seed-users":
        asyncio.run(seed_users())
    elif args.command == "sync-from-fixture":
        asyncio.run(sync_from_fixture())
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
