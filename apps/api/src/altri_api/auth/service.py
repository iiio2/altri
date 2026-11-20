"""Session tokens: issue, resolve and revoke. Only SHA-256 hashes of tokens are stored."""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api import clock
from altri_api.config import get_settings
from altri_api.models import AuthSession, Team, TeamMembership, User

SESSION_COOKIE = "altri_session"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def find_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email.strip().lower()))


async def create_session(db: AsyncSession, user: User) -> tuple[str, datetime]:
    """Create a session for `user`; returns the raw token (shown once) and its expiry."""
    token = secrets.token_urlsafe(32)
    now = clock.now()
    expires_at = now + timedelta(hours=get_settings().session_ttl_hours)
    db.add(AuthSession(token_hash=hash_token(token), user_id=user.id, created_at=now, expires_at=expires_at))
    await db.flush()
    return token, expires_at


async def resolve_session(db: AsyncSession, token: str) -> User | None:
    """Return the user behind a live (unrevoked, unexpired) token, else None."""
    session = await db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == hash_token(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > clock.now(),
        )
    )
    return session.user if session else None


async def revoke_session(db: AsyncSession, token: str) -> None:
    await db.execute(
        update(AuthSession)
        .where(AuthSession.token_hash == hash_token(token), AuthSession.revoked_at.is_(None))
        .values(revoked_at=clock.now())
    )


async def teams_for_user(db: AsyncSession, user: User) -> list[Team]:
    """Admins see every team in their company; everyone else sees the teams they belong to."""
    stmt = select(Team).where(Team.company_id == user.company_id).order_by(Team.name, Team.id)
    if not user.role.is_admin:
        stmt = stmt.join(TeamMembership, TeamMembership.team_id == Team.id).where(TeamMembership.user_id == user.id)
    return list(await db.scalars(stmt))
