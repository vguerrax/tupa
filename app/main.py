from fastapi import FastAPI

from app.config import get_settings
from app.routers.tenants import router as tenants_router

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(tenants_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
