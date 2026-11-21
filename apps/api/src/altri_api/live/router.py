"""WebSocket: /api/v1/teams/{team_id}/live

Server -> client messages (JSON):
  {"type": "hello",   "user_id", "server_now", "meeting": MeetingState | null}   on connect, so every (re)connect
                                                                                   starts from the current state
  {"type": "meeting", "meeting": MeetingState}                                   meeting started/changed/ended
  {"type": "changed", "resources": ["issues", "scorecard", ...]}                 refetch these over REST
  {"type": "pong",    "server_now"}                                              reply to {"type": "ping"}

Mutations always go through REST; the socket only pushes. Authentication is the session cookie (browsers) or an
`Authorization: Bearer` header (other clients). The session and team access are re-checked periodically.
"""

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from altri_api import clock
from altri_api.auth.deps import find_readable_team
from altri_api.auth.service import SESSION_COOKIE, resolve_session
from altri_api.config import get_settings
from altri_api.db import get_sessionmaker
from altri_api.live.hub import hub
from altri_api.meetings import service as meetings
from altri_api.models import User

router = APIRouter(tags=["live"])
log = logging.getLogger(__name__)

RECHECK_SECONDS = 60.0


def _token(ws: WebSocket) -> str | None:
    auth = ws.headers.get("authorization", "")
    scheme, _, credentials = auth.partition(" ")
    if scheme.lower() == "bearer" and credentials:
        return credentials
    return ws.cookies.get(SESSION_COOKIE)


async def _authorize(token: str | None, team_id: str) -> User | None:
    if not token:
        return None
    async with get_sessionmaker()() as db:
        user = await resolve_session(db, token)
        if user is None or await find_readable_team(db, user, team_id) is None:
            return None
        return user


async def _hello(user: User, team_id: str) -> dict[str, object]:
    async with get_sessionmaker()() as db:
        meeting = await meetings.active_meeting(db, team_id)
        now = clock.now()
        state = await meetings.build_state(db, meeting, now) if meeting else None
    return {
        "type": "hello",
        "user_id": user.id,
        "server_now": now.isoformat().replace("+00:00", "Z"),
        "meeting": state.model_dump(mode="json") if state else None,
    }


@router.websocket("/teams/{team_id}/live")
async def live(ws: WebSocket, team_id: str) -> None:
    # Browsers always send Origin. Refusing unknown origins stops other sites from riding the session cookie
    # (cross-site WebSocket hijacking); non-browser clients without Origin authenticate with a Bearer token.
    origin = ws.headers.get("origin")
    if origin is not None and origin not in get_settings().cors_origins:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="origin not allowed")
        return
    token = _token(ws)
    user = await _authorize(token, team_id)
    if user is None:
        # Same refusal for a bad session, an unknown team and someone else's team.
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="no access to this team")
        return

    await ws.accept()
    async with hub.subscribe(team_id) as sub:
        await ws.send_json(await _hello(user, team_id))
        receiver = asyncio.create_task(_receive(ws))
        try:
            while not receiver.done():
                getter = asyncio.create_task(sub.queue.get())
                overflow = asyncio.create_task(sub.overflowed.wait())
                done, _ = await asyncio.wait(
                    {getter, receiver, overflow}, timeout=RECHECK_SECONDS, return_when=asyncio.FIRST_COMPLETED
                )
                for task in (getter, overflow):
                    if task not in done:
                        task.cancel()
                if overflow in done:
                    await ws.close(code=status.WS_1013_TRY_AGAIN_LATER, reason="fell behind; reconnect")
                    break
                if getter in done:
                    await ws.send_json(getter.result())
                elif not done and await _authorize(token, team_id) is None:
                    await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="session ended or access revoked")
                    break
        except WebSocketDisconnect:
            pass
        finally:
            receiver.cancel()
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
                await receiver


async def _receive(ws: WebSocket) -> None:
    """Answer pings (clients use them to measure clock offset) until the client goes away."""
    try:
        while True:
            message = await ws.receive_json()
            if isinstance(message, dict) and message.get("type") == "ping":
                await ws.send_json({"type": "pong", "server_now": clock.now().isoformat().replace("+00:00", "Z")})
    except WebSocketDisconnect, ValueError, RuntimeError:
        return
