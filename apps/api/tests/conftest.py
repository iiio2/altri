"""Test fixtures.

Database: a dedicated database (TEST_DATABASE_URL, or DATABASE_URL's database name + `_test`).
It is rebuilt from migrations and seed.json once per run, so tests never touch dev data.

Clock: APP_NOW is pinned to the seed's "now". Tests move it with the `set_now` fixture.
"""

import os
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api import config, db

SEED_NOW = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
API_DIR = Path(__file__).resolve().parents[1]


def _test_database_url() -> str:
    if url := os.environ.get("TEST_DATABASE_URL"):
        return url
    parts = urlsplit(config.get_settings().database_url)
    name = parts.path.lstrip("/")
    if name.endswith("_test"):
        return parts.geturl()
    return urlunsplit(parts._replace(path=f"/{name}_test"))


def _ensure_database(url: str) -> None:
    parts = urlsplit(url)
    name = parts.path.lstrip("/")
    admin_url = urlunsplit(parts._replace(path="/postgres"))
    with psycopg.connect(admin_url, autocommit=True, prepare_threshold=None) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            conn.execute(f'CREATE DATABASE "{name}"')  # name comes from config, not user input


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    url = _test_database_url()
    os.environ["DATABASE_URL"] = url
    os.environ["APP_NOW"] = SEED_NOW.isoformat()
    config.get_settings.cache_clear()
    _ensure_database(url)

    # Start from an empty schema every run, then migrate (exercises the real migrations).
    with psycopg.connect(url, autocommit=True, prepare_threshold=None) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    command.upgrade(Config(str(API_DIR / "alembic.ini")), "head")
    db.get_engine.cache_clear()
    db.get_sessionmaker.cache_clear()
    yield


@pytest.fixture(scope="session", autouse=True)
async def _seeded(_database: None) -> AsyncIterator[None]:
    from altri_api.seed import apply_seed, load_seed_file

    async with db.get_sessionmaker()() as session, session.begin():
        await apply_seed(session, load_seed_file(config.get_settings().seed_path))
    yield
    await db.get_engine().dispose()


@pytest.fixture(autouse=True)
async def _clean_sessions(_seeded: None) -> AsyncIterator[None]:
    yield
    async with db.get_sessionmaker()() as session, session.begin():
        await session.execute(text("TRUNCATE auth_sessions"))


@pytest.fixture
def set_now() -> Iterator[Callable[[datetime], None]]:
    settings = config.get_settings()
    original = settings.app_now

    def _set(value: datetime) -> None:
        settings.app_now = value

    yield _set
    settings.app_now = original


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with db.get_sessionmaker()() as s:
        yield s


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from altri_api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def login(client: AsyncClient, email: str) -> dict[str, str]:
    """Sign in and return Bearer headers for that user (lets one client act as several users)."""
    res = await client.post("/api/v1/auth/login", json={"email": email})
    assert res.status_code == 200, res.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {res.json()['access_token']}"}
