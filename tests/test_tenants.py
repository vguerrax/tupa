import uuid

import pytest


@pytest.mark.asyncio
async def test_create_tenant_and_get_unlimited_free_plan(client):
    product_id = str(uuid.uuid4())

    create_response = await client.post(
        "/tenants", json={"product_id": product_id, "name": "Moara Bakery"}
    )

    assert create_response.status_code == 201
    tenant = create_response.json()
    assert list(tenant) == ["tenant_id"]

    plan_response = await client.get(f"/tenants/{tenant['tenant_id']}/plan")

    assert plan_response.status_code == 200
    assert plan_response.json() == {
        "tenant_id": tenant["tenant_id"],
        "plan": "free",
        "status": "active",
        "limits": {
            "max_recipes": -1,
            "max_slots": -1,
            "max_users": -1,
            "max_ingredients": -1,
        },
    }


@pytest.mark.asyncio
async def test_get_plan_for_unknown_tenant_returns_404(client):
    response = await client.get(f"/tenants/{uuid.uuid4()}/plan")

    assert response.status_code == 404
    assert response.json() == {"detail": "Tenant not found"}


@pytest.mark.asyncio
async def test_create_tenant_validates_input(client):
    response = await client.post(
        "/tenants", json={"product_id": "invalid", "name": ""}
    )

    assert response.status_code == 422
