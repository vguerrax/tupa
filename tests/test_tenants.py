import uuid

import pytest

from app.services.subscription_service import MOARA_PRODUCT_ID

SERVICE_HEADERS = {
    "X-Service-Token": f"tupa_{MOARA_PRODUCT_ID.hex}_test-secret"
}


@pytest.mark.asyncio
async def test_create_tenant_and_get_real_free_plan(client):
    product_id = str(MOARA_PRODUCT_ID)

    create_response = await client.post(
        "/tenants",
        headers=SERVICE_HEADERS,
        json={"product_id": product_id, "name": "Moara Bakery"},
    )

    assert create_response.status_code == 201
    tenant = create_response.json()
    assert list(tenant) == ["tenant_id"]

    plan_response = await client.get(
        f"/tenants/{tenant['tenant_id']}/plan", headers=SERVICE_HEADERS
    )

    assert plan_response.status_code == 200
    plan = plan_response.json()
    assert plan["tenant_id"] == tenant["tenant_id"]
    assert plan["plan"] == "free"
    assert plan["status"] == "active"
    assert plan["pending_plan"] is None
    assert plan["limits"] == {
        "max_recipes": 10,
        "max_slots": 20,
        "max_users": 2,
        "max_ingredients": -1,
        "reports": False,
        "export": False,
    }


@pytest.mark.asyncio
async def test_get_plan_for_unknown_tenant_returns_404(client):
    response = await client.get(
        f"/tenants/{uuid.uuid4()}/plan", headers=SERVICE_HEADERS
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Tenant not found"}


@pytest.mark.asyncio
async def test_create_tenant_validates_input(client):
    response = await client.post(
        "/tenants", headers=SERVICE_HEADERS, json={"product_id": "invalid", "name": ""}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_tenant_requires_registered_product_with_free_plan(
    client, register_product
):
    product_id = uuid.uuid4()
    headers = await register_product(product_id)
    response = await client.post(
        "/tenants", headers=headers, json={"product_id": str(product_id), "name": "Unknown"}
    )

    assert response.status_code == 404
