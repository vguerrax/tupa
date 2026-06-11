import base64
import uuid

import pytest

from app.services.subscription_service import MOARA_PLAN_IDS, MOARA_PRODUCT_ID


def admin_headers(username="admin", password="change-me"):
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {credentials}"}


def plan_payload(**overrides):
    payload = {
        "product_id": str(MOARA_PRODUCT_ID),
        "name": "Business",
        "slug": "business",
        "position": "4",
        "price_cents": "12990",
        "currency": "BRL",
        "max_recipes": "500",
        "max_slots": "1000",
        "max_users": "20",
        "max_ingredients": "-1",
        "reports": "complete",
        "export": "true",
        "is_active": "true",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_plans_page_requires_admin_authentication(client):
    response = await client.get("/admin/plans")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_can_create_plan_and_it_becomes_public(client):
    response = await client.post(
        "/admin/plans",
        headers=admin_headers(),
        data=plan_payload(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Plano salvo com sucesso." in response.text
    assert "Business" in response.text

    public = await client.get(f"/plans?product_id={MOARA_PRODUCT_ID}")
    plan = next(item for item in public.json() if item["slug"] == "business")
    assert plan["price_cents"] == 12990
    assert plan["features"]["max_users"] == 20
    assert plan["features"]["export"] is True


@pytest.mark.asyncio
async def test_admin_can_edit_and_deactivate_plan(client):
    await client.post("/admin/plans", headers=admin_headers(), data=plan_payload())
    public = await client.get(f"/plans?product_id={MOARA_PRODUCT_ID}")
    plan_id = next(item["id"] for item in public.json() if item["slug"] == "business")

    response = await client.post(
        "/admin/plans",
        headers=admin_headers(),
        data=plan_payload(
            plan_id=plan_id,
            name="Business Plus",
            price_cents="15990",
            max_users="30",
            is_active="",
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Business Plus" in response.text
    public = await client.get(f"/plans?product_id={MOARA_PRODUCT_ID}")
    assert all(item["id"] != plan_id for item in public.json())


@pytest.mark.asyncio
async def test_free_plan_cannot_be_deactivated(client):
    response = await client.post(
        "/admin/plans",
        headers=admin_headers(),
        data=plan_payload(
            plan_id=str(MOARA_PLAN_IDS["free"]),
            name="Free",
            slug="free",
            position="0",
            price_cents="0",
            is_active="",
        ),
    )

    assert response.status_code == 422
    assert "O plano free nao pode ser desativado." in response.text


@pytest.mark.asyncio
async def test_duplicate_plan_slug_returns_error(client):
    response = await client.post(
        "/admin/plans",
        headers=admin_headers(),
        data=plan_payload(slug="pro"),
    )

    assert response.status_code == 422
    assert "Ja existe um plano com este slug no produto." in response.text
