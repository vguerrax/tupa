import uuid

import bcrypt
import jwt
import pytest

from app.config import get_settings
from app.security import PUBLIC_KEY

PASSWORD = "very-secret-password"


async def create_user(
    client, product_id, headers, email="user@example.com", password=PASSWORD
):
    response = await client.post(
        "/auth/users",
        headers=headers,
        json={"product_id": str(product_id), "email": email, "password": password},
    )
    assert response.status_code == 201
    return response.json()["user_id"]


async def login(client, product_id, email="user@example.com", password=PASSWORD):
    return await client.post(
        "/auth/token",
        json={"product_id": str(product_id), "email": email, "password": password},
    )


@pytest.mark.asyncio
async def test_login_issues_rs256_tokens_with_required_claims(client, register_product):
    product_id = uuid.uuid4()
    headers = await register_product(product_id)
    user_id = await create_user(client, product_id, headers)

    response = await login(client, product_id)

    assert response.status_code == 200
    tokens = response.json()
    access_payload = jwt.decode(
        tokens["access_token"],
        PUBLIC_KEY,
        algorithms=["RS256"],
        issuer=get_settings().jwt_issuer,
    )
    refresh_payload = jwt.decode(
        tokens["refresh_token"],
        PUBLIC_KEY,
        algorithms=["RS256"],
        issuer=get_settings().jwt_issuer,
    )
    assert access_payload["sub"] == user_id
    assert access_payload["product_id"] == str(product_id)
    assert access_payload["type"] == "access"
    assert refresh_payload["type"] == "refresh"
    assert access_payload["jti"] != refresh_payload["jti"]
    assert tokens["expires_in"] == get_settings().access_token_minutes * 60


@pytest.mark.asyncio
async def test_same_email_is_isolated_by_product(client, register_product):
    first_product = uuid.uuid4()
    second_product = uuid.uuid4()
    first_headers = await register_product(first_product)
    second_headers = await register_product(second_product)
    await create_user(client, first_product, first_headers)
    await create_user(
        client, second_product, second_headers, password="different-password"
    )

    wrong_product_login = await login(client, second_product)
    correct_product_login = await login(
        client, second_product, password="different-password"
    )

    assert wrong_product_login.status_code == 401
    assert correct_product_login.status_code == 200


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_rejects_reuse(client, register_product):
    product_id = uuid.uuid4()
    headers = await register_product(product_id)
    await create_user(client, product_id, headers)
    tokens = (await login(client, product_id)).json()

    refreshed = await client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    reused = await client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != tokens["refresh_token"]
    assert reused.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_all_refresh_tokens(client, register_product):
    product_id = uuid.uuid4()
    headers = await register_product(product_id)
    await create_user(client, product_id, headers)
    first = (await login(client, product_id)).json()
    second = (await login(client, product_id)).json()

    response = await client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {first['access_token']}"}
    )

    assert response.status_code == 200
    for refresh_token in (first["refresh_token"], second["refresh_token"]):
        refresh_response = await client.post(
            "/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_lazy_migration_accepts_bcrypt_and_upgrades_cost_on_login(
    client, register_product
):
    product_id = uuid.uuid4()
    headers = await register_product(product_id)
    old_hash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()

    migration = await client.post(
        "/auth/migrate",
        headers=headers,
        json={
            "product_id": str(product_id),
            "email": "legacy@example.com",
            "password_hash": old_hash,
        },
    )
    logged_in = await login(client, product_id, email="legacy@example.com")

    assert migration.status_code == 201
    assert logged_in.status_code == 200


@pytest.mark.asyncio
async def test_internal_endpoints_require_service_token(client):
    response = await client.post(
        "/auth/users",
        json={
            "product_id": str(uuid.uuid4()),
            "email": "user@example.com",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_migration_rejects_invalid_bcrypt_hash(client, register_product):
    product_id = uuid.uuid4()
    headers = await register_product(product_id)
    response = await client.post(
        "/auth/migrate",
        headers=headers,
        json={
            "product_id": str(product_id),
            "email": "legacy@example.com",
            "password_hash": "$2b$12$not-a-valid-hash",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_product_token_cannot_access_another_product(client, register_product):
    first_product = uuid.uuid4()
    second_product = uuid.uuid4()
    first_headers = await register_product(first_product)
    await register_product(second_product)

    response = await client.post(
        "/auth/users",
        headers=first_headers,
        json={
            "product_id": str(second_product),
            "email": "user@example.com",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_jwks_exposes_rs256_public_key(client):
    response = await client.get("/.well-known/jwks")

    assert response.status_code == 200
    key = response.json()["keys"][0]
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert "n" in key and "e" in key and "kid" in key


@pytest.mark.asyncio
async def test_login_is_rate_limited(client):
    product_id = uuid.uuid4()
    payload = {
        "product_id": str(product_id),
        "email": "limited@example.com",
        "password": PASSWORD,
    }

    for _ in range(get_settings().login_rate_limit):
        response = await client.post("/auth/token", json=payload)
        assert response.status_code == 401

    response = await client.post("/auth/token", json=payload)

    assert response.status_code == 429
