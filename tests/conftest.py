from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import app
from app.models.subscription import Product
from app.routers.auth import login_limiter
from app.services.service_token_service import build_token, hash_token
from app.services.subscription_service import MOARA_PRODUCT_ID, seed_moara_plans


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        await seed_moara_plans(session)
        moara = await session.get(Product, MOARA_PRODUCT_ID)
        token = build_token(MOARA_PRODUCT_ID, "test-secret")
        moara.service_token_hash = hash_token(token)
        moara.service_token_hint = token[-8:]
        await session.commit()
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def register_product(session_factory):
    async def register(product_id):
        token = build_token(product_id, "test-secret")
        async with session_factory() as session:
            session.add(
                Product(
                    id=product_id,
                    slug=f"test-{product_id.hex}",
                    name="Test Product",
                    service_token_hash=hash_token(token),
                    service_token_hint=token[-8:],
                )
            )
            await session.commit()
        return {"X-Service-Token": token}

    return register


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    login_limiter.clear()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()
