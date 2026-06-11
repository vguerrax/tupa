from datetime import UTC, datetime, timedelta
import uuid

import pytest
from sqlalchemy import select

from app.models.subscription import Subscription
from app.services.subscription_service import MOARA_PLAN_IDS, MOARA_PRODUCT_ID

SERVICE_HEADERS = {
    "X-Service-Token": f"tupa_{MOARA_PRODUCT_ID.hex}_test-secret"
}


async def create_tenant(client):
    response = await client.post(
        "/tenants",
        headers=SERVICE_HEADERS,
        json={"product_id": str(MOARA_PRODUCT_ID), "name": "Moara Bakery"},
    )
    assert response.status_code == 201
    return response.json()["tenant_id"]


@pytest.mark.asyncio
async def test_lists_active_moara_plans_in_order(client):
    response = await client.get(f"/plans?product_id={MOARA_PRODUCT_ID}")

    assert response.status_code == 200
    plans = response.json()
    assert [plan["slug"] for plan in plans] == ["free", "starter", "pro", "pro-plus"]
    assert plans[0]["price_cents"] == 0
    assert plans[-1]["features"]["max_recipes"] == -1


@pytest.mark.asyncio
async def test_upgrade_changes_plan_immediately_and_expands_limits(client):
    tenant_id = await create_tenant(client)

    response = await client.post(
        f"/tenants/{tenant_id}/upgrade",
        headers=SERVICE_HEADERS,
        json={"plan_id": str(MOARA_PLAN_IDS["pro"])},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["changed_immediately"] is True
    assert result["plan"] == "pro"
    assert result["limits"]["max_recipes"] == 200
    assert result["event_type"] == "subscription.upgraded"


@pytest.mark.asyncio
async def test_downgrade_is_scheduled_without_deleting_or_reducing_current_plan(client):
    tenant_id = await create_tenant(client)
    await client.post(
        f"/tenants/{tenant_id}/upgrade",
        headers=SERVICE_HEADERS,
        json={"plan_id": str(MOARA_PLAN_IDS["pro"])},
    )

    response = await client.post(
        f"/tenants/{tenant_id}/downgrade",
        headers=SERVICE_HEADERS,
        json={"plan_id": str(MOARA_PLAN_IDS["free"])},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["changed_immediately"] is False
    assert result["plan"] == "pro"
    assert result["pending_plan"] == "free"
    assert result["pending_change_at"] is not None
    assert result["limits"]["max_recipes"] == 200
    assert result["event_type"] == "subscription.downgrade_scheduled"


@pytest.mark.asyncio
async def test_invalid_plan_direction_is_rejected(client):
    tenant_id = await create_tenant(client)

    response = await client.post(
        f"/tenants/{tenant_id}/downgrade",
        headers=SERVICE_HEADERS,
        json={"plan_id": str(MOARA_PLAN_IDS["pro"])},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_subscription_events_are_auditable_and_protected(client):
    tenant_id = await create_tenant(client)
    await client.post(
        f"/tenants/{tenant_id}/upgrade",
        headers=SERVICE_HEADERS,
        json={"plan_id": str(MOARA_PLAN_IDS["starter"])},
    )

    unauthorized = await client.get(f"/tenants/{tenant_id}/events")
    response = await client.get(
        f"/tenants/{tenant_id}/events", headers=SERVICE_HEADERS
    )

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert [event["event_type"] for event in response.json()] == [
        "subscription.created",
        "subscription.upgraded",
    ]


@pytest.mark.asyncio
async def test_due_downgrade_is_applied_when_plan_is_read(client, session_factory):
    tenant_id = await create_tenant(client)
    await client.post(
        f"/tenants/{tenant_id}/upgrade",
        headers=SERVICE_HEADERS,
        json={"plan_id": str(MOARA_PLAN_IDS["pro"])},
    )
    await client.post(
        f"/tenants/{tenant_id}/downgrade",
        headers=SERVICE_HEADERS,
        json={"plan_id": str(MOARA_PLAN_IDS["free"])},
    )
    async with session_factory() as session:
        subscription = await session.scalar(
            select(Subscription).where(Subscription.tenant_id == uuid.UUID(tenant_id))
        )
        subscription.current_period_end = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    response = await client.get(f"/tenants/{tenant_id}/plan", headers=SERVICE_HEADERS)

    assert response.status_code == 200
    assert response.json()["plan"] == "free"
    assert response.json()["pending_plan"] is None
    assert response.json()["pending_change_at"] is None
