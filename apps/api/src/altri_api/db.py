"""Async SQLAlchemy engine and per-request session."""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from altri_api.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(
        get_settings().sqlalchemy_url,
        pool_pre_ping=True,
        # Neon's pooler runs pgbouncer in transaction mode; server-side prepared
        # statements don't survive connection reassignment there.
        connect_args={"prepare_threshold": None},
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
