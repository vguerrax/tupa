import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.subscription import Plan, Product

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REPORT_VALUES = {"none", "basic", "complete"}


class PlanError(Exception):
    pass


class PlanNotFound(PlanError):
    pass


class PlanAlreadyExists(PlanError):
    pass


class InvalidPlan(PlanError):
    pass


@dataclass
class PlanInput:
    name: str
    slug: str
    position: int
    price_cents: int
    currency: str
    max_recipes: int
    max_slots: int
    max_users: int
    max_ingredients: int
    reports: str
    export: bool
    is_active: bool


def _validate(data: PlanInput) -> PlanInput:
    data.name = data.name.strip()
    data.slug = data.slug.strip().lower()
    data.currency = data.currency.strip().upper()
    if not data.name:
        raise InvalidPlan("Nome e obrigatorio.")
    if not SLUG_PATTERN.fullmatch(data.slug):
        raise InvalidPlan("Use apenas letras minusculas, numeros e hifens no slug.")
    if data.position < 0 or data.price_cents < 0:
        raise InvalidPlan("Posicao e preco nao podem ser negativos.")
    limits = [data.max_recipes, data.max_slots, data.max_users, data.max_ingredients]
    if any(value < -1 for value in limits):
        raise InvalidPlan("Limites devem ser -1 (ilimitado), zero ou positivos.")
    if data.reports not in REPORT_VALUES:
        raise InvalidPlan("Nivel de relatorios invalido.")
    if len(data.currency) != 3:
        raise InvalidPlan("Moeda deve usar tres letras, como BRL.")
    return data


async def list_products_with_plans(session: AsyncSession) -> list[Product]:
    return list(
        await session.scalars(
            select(Product).options(selectinload(Product.plans)).order_by(Product.name)
        )
    )


async def get_product(session: AsyncSession, product_id: uuid.UUID) -> Product | None:
    return await session.scalar(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.plans))
    )


def _apply(plan: Plan, data: PlanInput) -> None:
    plan.name = data.name
    plan.slug = data.slug
    plan.position = data.position
    plan.price_cents = data.price_cents
    plan.currency = data.currency
    plan.is_active = data.is_active
    plan.features = {
        "max_recipes": data.max_recipes,
        "max_slots": data.max_slots,
        "max_users": data.max_users,
        "max_ingredients": data.max_ingredients,
        "reports": False if data.reports == "none" else data.reports,
        "export": data.export,
    }


async def save_plan(
    session: AsyncSession,
    product_id: uuid.UUID,
    data: PlanInput,
    plan_id: uuid.UUID | None = None,
) -> Plan:
    data = _validate(data)
    product = await session.get(Product, product_id)
    if product is None:
        raise PlanNotFound("Produto nao encontrado.")

    if plan_id:
        plan = await session.get(Plan, plan_id)
        if plan is None or plan.product_id != product_id:
            raise PlanNotFound("Plano nao encontrado.")
        if plan.slug == "free" and not data.is_active:
            raise InvalidPlan("O plano free nao pode ser desativado.")
    else:
        plan = Plan(product_id=product_id, interval="month")
        session.add(plan)

    _apply(plan, data)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise PlanAlreadyExists("Ja existe um plano com este slug no produto.") from exc
    await session.refresh(plan)
    return plan
