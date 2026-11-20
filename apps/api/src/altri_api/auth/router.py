from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from altri_api.auth import service
from altri_api.auth.deps import CurrentUser, Db, SessionToken
from altri_api.auth.schemas import LoginIn, LoginOut, MeOut, TeamOut, UserOut
from altri_api.config import get_settings
from altri_api.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

UNAUTHORIZED = {401: {"description": "Missing, invalid or expired session"}}


async def _me(db: Db, user: User) -> MeOut:
    teams = await service.teams_for_user(db, user)
    return MeOut(
        user=UserOut.model_validate(user),
        teams=[TeamOut.model_validate(t) for t in teams],
        can_write=user.role.can_write,
    )


@router.get("/users", response_model=list[UserOut], summary="List sign-in accounts (seeded user switcher)")
async def list_users(db: Db) -> list[User]:
    """Public on purpose: the spec replaces sign-up with a seeded user switcher."""
    return list(await db.scalars(select(User).order_by(User.id)))


@router.post(
    "/login",
    response_model=LoginOut,
    summary="Sign in as a seeded user",
    responses={401: {"description": "No user with that email"}},
)
async def login(body: LoginIn, response: Response, db: Db, old_token: SessionToken) -> LoginOut:
    """Passwordless sign-in by email (spec: "a seeded user switcher or simple login is enough").

    Issues a new session every time (no fixation) and revokes the caller's previous one, if any.
    """
    user = await service.find_user_by_email(db, body.email)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Unknown email")
    if old_token:
        await service.revoke_session(db, old_token)
    token, expires_at = await service.create_session(db, user)
    me = await _me(db, user)
    await db.commit()

    settings = get_settings()
    response.set_cookie(
        service.SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return LoginOut(**me.model_dump(), access_token=token, expires_at=expires_at)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out (revokes the session)",
    responses=UNAUTHORIZED,
)
async def logout(user: CurrentUser, token: SessionToken, db: Db, response: Response) -> None:
    assert token is not None  # CurrentUser guarantees it
    await service.revoke_session(db, token)
    await db.commit()
    response.delete_cookie(service.SESSION_COOKIE, path="/")


@router.get("/me", response_model=MeOut, summary="Current user and their teams", responses=UNAUTHORIZED)
async def me(user: CurrentUser, db: Db) -> MeOut:
    return await _me(db, user)
