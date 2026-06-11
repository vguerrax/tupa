import uuid
from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    product_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)


class TenantResponse(BaseModel):
    tenant_id: uuid.UUID

