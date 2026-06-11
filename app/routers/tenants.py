import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.tenant import PlanResponse, TenantCreate, TenantResponse
from app.services import tenant_service

router = APIRouter(prefix="/tenants", tags=["tenants"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(data: TenantCreate, session: Session) -> TenantResponse:
    tenant = await tenant_service.create_tenant(session, data)
    return TenantResponse(tenant_id=tenant.id)


@router.get("/{tenant_id}/plan", response_model=PlanResponse)
async def get_tenant_plan(tenant_id: uuid.UUID, session: Session) -> PlanResponse:
    plan = await tenant_service.get_tenant_plan(session, tenant_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return plan
