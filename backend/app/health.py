from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import engine

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    database: str = Field(examples=["up"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc
    return HealthResponse(status="ok", database="up")
