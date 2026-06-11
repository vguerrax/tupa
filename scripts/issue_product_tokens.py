import asyncio
import re

from sqlalchemy import select

from app.database import AsyncSessionFactory
from app.models.subscription import Product
from app.services.service_token_service import rotate_token


def env_name(slug: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", slug.upper()).strip("_")


async def main() -> None:
    async with AsyncSessionFactory() as session:
        products = list(await session.scalars(select(Product).order_by(Product.slug)))
        for product in products:
            if product.service_token_hash is not None:
                continue
            token = await rotate_token(session, product)
            print(f"{env_name(product.slug)}_PRODUCT_ID={product.id}")
            print(f"{env_name(product.slug)}_AUTH_SERVICE_TOKEN={token}")


if __name__ == "__main__":
    asyncio.run(main())
