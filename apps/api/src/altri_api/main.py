from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from altri_api.auth.router import router as auth_router
from altri_api.config import get_settings
from altri_api.db import get_engine
from altri_api.issues.router import router as issues_router
from altri_api.live.router import router as live_router
from altri_api.meetings.router import router as meetings_router
from altri_api.rocks.router import router as rocks_router
from altri_api.scorecard.router import router as scorecard_router
from altri_api.teams.router import router as teams_router
from altri_api.todos.router import router as todos_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await get_engine().dispose()


DESCRIPTION = """Weekly leadership-meeting API (Measure → Commit → Resolve).

**Auth.** Sign in with `POST /api/v1/auth/login`; the session travels as an HttpOnly cookie or a Bearer token.
Every role and team rule is enforced here: a team the caller can't read is a 403 (even for unknown ids), and
Observers get a 403 on every write.

**Time.** Timestamps are UTC. Weeks are named by their Monday and run Monday-Sunday in the company time zone;
due dates are company-time calendar dates. "Now" comes from `APP_NOW`.

**Live updates.** `WS /api/v1/teams/{team_id}/live` pushes meeting state and "refetch" signals; see `live/router.py`.

**Errors.** `{"detail": ...}`. 401 no session, 403 no access / wrong role, 404 unknown item inside a readable
team, 409 the item's current state forbids the action (or a stale `expected_version`), 422 invalid input.
"""

app = FastAPI(title="Altri API", version="0.2.0", description=DESCRIPTION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

api = APIRouter(prefix="/api/v1")
for router in (
    auth_router,
    teams_router,
    scorecard_router,
    issues_router,
    todos_router,
    rocks_router,
    meetings_router,
    live_router,
):
    api.include_router(router)
app.include_router(api)


@app.get("/healthz", tags=["ops"], summary="Liveness probe")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
