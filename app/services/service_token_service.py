import hashlib
import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Product

TOKEN_PREFIX = "tupa"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def build_token(product_id: uuid.UUID, secret: str | None = None) -> str:
    return f"{TOKEN_PREFIX}_{product_id.hex}_{secret or secrets.token_urlsafe(32)}"


def product_id_from_token(token: str) -> uuid.UUID | None:
    try:
        prefix, product_hex, _ = token.split("_", 2)
        if prefix != TOKEN_PREFIX:
            return None
        return uuid.UUID(hex=product_hex)
    except (ValueError, AttributeError):
        return None


async def rotate_token(session: AsyncSession, product: Product) -> str:
    token = build_token(product.id)
    product.service_token_hash = hash_token(token)
    product.service_token_hint = token[-8:]
    await session.commit()
    await session.refresh(product)
    return token
