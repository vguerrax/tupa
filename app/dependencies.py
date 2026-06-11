import secrets
import uuid
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials, HTTPBearer

from app.config import get_settings
from app.database import get_session
from app.models.subscription import Product
from app.security import decode_token
from app.services.service_token_service import hash_token, product_id_from_token
from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()
bearer = HTTPBearer(auto_error=False)
basic = HTTPBasic()


async def require_service_token(
    x_service_token: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> Product:
    product_id = product_id_from_token(x_service_token) if x_service_token else None
    product = await session.get(Product, product_id) if product_id else None
    if (
        product is None
        or product.service_token_hash is None
        or not secrets.compare_digest(product.service_token_hash, hash_token(x_service_token))
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return product


def ensure_product_access(product: Product, product_id: uuid.UUID) -> None:
    if product.id != product_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Product mismatch")


async def current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> uuid.UUID:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    try:
        payload = decode_token(credentials.credentials, "access")
        return uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
        ) from exc


async def require_admin(
    credentials: Annotated[HTTPBasicCredentials, Depends(basic)],
) -> str:
    valid_username = secrets.compare_digest(credentials.username, settings.admin_username)
    valid_password = secrets.compare_digest(
        credentials.password, settings.effective_admin_password
    )
    if not (valid_username and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
