import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Plan, Product
from app.services import service_token_service

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ProductAlreadyExists(Exception):
    pass


class InvalidSlug(Exception):
    pass


async def list_products(session: AsyncSession) -> list[tuple[Product, int]]:
    rows = await session.execute(
        select(Product, func.count(Plan.id))
        .outerjoin(Plan)
        .group_by(Product.id)
        .order_by(Product.name)
    )
    return list(rows.tuples())


async def create_product(session: AsyncSession, name: str, slug: str) -> tuple[Product, str]:
    normalized_name = name.strip()
    normalized_slug = slug.strip().lower()
    if not normalized_name:
        raise ValueError("Nome e obrigatorio")
    if not SLUG_PATTERN.fullmatch(normalized_slug):
        raise InvalidSlug

    product = Product(name=normalized_name, slug=normalized_slug)
    try:
        session.add(product)
        await session.flush()
        token = service_token_service.build_token(product.id)
        product.service_token_hash = service_token_service.hash_token(token)
        product.service_token_hint = token[-8:]
        session.add(
            Plan(
                product_id=product.id,
                slug="free",
                name="Free",
                position=0,
                interval="month",
                price_cents=0,
                currency="BRL",
                is_active=True,
                features={
                    "max_recipes": -1,
                    "max_slots": -1,
                    "max_users": -1,
                    "max_ingredients": -1,
                    "reports": False,
                    "export": False,
                },
            )
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ProductAlreadyExists from exc
    await session.refresh(product)
    return product, token


async def rotate_service_token(session: AsyncSession, product_id: uuid.UUID) -> str:
    product = await session.get(Product, product_id)
    if product is None:
        raise ValueError("Produto nao encontrado")
    return await service_token_service.rotate_token(session, product)
