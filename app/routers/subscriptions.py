import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import ensure_product_access, require_service_token
from app.models.subscription import Product
from app.models.tenant import Tenant
from app.schemas.subscription import (
    ChangePlanRequest,
    ChangePlanResponse,
    PlanPublic,
    SubscriptionEventResponse,
)
from app.services import subscription_service

router = APIRouter(tags=["subscriptions"])
Session = Annotated[AsyncSession, Depends(get_session)]
ServiceProduct = Annotated[Product, Depends(require_service_token)]


async def ensure_tenant_access(
    session: AsyncSession, tenant_id: uuid.UUID, product: Product
) -> None:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    ensure_product_access(product, tenant.product_id)


@router.get("/plans", response_model=list[PlanPublic])
async def list_plans(
    session: Session, product_id: uuid.UUID = Query(...)
) -> list[PlanPublic]:
    return await subscription_service.list_public_plans(session, product_id)


async def _change_plan(
    tenant_id: uuid.UUID,
    data: ChangePlanRequest,
    session: AsyncSession,
    direction: str,
) -> ChangePlanResponse:
    try:
        return await subscription_service.change_plan(
            session, tenant_id, data.plan_id, direction
        )
    except subscription_service.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except subscription_service.InvalidPlanChange as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/tenants/{tenant_id}/upgrade", response_model=ChangePlanResponse)
async def upgrade(
    tenant_id: uuid.UUID,
    data: ChangePlanRequest,
    session: Session,
    product: ServiceProduct,
) -> ChangePlanResponse:
    await ensure_tenant_access(session, tenant_id, product)
    return await _change_plan(tenant_id, data, session, "upgrade")


@router.post("/tenants/{tenant_id}/downgrade", response_model=ChangePlanResponse)
async def downgrade(
    tenant_id: uuid.UUID,
    data: ChangePlanRequest,
    session: Session,
    product: ServiceProduct,
) -> ChangePlanResponse:
    await ensure_tenant_access(session, tenant_id, product)
    return await _change_plan(tenant_id, data, session, "downgrade")


@router.get(
    "/tenants/{tenant_id}/events", response_model=list[SubscriptionEventResponse]
)
async def events(
    tenant_id: uuid.UUID, session: Session, product: ServiceProduct
) -> list[SubscriptionEventResponse]:
    await ensure_tenant_access(session, tenant_id, product)
    try:
        return await subscription_service.list_events(session, tenant_id)
    except subscription_service.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
