import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    async def subscribe(self, meeting_id: str) -> AsyncIterator[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._queues[meeting_id].add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._queues[meeting_id].discard(q)

    async def publish(self, meeting_id: str, event: dict[str, Any]) -> None:
        for q in list(self._queues.get(meeting_id, ())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass


bus = EventBus()
