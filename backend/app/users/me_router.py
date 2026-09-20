from fastapi import APIRouter

from app.auth import CurrentUser
from app.users.schemas import MeResponse


router = APIRouter(
    tags=["auth"],
)


@router.get(
    "/me",
    response_model=MeResponse,
)
async def get_me(
    user: CurrentUser,
) -> MeResponse:
    return user
