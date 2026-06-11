import base64
import hashlib
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

import bcrypt
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import get_settings

settings = get_settings()


def _load_keys() -> tuple[str, str]:
    if settings.jwt_private_key and settings.jwt_public_key:
        return (
            settings.jwt_private_key.replace("\\n", "\n"),
            settings.jwt_public_key.replace("\\n", "\n"),
        )
    if settings.environment == "production":
        raise RuntimeError("JWT_PRIVATE_KEY and JWT_PUBLIC_KEY are required in production")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem.decode(), public_pem.decode()


PRIVATE_KEY, PUBLIC_KEY = _load_keys()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def bcrypt_cost(password_hash: str) -> int:
    try:
        return int(password_hash.split("$")[2])
    except (IndexError, ValueError):
        return 0


def is_valid_bcrypt_hash(password_hash: str) -> bool:
    try:
        bcrypt.checkpw(b"", password_hash.encode())
    except ValueError:
        return False
    return True


def create_token(
    user_id: uuid.UUID, product_id: uuid.UUID, token_type: str
) -> tuple[str, uuid.UUID, datetime]:
    now = datetime.now(UTC)
    lifetime = (
        timedelta(minutes=settings.access_token_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    expires_at = now + lifetime
    jti = uuid.uuid4()
    payload = {
        "sub": str(user_id),
        "product_id": str(product_id),
        "type": token_type,
        "jti": str(jti),
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(
        payload,
        PRIVATE_KEY,
        algorithm="RS256",
        headers={"kid": settings.jwt_key_id},
    )
    return token, jti, expires_at


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        PUBLIC_KEY,
        algorithms=["RS256"],
        issuer=settings.jwt_issuer,
        options={"require": ["sub", "product_id", "type", "jti", "exp", "iat"]},
    )
    if payload["type"] != expected_type:
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload


def _base64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def jwks() -> dict[str, list[dict[str, str]]]:
    public_key = serialization.load_pem_public_key(PUBLIC_KEY.encode())
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise RuntimeError("Configured public key is not RSA")
    numbers = public_key.public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": settings.jwt_key_id,
                "n": _base64url_uint(numbers.n),
                "e": _base64url_uint(numbers.e),
            }
        ]
    }


class FixedWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= now - self.window_seconds:
                attempts.popleft()
            if len(attempts) >= self.limit:
                return False
            attempts.append(now)
            return True

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()


def rate_limit_key(product_id: uuid.UUID, email: str, client_host: str) -> str:
    value = f"{product_id}:{email.lower()}:{client_host}"
    return hashlib.sha256(value.encode()).hexdigest()
