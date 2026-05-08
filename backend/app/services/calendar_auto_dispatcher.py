import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import AsyncSessionLocal
from app.models import CalendarDispatch, Meeting
from app.services.google_calendar import (
    GoogleCalendarError,
    ensure_fresh_token,
    extract_meeting_link,
    get_active_connection,
    list_primary_events,
)
from app.services.recall import RecallApiError, RecallClient, RecallPoolExhausted
from app.services.url_parser import parse_meeting_url

logger = logging.getLogger("uvicorn.error")


class CalendarAutoDispatcher:
    def __init__(self, settings: Settings, recall: RecallClient) -> None:
        self.settings = settings
        self.recall = recall
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="calendar-auto-dispatcher")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        logger.info(
            "Calendar auto-dispatcher started (interval=%ss)",
            self.settings.calendar_auto_dispatch_interval_seconds,
        )
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("Calendar auto-dispatcher tick raised; continuing")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.settings.calendar_auto_dispatch_interval_seconds,
                )
            except TimeoutError:
                pass
        logger.info("Calendar auto-dispatcher stopped")

    async def _tick(self) -> None:
        async with AsyncSessionLocal() as session:
            connection = await get_active_connection(session)
            if connection is None or not connection.auto_dispatch_enabled:
                return

            try:
                access_token = await ensure_fresh_token(session, connection, self.settings)
                now = datetime.now(UTC)
                events = await list_primary_events(
                    access_token,
                    now,
                    now + timedelta(minutes=self.settings.calendar_auto_dispatch_lookahead_minutes),
                )
            except GoogleCalendarError:
                logger.warning("Calendar auto-dispatch skipped because Google Calendar is unavailable")
                return

            for event in events:
                await self._maybe_dispatch_event(session, event)

    async def _maybe_dispatch_event(self, session: AsyncSession, event: dict[str, Any]) -> None:
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            return
        if event.get("status") == "cancelled":
            return
        if await session.scalar(select(CalendarDispatch).where(CalendarDispatch.google_event_id == event_id)):
            return

        event_start = event_start_datetime(event)
        if event_start is None:
            return

        meeting_link = extract_meeting_link(event)
        if meeting_link is None:
            return

        try:
            parsed_url = parse_meeting_url(meeting_link["url"])
        except ValueError:
            return

        now = datetime.now(UTC)
        title = str(event.get("summary") or "Calendar meeting")
        meeting = Meeting(
            id=uuid4().hex,
            meeting_url=parsed_url.normalized_url,
            platform=parsed_url.platform,
            title=title,
            status="dispatching",
            created_at=now,
            updated_at=now,
        )
        session.add(meeting)
        await session.flush()

        dispatch = CalendarDispatch(
            google_event_id=event_id,
            meeting_id=meeting.id,
            meeting_url=parsed_url.normalized_url,
            event_title=title,
            event_start=event_start,
            dispatched_at=now,
            status="dispatching",
        )
        session.add(dispatch)

        try:
            bot_response = await self.recall.create_bot(
                meeting_url=parsed_url.normalized_url,
                bot_name=self.settings.recall_bot_name,
            )
            bot_id = bot_response.get("id")
            if not isinstance(bot_id, str) or not bot_id:
                raise ValueError("missing_bot_id")
            meeting.bot_id = bot_id
            meeting.status = "bot_created"
            dispatch.status = "dispatched"
        except RecallPoolExhausted as exc:
            logger.warning("Calendar auto-dispatch pool exhausted: status=%s body=%s", exc.status_code, exc.body)
            meeting.status = "failed"
            meeting.sub_code = "dispatch_error"
            dispatch.status = "failed"
        except (RecallApiError, httpx.HTTPError, ValueError) as exc:
            logger.warning("Calendar auto-dispatch failed for event %s: %s", event_id, exc)
            meeting.status = "failed"
            meeting.sub_code = "dispatch_error"
            dispatch.status = "failed"

        meeting.updated_at = datetime.now(UTC)
        await session.commit()


def event_start_datetime(event: dict[str, Any]) -> datetime | None:
    start = event.get("start")
    if not isinstance(start, dict):
        return None
    date_time = start.get("dateTime")
    if not isinstance(date_time, str):
        return None
    try:
        parsed = datetime.fromisoformat(date_time.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC)
