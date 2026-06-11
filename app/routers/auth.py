import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.dependencies import current_user_id, ensure_product_access, require_service_token
from app.models.subscription import Product
from app.schemas.auth import (
    Credentials,
    MessageResponse,
    MigratedUser,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from app.security import FixedWindowRateLimiter, jwks, rate_limit_key
from app.services import auth_service

settings = get_settings()
router = APIRouter(tags=["auth"])
Session = Annotated[AsyncSession, Depends(get_session)]
ServiceProduct = Annotated[Product, Depends(require_service_token)]
CurrentUser = Annotated[uuid.UUID, Depends(current_user_id)]
login_limiter = FixedWindowRateLimiter(
    settings.login_rate_limit, settings.login_rate_window_seconds
)


@router.post("/auth/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: Credentials, session: Session, product: ServiceProduct
) -> UserResponse:
    ensure_product_access(product, data.product_id)
    try:
        user = await auth_service.create_user(session, data)
    except auth_service.UserAlreadyExists as exc:
        raise HTTPException(status_code=409, detail="User already exists") from exc
    return UserResponse(user_id=user.id)


@router.post("/auth/migrate", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def migrate_user(
    data: MigratedUser, session: Session, product: ServiceProduct
) -> UserResponse:
    ensure_product_access(product, data.product_id)
    try:
        user = await auth_service.migrate_user(session, data)
    except auth_service.UserAlreadyExists as exc:
        raise HTTPException(status_code=409, detail="User already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UserResponse(user_id=user.id)


@router.post("/auth/token", response_model=TokenResponse)
async def token(data: Credentials, request: Request, session: Session) -> TokenResponse:
    host = request.client.host if request.client else "unknown"
    if not login_limiter.allow(rate_limit_key(data.product_id, str(data.email), host)):
        raise HTTPException(status_code=429, detail="Too many login attempts")
    try:
        return await auth_service.authenticate(session, data)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid credentials") from exc


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, session: Session) -> TokenResponse:
    try:
        return await auth_service.refresh(session, data.refresh_token)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc


@router.post("/auth/logout", response_model=MessageResponse)
async def logout(user_id: CurrentUser, session: Session) -> MessageResponse:
    await auth_service.revoke_all(session, user_id)
    return MessageResponse(detail="Logged out")


@router.get("/.well-known/jwks")
async def get_jwks() -> dict[str, list[dict[str, str]]]:
    return jwks()
