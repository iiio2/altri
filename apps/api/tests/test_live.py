"""Real-time sync over the live WebSocket: everyone sees the same meeting state within the request that changed it."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from httpx import AsyncClient
from httpx_ws import WebSocketDisconnect, WebSocketUpgradeError, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from altri_api.main import app
from tests.conftest import MEMBER, OBSERVER, OPS_MEMBER, login

LEAD = "/api/v1/teams/team_lead"
LIVE = f"{LEAD}/live"


@asynccontextmanager
async def ws_client() -> AsyncIterator[AsyncClient]:
    """Opened inside each test (not a fixture): the transport's task group must start and stop in one task."""
    async with AsyncClient(transport=ASGIWebSocketTransport(app), base_url="http://test") as c:
        yield c


async def next_of_type(ws, kind: str) -> dict:
    while True:
        message = await asyncio.wait_for(ws.receive_json(), timeout=2)
        if message["type"] == kind:
            return message


async def test_second_browser_follows_the_facilitator(fresh_data: None) -> None:
    async with ws_client() as client:
        facilitator, viewer = await login(client, MEMBER), await login(client, OBSERVER)

        async with aconnect_ws(LIVE, client, headers=viewer) as ws:
            hello = await ws.receive_json()
            assert (hello["type"], hello["user_id"], hello["meeting"]) == ("hello", "u5", None)

            meeting = (await client.post(f"{LEAD}/meetings", headers=facilitator)).json()
            started = await next_of_type(ws, "meeting")
            assert (started["meeting"]["id"], started["meeting"]["section"]) == (meeting["id"], "scorecard")

            await client.put(f"{LEAD}/meetings/{meeting['id']}/section", json={"section": "ids"}, headers=facilitator)
            advanced = await next_of_type(ws, "meeting")
            assert advanced["meeting"]["section"] == "ids"

            await client.post(f"{LEAD}/meetings/{meeting['id']}/end", headers=facilitator)
            ended = await next_of_type(ws, "meeting")
            assert ended["meeting"]["status"] == "ended"


async def test_late_join_gets_the_current_state(fresh_data: None) -> None:
    async with ws_client() as client:
        facilitator = await login(client, MEMBER)
        meeting = (await client.post(f"{LEAD}/meetings", headers=facilitator)).json()
        await client.put(f"{LEAD}/meetings/{meeting['id']}/section", json={"section": "conclude"}, headers=facilitator)

        # The facilitator reconnecting (refresh) and an Observer joining late both start from the current state.
        for headers in (facilitator, await login(client, OBSERVER)):
            async with aconnect_ws(LIVE, client, headers=headers) as ws:
                hello = await ws.receive_json()
                assert (hello["meeting"]["id"], hello["meeting"]["section"]) == (meeting["id"], "conclude")


async def test_data_changes_tell_clients_what_to_refetch(fresh_data: None) -> None:
    async with ws_client() as client:
        member = await login(client, MEMBER)

        async with aconnect_ws(LIVE, client, headers=await login(client, OBSERVER)) as ws:
            await ws.receive_json()  # hello
            await client.put(f"{LEAD}/measurables/m1/scores/2026-11-09", json={"value": 4}, headers=member)
            assert (await next_of_type(ws, "changed"))["resources"] == ["scorecard"]
            await client.post(f"{LEAD}/issues", json={"title": "New"}, headers=member)
            assert (await next_of_type(ws, "changed"))["resources"] == ["issues"]
            await ws.send_json({"type": "ping"})
            assert (await next_of_type(ws, "pong"))["server_now"] == "2026-11-11T15:00:00Z"


async def test_events_stay_within_the_team(fresh_data: None) -> None:
    async with ws_client() as client:
        ops, lead = await login(client, OPS_MEMBER), await login(client, MEMBER)
        async with aconnect_ws("/api/v1/teams/team_ops/live", client, headers=ops) as ws:
            await ws.receive_json()  # hello
            await client.post(f"{LEAD}/issues", json={"title": "Leadership only"}, headers=lead)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(ws.receive_json(), timeout=0.3)


@pytest.mark.parametrize(
    ("email", "team", "extra_headers"),
    [
        (None, "team_lead", {}),  # no session
        (OPS_MEMBER, "team_lead", {}),  # another team
        (MEMBER, "team_nope", {}),  # unknown team
        (MEMBER, "team_lead", {"origin": "https://evil.example"}),  # cross-site WebSocket hijacking
    ],
)
async def test_live_socket_refuses(email: str | None, team: str, extra_headers: dict) -> None:
    async with ws_client() as client:
        headers = {**(await login(client, email) if email else {}), **extra_headers}
        # Refused before the handshake completes: uvicorn answers HTTP 403; the in-process transport reports 1008.
        assert await refusal(client, f"/api/v1/teams/{team}/live", headers) in (403, 1008)


async def refusal(client: AsyncClient, url: str, headers: dict) -> int:
    try:
        async with aconnect_ws(url, client, headers=headers):
            return 0
    except BaseException as exc:  # the transport may wrap it in an exception group
        while isinstance(exc, BaseExceptionGroup):
            exc = exc.exceptions[0]
        if isinstance(exc, WebSocketUpgradeError):
            return exc.response.status_code
        if isinstance(exc, WebSocketDisconnect):
            return exc.code
        raise


async def test_allowed_origin_with_cookie_session() -> None:
    async with ws_client() as client:
        res = await client.post("/api/v1/auth/login", json={"email": MEMBER})  # sets the cookie on the client
        assert res.status_code == 200
        async with aconnect_ws(LIVE, client, headers={"origin": "http://localhost:3000"}) as ws:
            assert (await ws.receive_json())["user_id"] == "u2"
