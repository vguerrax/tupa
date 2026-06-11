import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.schemas.tenant import PlanResponse, TenantCreate


async def create_tenant(session: AsyncSession, data: TenantCreate) -> Tenant:
    tenant = Tenant(**data.model_dump())
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def get_tenant_plan(
    session: AsyncSession, tenant_id: uuid.UUID
) -> PlanResponse | None:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        return None
    return PlanResponse(tenant_id=tenant.id)
