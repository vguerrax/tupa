import uuid
from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    product_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)


class TenantResponse(BaseModel):
    tenant_id: uuid.UUID


class PlanLimits(BaseModel):
    max_recipes: int = -1
    max_slots: int = -1
    max_users: int = -1
    max_ingredients: int = -1


class PlanResponse(BaseModel):
    tenant_id: uuid.UUID
    plan: str = "free"
    status: str = "active"
    limits: PlanLimits = Field(default_factory=PlanLimits)
