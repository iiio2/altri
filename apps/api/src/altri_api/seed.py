"""Load seed.json into the database. Safe to rerun: rows are upserted by their seed ids.

Usage: uv run python -m altri_api.seed [path/to/seed.json]
"""

import asyncio
import json
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api.config import get_settings
from altri_api.db import get_engine, get_sessionmaker
from altri_api.models import Company, Role, Team, TeamMembership, User


class _SeedCompany(BaseModel):
    id: str
    name: str
    timezone: str


class _SeedTeam(BaseModel):
    id: str
    name: str


class _SeedUser(BaseModel):
    id: str
    name: str
    email: str
    role: Role


class _SeedMembership(BaseModel):
    user_id: str
    team_id: str


class SeedFile(BaseModel):
    # Other sections (measurables, issues, ...) are loaded by later features.
    model_config = ConfigDict(extra="ignore")

    company: _SeedCompany
    teams: list[_SeedTeam]
    users: list[_SeedUser]
    memberships: list[_SeedMembership]


def load_seed_file(path: Path) -> SeedFile:
    return SeedFile.model_validate(json.loads(path.read_text()))


async def _upsert(session: AsyncSession, model: type, rows: list[dict], key: list[str]) -> None:
    if not rows:
        return
    stmt = pg_insert(model).values(rows)
    update_cols = {c: stmt.excluded[c] for c in rows[0] if c not in key}
    if update_cols:
        stmt = stmt.on_conflict_do_update(index_elements=key, set_=update_cols)
    else:
        stmt = stmt.on_conflict_do_nothing()
    await session.execute(stmt)


async def apply_seed(session: AsyncSession, seed: SeedFile) -> None:
    company_id = seed.company.id
    await _upsert(session, Company, [seed.company.model_dump()], ["id"])
    await _upsert(session, Team, [{**t.model_dump(), "company_id": company_id} for t in seed.teams], ["id"])
    await _upsert(
        session,
        User,
        [{**u.model_dump(), "email": u.email.strip().lower(), "company_id": company_id} for u in seed.users],
        ["id"],
    )
    await _upsert(session, TeamMembership, [m.model_dump() for m in seed.memberships], ["user_id", "team_id"])


async def main(path: Path) -> None:
    seed = load_seed_file(path)
    async with get_sessionmaker()() as session, session.begin():
        await apply_seed(session, seed)
    await get_engine().dispose()
    print(f"Seeded {len(seed.teams)} teams, {len(seed.users)} users, {len(seed.memberships)} memberships from {path}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]) if len(sys.argv) > 1 else get_settings().seed_path))
