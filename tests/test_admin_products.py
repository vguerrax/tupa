import base64
import re
import uuid

import pytest
from sqlalchemy import select

from app.models.subscription import Product


def admin_headers(username="admin", password="change-me"):
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {credentials}"}


@pytest.mark.asyncio
async def test_products_page_requires_admin_authentication(client):
    response = await client.get("/admin/products")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


@pytest.mark.asyncio
async def test_admin_can_create_and_list_product_with_free_plan(client):
    response = await client.post(
        "/admin/products",
        headers=admin_headers(),
        data={"name": "Produto Dois", "slug": "produto-dois"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Produto cadastrado com plano free ilimitado." in response.text
    assert "Produto Dois" in response.text
    assert "produto-dois" in response.text
    assert "Token gerado. Copie agora" in response.text
    assert "Cache-Control" in response.headers
    assert response.headers["Cache-Control"] == "no-store"

    product_id = response.text.split("produto-dois</td>", 1)[1].split("<code>", 1)[1].split(
        "</code>", 1
    )[0]
    plans = await client.get(f"/plans?product_id={product_id}")
    assert plans.status_code == 200
    assert plans.json()[0]["slug"] == "free"
    assert plans.json()[0]["features"]["max_users"] == -1


@pytest.mark.asyncio
async def test_rotating_product_token_invalidates_previous_token(client, session_factory):
    created = await client.post(
        "/admin/products",
        headers=admin_headers(),
        data={"name": "Produto Dois", "slug": "produto-dois"},
    )
    old_token = re.search(r"tupa_[a-f0-9]{32}_[A-Za-z0-9_-]+", created.text).group()
    product_id = old_token.split("_")[1]

    rotated = await client.post(
        f"/admin/products/{product_id}/rotate-token", headers=admin_headers()
    )
    new_token = re.search(r"tupa_[a-f0-9]{32}_[A-Za-z0-9_-]+", rotated.text).group()

    assert rotated.headers["Cache-Control"] == "no-store"
    assert new_token != old_token
    payload = {"product_id": str(product_id), "name": "Tenant"}
    rejected = await client.post(
        "/tenants", headers={"X-Service-Token": old_token}, json=payload
    )
    accepted = await client.post(
        "/tenants", headers={"X-Service-Token": new_token}, json=payload
    )
    assert rejected.status_code == 401
    assert accepted.status_code == 201

    async with session_factory() as session:
        product = await session.scalar(
            select(Product).where(Product.id == uuid.UUID(product_id))
        )
        assert product.service_token_hash != new_token
        assert product.service_token_hint == new_token[-8:]


@pytest.mark.asyncio
async def test_duplicate_slug_returns_form_error(client):
    payload = {"name": "Produto Dois", "slug": "produto-dois"}
    await client.post("/admin/products", headers=admin_headers(), data=payload)

    response = await client.post(
        "/admin/products", headers=admin_headers(), data=payload
    )

    assert response.status_code == 422
    assert "Ja existe um produto com este slug." in response.text
