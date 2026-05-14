import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
from google.cloud.firestore_v1 import AsyncClient

from app.config import Settings
from app.firestore_client import get_firestore_client
from app.repositories import calendar_dispatch as dispatch_repo
from app.repositories import google as google_repo
from app.repositories import meetings as meetings_repo
from app.services.google_calendar import (
    GoogleCalendarError,
    ensure_fresh_token,
    extract_meeting_link,
    list_primary_events,
)
from app.services.recall import RecallApiError, RecallClient, RecallPoolExhausted
from app.services.url_parser import parse_meeting_url

logger = logging.getLogger("uvicorn.error")


class CalendarAutoDispatcher:
    def __init__(self, settings: Settings, recall: RecallClient, db: AsyncClient | None = None) -> None:
        self.settings = settings
        self.recall = recall
        self.db = db or get_firestore_client()
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
        connections = await google_repo.list_auto_dispatch_connections(self.db)
        for org_id, connection in connections:
            try:
                access_token, updates = await ensure_fresh_token(connection, self.settings)
                if updates is not None:
                    await google_repo.upsert_google_connection(self.db, org_id, updates)
                now = datetime.now(UTC)
                events = await list_primary_events(
                    access_token,
                    now,
                    now + timedelta(minutes=self.settings.calendar_auto_dispatch_lookahead_minutes),
                )
            except GoogleCalendarError:
                logger.warning("Calendar auto-dispatch skipped because Google Calendar is unavailable")
                continue

            for event in events:
                await self._maybe_dispatch_event(org_id, event)

    async def _maybe_dispatch_event(self, org_id: str, event: dict[str, Any]) -> None:
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            return
        if event.get("status") == "cancelled":
            return
        if await dispatch_repo.is_event_dispatched(self.db, org_id, event_id):
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
        meeting_id = uuid4().hex
        meeting: dict[str, Any] = {
            "id": meeting_id,
            "meeting_url": parsed_url.normalized_url,
            "platform": parsed_url.platform,
            "title": title,
            "org_id": org_id,
            "created_by_uid": None,
            "platform_conversation_id": None,
            "bot_id": None,
            "recording_id": None,
            "transcript_id": None,
            "status": "dispatching",
            "sub_code": None,
            "started_at": None,
            "ended_at": None,
            "duration_sec": None,
            "transcript_path": None,
            "recording_path": None,
            "deleted_at": None,
            "participants": [],
            "created_at": now,
            "updated_at": now,
        }
        await meetings_repo.create_meeting(self.db, meeting)

        dispatch_status = "dispatching"
        try:
            bot_response = await self.recall.create_bot(
                meeting_url=parsed_url.normalized_url,
                bot_name=self.settings.recall_bot_name,
            )
            bot_id = bot_response.get("id")
            if not isinstance(bot_id, str) or not bot_id:
                raise ValueError("missing_bot_id")
            await meetings_repo.update_meeting(
                self.db,
                org_id,
                meeting_id,
                {"bot_id": bot_id, "status": "bot_created"},
            )
            dispatch_status = "dispatched"
        except RecallPoolExhausted as exc:
            logger.warning("Calendar auto-dispatch pool exhausted: status=%s body=%s", exc.status_code, exc.body)
            await meetings_repo.update_meeting(
                self.db,
                org_id,
                meeting_id,
                {"status": "failed", "sub_code": "dispatch_error"},
            )
            dispatch_status = "failed"
        except (RecallApiError, httpx.HTTPError, ValueError) as exc:
            logger.warning("Calendar auto-dispatch failed for event %s: %s", event_id, exc)
            await meetings_repo.update_meeting(
                self.db,
                org_id,
                meeting_id,
                {"status": "failed", "sub_code": "dispatch_error"},
            )
            dispatch_status = "failed"

        await dispatch_repo.record_dispatch(
            self.db,
            org_id,
            event_id,
            meeting_id=meeting_id,
            meeting_url=parsed_url.normalized_url,
            event_title=title,
            event_start=event_start,
            dispatched_at=now,
            status=dispatch_status,
        )


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
