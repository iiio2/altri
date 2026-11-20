"""The database itself rejects invalid data, independent of the API layer."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api import config
from altri_api.models import TeamMembership, User
from altri_api.seed import apply_seed, load_seed_file
from tests.conftest import SEED_NOW

USER_INSERT = "INSERT INTO users (id, company_id, name, email, role) VALUES (:id, 'co_1', :name, :email, :role)"


@pytest.mark.parametrize(
    "row",
    [
        {"id": "x1", "name": "X", "email": "x1@acme.test", "role": "superuser"},  # unknown role
        {"id": "x2", "name": "X", "email": "X2@Acme.test", "role": "observer"},  # not normalized
        {"id": "x3", "name": "X", "email": "no-at-sign", "role": "observer"},
        {"id": "x4", "name": "X", "email": "blake@acme.test", "role": "observer"},  # duplicate email
        {"id": "x5", "name": "  ", "email": "x5@acme.test", "role": "observer"},  # blank name
    ],
)
async def test_invalid_users_are_rejected(session: AsyncSession, row: dict[str, str]) -> None:
    with pytest.raises(IntegrityError):
        await session.execute(text(USER_INSERT), row)
    await session.rollback()


async def test_membership_requires_existing_team(session: AsyncSession) -> None:
    session.add(TeamMembership(user_id="u2", team_id="team_missing"))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_session_cannot_expire_before_it_starts(session: AsyncSession) -> None:
    stmt = text("INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at) VALUES (:h, 'u1', :c, :e)")
    with pytest.raises(IntegrityError):
        await session.execute(stmt, {"h": "a" * 64, "c": SEED_NOW, "e": SEED_NOW - timedelta(seconds=1)})
    await session.rollback()


async def test_seed_is_safe_to_rerun(session: AsyncSession) -> None:
    async def counts() -> tuple[int, int]:
        users = await session.scalar(select(func.count()).select_from(User))
        members = await session.scalar(select(func.count()).select_from(TeamMembership))
        return users, members

    before = await counts()
    await apply_seed(session, load_seed_file(config.get_settings().seed_path))
    await session.commit()

    assert await counts() == before == (9, 11)
