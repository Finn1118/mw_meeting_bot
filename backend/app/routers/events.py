import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sse_starlette import EventSourceResponse

from app.events import bus

router = APIRouter(prefix="/api/events", tags=["events"])


class TestPublishRequest(BaseModel):
    meeting_id: str = Field(min_length=1)
    payload: dict[str, Any]


@router.get("")
async def stream_events(meeting_id: str, request: Request, org_id: str | None = None) -> EventSourceResponse:
    async def event_generator() -> AsyncIterator[dict[str, str]]:
        subscription = cast(Any, bus.subscribe(meeting_id))
        subscription_iter = subscription.__aiter__()
        next_event: asyncio.Task[dict[str, Any]] = asyncio.create_task(
            cast(Any, subscription_iter.__anext__())
        )
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(asyncio.shield(next_event), timeout=15)
                except TimeoutError:
                    yield {"event": "ping", "data": ""}
                    continue

                yield {"event": "update", "data": json.dumps(event)}
                next_event = asyncio.create_task(cast(Any, subscription_iter.__anext__()))
        finally:
            next_event.cancel()
            with suppress(asyncio.CancelledError):
                await next_event
            await subscription.aclose()

    return EventSourceResponse(event_generator())


@router.post("/_test_publish")
async def test_publish(payload: TestPublishRequest) -> dict[str, bool]:
    if os.getenv("ENV") != "dev":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    await bus.publish(payload.meeting_id, payload.payload)
    return {"ok": True}
