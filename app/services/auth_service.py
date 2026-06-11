import uuid
from datetime import UTC, datetime

import jwt
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.auth import RefreshToken, User
from app.schemas.auth import Credentials, MigratedUser, TokenResponse
from app.security import (
    bcrypt_cost,
    create_token,
    decode_token,
    hash_password,
    is_valid_bcrypt_hash,
    verify_password,
)

settings = get_settings()


class AuthError(Exception):
    pass


class UserAlreadyExists(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def _persist_user(session: AsyncSession, user: User) -> User:
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise UserAlreadyExists from exc
    await session.refresh(user)
    return user


async def create_user(session: AsyncSession, data: Credentials) -> User:
    return await _persist_user(
        session,
        User(
            product_id=data.product_id,
            email=normalize_email(str(data.email)),
            password_hash=hash_password(data.password),
        ),
    )


async def migrate_user(session: AsyncSession, data: MigratedUser) -> User:
    if not is_valid_bcrypt_hash(data.password_hash):
        raise ValueError("Only valid bcrypt hashes can be migrated")
    return await _persist_user(
        session,
        User(
            product_id=data.product_id,
            email=normalize_email(str(data.email)),
            password_hash=data.password_hash,
        ),
    )


async def _issue_pair(session: AsyncSession, user: User) -> TokenResponse:
    access_token, _, _ = create_token(user.id, user.product_id, "access")
    refresh_token, refresh_jti, refresh_expires_at = create_token(
        user.id, user.product_id, "refresh"
    )
    session.add(
        RefreshToken(
            jti=refresh_jti,
            user_id=user.id,
            product_id=user.product_id,
            expires_at=refresh_expires_at,
        )
    )
    await session.commit()
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_minutes * 60,
    )


async def authenticate(session: AsyncSession, data: Credentials) -> TokenResponse:
    user = await session.scalar(
        select(User).where(
            User.product_id == data.product_id,
            User.email == normalize_email(str(data.email)),
        )
    )
    if user is None or not verify_password(data.password, user.password_hash):
        raise AuthError
    if bcrypt_cost(user.password_hash) < 12:
        user.password_hash = hash_password(data.password)
    return await _issue_pair(session, user)


async def refresh(session: AsyncSession, token: str) -> TokenResponse:
    try:
        payload = decode_token(token, "refresh")
        jti = uuid.UUID(payload["jti"])
        user_id = uuid.UUID(payload["sub"])
        product_id = uuid.UUID(payload["product_id"])
    except (jwt.InvalidTokenError, ValueError, KeyError) as exc:
        raise AuthError from exc

    stored_token = await session.scalar(
        select(RefreshToken).where(RefreshToken.jti == jti).with_for_update()
    )
    now = datetime.now(UTC)
    if stored_token is None:
        raise AuthError
    expires_at = stored_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        stored_token.revoked_at is not None
        or expires_at < now
        or stored_token.user_id != user_id
        or stored_token.product_id != product_id
    ):
        raise AuthError

    user = await session.get(User, user_id)
    if user is None or user.product_id != product_id:
        raise AuthError

    stored_token.revoked_at = now
    return await _issue_pair(session, user)


async def revoke_all(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()
