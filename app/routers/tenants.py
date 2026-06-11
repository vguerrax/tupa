import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import ensure_product_access, require_service_token
from app.models.subscription import Product
from app.models.tenant import Tenant
from app.schemas.subscription import PlanResponse
from app.schemas.tenant import TenantCreate, TenantResponse
from app.services import tenant_service
from app.services.subscription_service import NotFound

router = APIRouter(prefix="/tenants", tags=["tenants"])
Session = Annotated[AsyncSession, Depends(get_session)]
ServiceProduct = Annotated[Product, Depends(require_service_token)]


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    data: TenantCreate, session: Session, product: ServiceProduct
) -> TenantResponse:
    ensure_product_access(product, data.product_id)
    try:
        tenant = await tenant_service.create_tenant(session, data)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TenantResponse(tenant_id=tenant.id)


@router.get("/{tenant_id}/plan", response_model=PlanResponse)
async def get_tenant_plan(
    tenant_id: uuid.UUID, session: Session, product: ServiceProduct
) -> PlanResponse:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is not None:
        ensure_product_access(product, tenant.product_id)
    plan = await tenant_service.get_tenant_plan(session, tenant_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return plan
