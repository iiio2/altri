"""In-process pub/sub that fans team events out to WebSocket subscribers.

The database owns all state; the hub only carries "something changed" signals and meeting snapshots. A client
that misses messages (disconnect, slow consumer) loses nothing: on (re)connect it receives a fresh snapshot and
refetches over REST. That is what makes late joins, refreshes and reconnects safe.

Scope: one process. Running several API workers would need a shared bus (Postgres LISTEN/NOTIFY or Redis)
behind this same `publish`/`subscribe` interface.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Any

log = logging.getLogger(__name__)

QUEUE_SIZE = 256


class Resource(StrEnum):
    """What a client should refetch when it receives a `changed` event."""

    SCORECARD = "scorecard"
    ISSUES = "issues"
    TODOS = "todos"
    ROCKS = "rocks"
    MEETING = "meeting"


class Subscription:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(QUEUE_SIZE)
        # Set when the subscriber fell too far behind; the socket closes and the client reconnects.
        self.overflowed = asyncio.Event()


class Hub:
    def __init__(self) -> None:
        self._subs: defaultdict[str, set[Subscription]] = defaultdict(set)

    @asynccontextmanager
    async def subscribe(self, team_id: str) -> AsyncIterator[Subscription]:
        sub = Subscription()
        self._subs[team_id].add(sub)
        try:
            yield sub
        finally:
            self._subs[team_id].discard(sub)
            if not self._subs[team_id]:
                del self._subs[team_id]

    def publish(self, team_id: str, message: dict[str, Any]) -> None:
        """Deliver to every subscriber of `team_id`. Never blocks the request that published."""
        for sub in list(self._subs.get(team_id, ())):
            try:
                sub.queue.put_nowait(message)
            except asyncio.QueueFull:
                log.warning("dropping slow live subscriber on team %s", team_id)
                sub.overflowed.set()

    def subscriber_count(self, team_id: str) -> int:
        return len(self._subs.get(team_id, ()))


hub = Hub()


def notify_changed(team_id: str, *resources: Resource) -> None:
    """Tell a team's live clients to refetch `resources`. Call only after the change is committed."""
    hub.publish(team_id, {"type": "changed", "resources": sorted(resources)})
