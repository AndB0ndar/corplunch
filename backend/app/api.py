from fastapi import APIRouter

from app.auth.router import router as auth_router
from app.catalog.router import router as catalog_router
from app.health import router as health_router
from app.users.me_router import router as me_router
from app.users.router import router as departments_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(me_router)
api_router.include_router(departments_router)
api_router.include_router(catalog_router)
