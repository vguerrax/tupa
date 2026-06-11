import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.subscription import Plan, Product, Subscription, SubscriptionEvent
from app.models.tenant import Tenant
from app.schemas.subscription import ChangePlanResponse, PlanResponse

MOARA_PRODUCT_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
MOARA_PLAN_IDS = {
    "free": uuid.UUID("20000000-0000-0000-0000-000000000001"),
    "starter": uuid.UUID("20000000-0000-0000-0000-000000000002"),
    "pro": uuid.UUID("20000000-0000-0000-0000-000000000003"),
    "pro-plus": uuid.UUID("20000000-0000-0000-0000-000000000004"),
}
MOARA_PLANS = [
    {
        "id": MOARA_PLAN_IDS["free"],
        "slug": "free",
        "name": "Free",
        "position": 0,
        "price_cents": 0,
        "features": {
            "max_recipes": 10,
            "max_slots": 20,
            "max_users": 2,
            "max_ingredients": -1,
            "reports": False,
            "export": False,
        },
    },
    {
        "id": MOARA_PLAN_IDS["starter"],
        "slug": "starter",
        "name": "Starter",
        "position": 1,
        "price_cents": 0,
        "features": {
            "max_recipes": 50,
            "max_slots": 100,
            "max_users": 4,
            "max_ingredients": -1,
            "reports": "basic",
            "export": False,
        },
    },
    {
        "id": MOARA_PLAN_IDS["pro"],
        "slug": "pro",
        "name": "Pro",
        "position": 2,
        "price_cents": 0,
        "features": {
            "max_recipes": 200,
            "max_slots": 500,
            "max_users": 10,
            "max_ingredients": -1,
            "reports": "complete",
            "export": True,
        },
    },
    {
        "id": MOARA_PLAN_IDS["pro-plus"],
        "slug": "pro-plus",
        "name": "Pro+",
        "position": 3,
        "price_cents": 0,
        "features": {
            "max_recipes": -1,
            "max_slots": -1,
            "max_users": -1,
            "max_ingredients": -1,
            "reports": "complete",
            "export": True,
        },
    },
]


class SubscriptionError(Exception):
    pass


class NotFound(SubscriptionError):
    pass


class InvalidPlanChange(SubscriptionError):
    pass


async def seed_moara_plans(session: AsyncSession) -> None:
    product = await session.get(Product, MOARA_PRODUCT_ID)
    if product is None:
        session.add(Product(id=MOARA_PRODUCT_ID, slug="moara", name="Moara"))
    for data in MOARA_PLANS:
        if await session.get(Plan, data["id"]) is None:
            session.add(Plan(product_id=MOARA_PRODUCT_ID, **data))
    await session.commit()


async def get_free_plan(session: AsyncSession, product_id: uuid.UUID) -> Plan:
    plan = await session.scalar(
        select(Plan).where(
            Plan.product_id == product_id, Plan.slug == "free", Plan.is_active.is_(True)
        )
    )
    if plan is None:
        raise NotFound("Product or free plan not found")
    return plan


def add_event(
    session: AsyncSession,
    subscription: Subscription,
    event_type: str,
    payload: dict,
) -> None:
    session.add(
        SubscriptionEvent(
            subscription_id=subscription.id, event_type=event_type, payload=payload
        )
    )


async def create_free_subscription(
    session: AsyncSession, tenant: Tenant, plan: Plan
) -> Subscription:
    now = datetime.now(UTC)
    subscription = Subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status="active",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    session.add(subscription)
    await session.flush()
    add_event(
        session,
        subscription,
        "subscription.created",
        {"plan_id": str(plan.id), "plan": plan.slug},
    )
    return subscription


async def _get_subscription(
    session: AsyncSession, tenant_id: uuid.UUID, for_update: bool = False
) -> Subscription | None:
    statement = (
        select(Subscription)
        .where(Subscription.tenant_id == tenant_id)
        .options(
            selectinload(Subscription.plan),
            selectinload(Subscription.pending_plan),
        )
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


def plan_response(subscription: Subscription) -> PlanResponse:
    return PlanResponse(
        tenant_id=subscription.tenant_id,
        subscription_id=subscription.id,
        plan_id=subscription.plan.id,
        plan=subscription.plan.slug,
        status=subscription.status,
        limits=subscription.plan.features,
        pending_plan=(
            subscription.pending_plan.slug if subscription.pending_plan else None
        ),
        pending_change_at=(
            subscription.current_period_end if subscription.pending_plan else None
        ),
    )


async def get_tenant_plan(
    session: AsyncSession, tenant_id: uuid.UUID
) -> PlanResponse | None:
    subscription = await _get_subscription(session, tenant_id, for_update=True)
    if (
        subscription
        and subscription.pending_plan
        and subscription.current_period_end
        and _as_utc(subscription.current_period_end) <= datetime.now(UTC)
    ):
        previous = subscription.plan
        subscription.plan_id = subscription.pending_plan.id
        subscription.plan = subscription.pending_plan
        subscription.pending_plan_id = None
        subscription.pending_plan = None
        subscription.current_period_start = datetime.now(UTC)
        subscription.current_period_end = datetime.now(UTC) + timedelta(days=30)
        add_event(
            session,
            subscription,
            "subscription.downgraded",
            {"from_plan": previous.slug, "to_plan": subscription.plan.slug},
        )
        await session.commit()
    return plan_response(subscription) if subscription else None


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def list_public_plans(session: AsyncSession, product_id: uuid.UUID) -> list[Plan]:
    return list(
        await session.scalars(
            select(Plan)
            .where(Plan.product_id == product_id, Plan.is_active.is_(True))
            .order_by(Plan.position)
        )
    )


async def change_plan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    target_plan_id: uuid.UUID,
    direction: str,
) -> ChangePlanResponse:
    subscription = await _get_subscription(session, tenant_id, for_update=True)
    target = await session.get(Plan, target_plan_id)
    if subscription is None:
        raise NotFound("Subscription not found")
    if target is None or not target.is_active:
        raise NotFound("Plan not found")
    if target.product_id != subscription.plan.product_id:
        raise InvalidPlanChange("Plan belongs to another product")

    is_upgrade = target.position > subscription.plan.position
    if direction == "upgrade" and not is_upgrade:
        raise InvalidPlanChange("Target plan is not an upgrade")
    if direction == "downgrade" and target.position >= subscription.plan.position:
        raise InvalidPlanChange("Target plan is not a downgrade")

    previous = subscription.plan
    event_type = (
        "subscription.upgraded"
        if direction == "upgrade"
        else "subscription.downgrade_scheduled"
    )
    payload = {
        "from_plan_id": str(previous.id),
        "from_plan": previous.slug,
        "to_plan_id": str(target.id),
        "to_plan": target.slug,
    }
    if is_upgrade:
        subscription.plan_id = target.id
        subscription.plan = target
        subscription.pending_plan_id = None
        subscription.pending_plan = None
        changed_immediately = True
    else:
        subscription.pending_plan_id = target.id
        subscription.pending_plan = target
        if subscription.current_period_end is None:
            subscription.current_period_end = datetime.now(UTC) + timedelta(days=30)
        payload["effective_at"] = subscription.current_period_end.isoformat()
        changed_immediately = False

    add_event(session, subscription, event_type, payload)
    await session.commit()
    response = plan_response(subscription)
    return ChangePlanResponse(
        **response.model_dump(),
        changed_immediately=changed_immediately,
        event_type=event_type,
    )


async def list_events(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[SubscriptionEvent]:
    subscription_id = await session.scalar(
        select(Subscription.id).where(Subscription.tenant_id == tenant_id)
    )
    if subscription_id is None:
        raise NotFound("Subscription not found")
    return list(
        await session.scalars(
            select(SubscriptionEvent)
            .where(SubscriptionEvent.subscription_id == subscription_id)
            .order_by(SubscriptionEvent.created_at, SubscriptionEvent.id)
        )
    )
