"""Authorization dependencies. Every role and team-boundary rule is enforced here, on the server.

Endpoints declare what they need through the Annotated aliases at the bottom:
    CurrentUser   - any signed-in user (401 otherwise)
    WriterUser    - Admin or Team Member (403 for Observers)
    ReadableTeam  - team in the path the user may read (403 otherwise)
    WritableTeam  - ReadableTeam + WriterUser
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api.auth.service import SESSION_COOKIE, resolve_session
from altri_api.db import get_db
from altri_api.models import Team, TeamMembership, User

# Declared as security schemes so they show up in the OpenAPI docs.
_cookie_scheme = APIKeyCookie(name=SESSION_COOKIE, auto_error=False, description="Set by POST /auth/login")
_bearer_scheme = HTTPBearer(auto_error=False, description="`access_token` from POST /auth/login")

Db = Annotated[AsyncSession, Depends(get_db)]

TEAM_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def session_token(
    cookie: Annotated[str | None, Depends(_cookie_scheme)],
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str | None:
    """Bearer header wins over the cookie when both are present."""
    if bearer is not None:
        return bearer.credentials
    return cookie


SessionToken = Annotated[str | None, Depends(session_token)]


async def current_user(db: Db, token: SessionToken) -> User:
    if not token:
        raise _unauthorized()
    user = await resolve_session(db, token)
    if user is None:
        raise _unauthorized("Session is invalid or expired")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_writer(user: CurrentUser) -> User:
    if not user.role.can_write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Observers have read-only access")
    return user


WriterUser = Annotated[User, Depends(require_writer)]


async def find_readable_team(db: AsyncSession, user: User, team_id: str) -> Team | None:
    """The team if `user` may read it (Admins: any team in their company; others: their teams), else None.

    One query, so the access check and the fetch can't disagree. Reusable outside HTTP routes (e.g. websockets).
    """
    stmt = select(Team).where(Team.id == team_id, Team.company_id == user.company_id)
    if not user.role.is_admin:
        stmt = stmt.where(exists().where(TeamMembership.team_id == Team.id, TeamMembership.user_id == user.id))
    return await db.scalar(stmt)


async def readable_team(
    db: Db,
    user: CurrentUser,
    team_id: Annotated[str, Path(pattern=TEAM_ID_PATTERN, description="Team id, e.g. `team_lead`")],
) -> Team:
    team = await find_readable_team(db, user, team_id)
    if team is None:
        # Same 403 whether the team is someone else's or doesn't exist, so ids can't be probed.
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not have access to this team")
    return team


ReadableTeam = Annotated[Team, Depends(readable_team)]


@dataclass(frozen=True, slots=True)
class TeamWriteContext:
    team: Team
    user: User


def writable_team(team: ReadableTeam, user: WriterUser) -> TeamWriteContext:
    return TeamWriteContext(team=team, user=user)


WritableTeam = Annotated[TeamWriteContext, Depends(writable_team)]
