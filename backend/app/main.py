from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import engine
from app.health import router as health_router
from app.users.router import router as departments_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(title="CorpLunch", lifespan=lifespan)
app.include_router(health_router, prefix="/api")
app.include_router(departments_router, prefix="/api")

