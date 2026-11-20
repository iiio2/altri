from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from altri_api.auth.router import router as auth_router
from altri_api.db import get_engine
from altri_api.teams.router import router as teams_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await get_engine().dispose()


app = FastAPI(
    title="Altri API",
    version="0.1.0",
    description="Weekly leadership-meeting API. Sign in with `POST /api/v1/auth/login`; "
    "the session travels as an HttpOnly cookie or a Bearer token.",
    lifespan=lifespan,
)

api = APIRouter(prefix="/api/v1")
api.include_router(auth_router)
api.include_router(teams_router)
app.include_router(api)


@app.get("/healthz", tags=["ops"], summary="Liveness probe")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
