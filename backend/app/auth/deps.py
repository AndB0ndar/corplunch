from fastapi import HTTPException, status


async def get_current_user() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


async def require_admin() -> None:
    await get_current_user()
