from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.deps import get_app_settings, get_session
from app.errors import ApiError
from app.schemas import (
    AutoDispatchSetting,
    AutoDispatchUpdate,
    CalendarEventList,
    CalendarEventRead,
    CalendarMeetingLink,
)
from app.services.google_calendar import (
    GoogleCalendarError,
    ensure_fresh_token,
    extract_meeting_link,
    get_active_connection,
    list_primary_events,
)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/auto-dispatch", response_model=AutoDispatchSetting)
async def get_auto_dispatch_setting(
    session: AsyncSession = Depends(get_session),
) -> AutoDispatchSetting:
    connection = await get_active_connection(session)
    return AutoDispatchSetting(enabled=connection.auto_dispatch_enabled if connection else False)


@router.patch("/auto-dispatch", response_model=AutoDispatchSetting)
async def update_auto_dispatch_setting(
    payload: AutoDispatchUpdate,
    session: AsyncSession = Depends(get_session),
) -> AutoDispatchSetting:
    connection = await get_active_connection(session)
    if connection is None:
        raise ApiError(status.HTTP_409_CONFLICT, "not_connected", "Google Calendar is not connected.")

    connection.auto_dispatch_enabled = payload.enabled
    await session.commit()
    return AutoDispatchSetting(enabled=connection.auto_dispatch_enabled)


@router.get("/events", response_model=CalendarEventList)
async def list_calendar_events(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    days: Annotated[int, Query(ge=1, le=30)] = 7,
) -> CalendarEventList:
    connection = await get_active_connection(session)
    if connection is None:
        raise ApiError(status.HTTP_409_CONFLICT, "not_connected", "Google Calendar is not connected.")

    try:
        access_token = await ensure_fresh_token(session, connection, settings)
        now = datetime.now(UTC)
        events = await list_primary_events(access_token, now, now + timedelta(days=days))
    except GoogleCalendarError as exc:
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "google_unavailable",
            "Google Calendar is unavailable.",
        ) from exc

    return CalendarEventList(items=[calendar_event_read(event) for event in events])


def calendar_event_read(event: dict[str, Any]) -> CalendarEventRead:
    organizer = event.get("organizer")
    meeting_link = extract_meeting_link(event)
    return CalendarEventRead(
        id=str(event.get("id", "")),
        title=str(event.get("summary") or "Untitled event"),
        start=event_time_value(event.get("start")),
        end=event_time_value(event.get("end")),
        organizer_email=organizer.get("email") if isinstance(organizer, dict) else None,
        html_link=event.get("htmlLink") if isinstance(event.get("htmlLink"), str) else None,
        meeting_link=CalendarMeetingLink(**meeting_link) if meeting_link else None,
    )


def event_time_value(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    date_time = value.get("dateTime")
    if isinstance(date_time, str):
        return date_time
    date = value.get("date")
    return date if isinstance(date, str) else None
