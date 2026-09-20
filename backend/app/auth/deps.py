from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.users.models import User


bearer_scheme = HTTPBearer(
    auto_error=False,
)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
        )

        user_id = payload.get("sub")

        if user_id is None:
            raise ValueError("Token subject is missing")

        user_id = int(user_id)

    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = await session.scalar(
        select(User).where(User.id == user_id)
    )

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


CurrentUser = Annotated[
    User,
    Depends(get_current_user),
]


async def require_admin(
    user: CurrentUser,
) -> User:
    if user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    return user


async def require_procurement(
    user: CurrentUser,
) -> User:
    if user.role.value not in {"procurement", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    return user


def create_access_token(user: User) -> str:
    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=settings.jwt_expire_minutes)
    )

    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm="HS256",
    )
