from fastapi import FastAPI

from app.config import get_settings
from app.routers.auth import router as auth_router
from app.routers.admin import router as admin_router
from app.routers.subscriptions import router as subscriptions_router
from app.routers.tenants import router as tenants_router

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(tenants_router)
app.include_router(subscriptions_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
