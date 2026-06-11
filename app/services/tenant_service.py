import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate
from app.schemas.subscription import PlanResponse
from app.services import subscription_service


async def create_tenant(session: AsyncSession, data: TenantCreate) -> Tenant:
    free_plan = await subscription_service.get_free_plan(session, data.product_id)
    tenant = Tenant(**data.model_dump())
    session.add(tenant)
    await session.flush()
    await subscription_service.create_free_subscription(session, tenant, free_plan)
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def get_tenant_plan(
    session: AsyncSession, tenant_id: uuid.UUID
) -> PlanResponse | None:
    return await subscription_service.get_tenant_plan(session, tenant_id)
