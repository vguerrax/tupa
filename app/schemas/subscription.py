import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlanPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    slug: str
    name: str
    interval: str
    price_cents: int
    currency: str
    features: dict[str, Any]


class ChangePlanRequest(BaseModel):
    plan_id: uuid.UUID


class SubscriptionEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class PlanResponse(BaseModel):
    tenant_id: uuid.UUID
    subscription_id: uuid.UUID
    plan_id: uuid.UUID
    plan: str
    status: str
    limits: dict[str, Any]
    pending_plan: str | None = None
    pending_change_at: datetime | None = None


class ChangePlanResponse(PlanResponse):
    changed_immediately: bool
    event_type: str
