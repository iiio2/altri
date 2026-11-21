"""Role and team-boundary rules (spec 2.4), enforced by the server."""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from altri_api.auth.deps import WritableTeam
from altri_api.auth.router import router as auth_router
from tests.conftest import login

ADMIN, MEMBER, OBSERVER = "avery@acme.test", "blake@acme.test", "ellis@acme.test"  # u1, u2 (lead+sales), u5 (lead)


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        (ADMIN, ["team_lead", "team_ops", "team_sales"]),  # every team, though only a member of Leadership
        (MEMBER, ["team_lead", "team_sales"]),
        ("dana@acme.test", ["team_lead", "team_ops"]),
        (OBSERVER, ["team_lead"]),
    ],
)
async def test_team_list_is_scoped_to_the_user(client: AsyncClient, email: str, expected: list[str]) -> None:
    headers = await login(client, email)

    teams = (await client.get("/api/v1/teams", headers=headers)).json()
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()

    assert sorted(t["id"] for t in teams) == expected
    assert sorted(t["id"] for t in me["teams"]) == expected


async def test_team_member_reading_another_team_is_refused(client: AsyncClient) -> None:
    headers = await login(client, MEMBER)

    assert (await client.get("/api/v1/teams/team_sales", headers=headers)).status_code == 200
    res = await client.get("/api/v1/teams/team_ops", headers=headers)
    assert res.status_code == 403


async def test_unknown_team_is_indistinguishable_from_a_forbidden_one(client: AsyncClient) -> None:
    headers = await login(client, MEMBER)

    forbidden = await client.get("/api/v1/teams/team_ops", headers=headers)
    missing = await client.get("/api/v1/teams/team_nope", headers=headers)

    assert (missing.status_code, missing.json()) == (forbidden.status_code, forbidden.json())


async def test_malformed_team_id_is_rejected(client: AsyncClient) -> None:
    headers = await login(client, ADMIN)
    assert (await client.get("/api/v1/teams/team%20lead;drop", headers=headers)).status_code == 422


async def test_admin_reads_any_team(client: AsyncClient) -> None:
    headers = await login(client, ADMIN)

    res = await client.get("/api/v1/teams/team_ops", headers=headers)

    assert res.status_code == 200
    assert sorted(m["id"] for m in res.json()["members"]) == ["u4", "u8", "u9"]


async def test_observer_reads_own_team(client: AsyncClient) -> None:
    headers = await login(client, OBSERVER)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()

    assert me["can_write"] is False
    assert (await client.get("/api/v1/teams/team_lead", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/teams/team_sales", headers=headers)).status_code == 403


async def test_requests_without_a_session_are_refused(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/teams")).status_code == 401
    assert (await client.get("/api/v1/teams/team_lead")).status_code == 401


# --- Write guard -----------------------------------------------------------------------------
# The shared `WritableTeam` dependency, exercised in isolation on a probe route. Every write endpoint uses it;
# the feature test modules check Observer and cross-team writes against the real endpoints too.

_probe = FastAPI()


@_probe.post("/api/v1/teams/{team_id}/probe")
async def _write_probe(ctx: WritableTeam) -> dict[str, str]:
    return {"team": ctx.team.id, "user": ctx.user.id}


_probe.include_router(auth_router, prefix="/api/v1")  # for signing in


@pytest.fixture
async def probe_client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=_probe), base_url="http://test") as c:
        yield c


@pytest.mark.parametrize(
    ("email", "team", "status"),
    [
        (OBSERVER, "team_lead", 403),  # Observer write in own team
        (MEMBER, "team_lead", 200),
        (MEMBER, "team_ops", 403),  # Team Member write in another team
        (ADMIN, "team_ops", 200),  # Admin write in a team they don't belong to
    ],
)
async def test_write_guard(probe_client: AsyncClient, email: str, team: str, status: int) -> None:
    headers = await login(probe_client, email)

    res = await probe_client.post(f"/api/v1/teams/{team}/probe", headers=headers)

    assert res.status_code == status, res.text
