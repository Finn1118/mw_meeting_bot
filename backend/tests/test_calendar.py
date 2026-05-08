from datetime import UTC, datetime, timedelta
from typing import Protocol, cast

import pytest
from httpx import AsyncClient
from pytest_httpx import HTTPXMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.deps import get_app_settings
from app.main import app
from app.models import CalendarDispatch, GoogleConnection, Meeting
from app.routers.google_auth import TOKEN_URL
from app.services.calendar_auto_dispatcher import CalendarAutoDispatcher
from app.services.google_calendar import extract_meeting_link
from app.services.recall import RecallClient


class FakeRecallClientProtocol(Protocol):
    created_bot_requests: list[tuple[str, str]]


def google_settings() -> Settings:
    return Settings(
        recall_api_key="test-key",
        google_oauth_client_id="client-id",
        google_oauth_client_secret="client-secret",
    )


async def create_google_connection(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    auto_dispatch_enabled: bool = False,
    expires_at: datetime | None = None,
) -> None:
    now = datetime.now(UTC)
    async with db_sessionmaker() as session:
        session.add(
            GoogleConnection(
                id="demo",
                email="finn@example.com",
                auto_dispatch_enabled=auto_dispatch_enabled,
                access_token="old-access-token",
                refresh_token="refresh-token",
                scope="calendar",
                expires_at=expires_at or now + timedelta(hours=1),
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_calendar_events_requires_connection(client: AsyncClient) -> None:
    response = await client.get("/api/calendar/events")

    assert response.status_code == 409
    assert response.json() == {
        "error": "not_connected",
        "message": "Google Calendar is not connected.",
    }


@pytest.mark.asyncio
async def test_calendar_auto_dispatch_defaults_off(client: AsyncClient) -> None:
    response = await client.get("/api/calendar/auto-dispatch")

    assert response.status_code == 200
    assert response.json() == {"enabled": False}


@pytest.mark.asyncio
async def test_calendar_auto_dispatch_toggle_requires_connection(client: AsyncClient) -> None:
    response = await client.patch("/api/calendar/auto-dispatch", json={"enabled": True})

    assert response.status_code == 409
    assert response.json() == {
        "error": "not_connected",
        "message": "Google Calendar is not connected.",
    }


@pytest.mark.asyncio
async def test_calendar_auto_dispatch_toggle_updates_connection(
    client: AsyncClient,
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await create_google_connection(db_sessionmaker)

    response = await client.patch("/api/calendar/auto-dispatch", json={"enabled": True})

    assert response.status_code == 200
    assert response.json() == {"enabled": True}
    async with db_sessionmaker() as session:
        connection = await session.get(GoogleConnection, "demo")

    assert connection is not None
    assert connection.auto_dispatch_enabled is True


@pytest.mark.asyncio
async def test_calendar_events_lists_and_detects_meeting_links(
    client: AsyncClient,
    db_sessionmaker: async_sessionmaker[AsyncSession],
    httpx_mock: HTTPXMock,
) -> None:
    await create_google_connection(db_sessionmaker)
    httpx_mock.add_response(
        method="GET",
        json={
            "items": [
                {
                    "id": "event_1",
                    "summary": "Team sync",
                    "start": {"dateTime": "2026-05-05T15:00:00Z"},
                    "end": {"dateTime": "2026-05-05T16:00:00Z"},
                    "organizer": {"email": "organizer@example.com"},
                    "htmlLink": "https://calendar.google.com/event?eid=1",
                    "hangoutLink": "https://meet.google.com/abc-defg-hij",
                }
            ]
        },
    )

    response = await client.get("/api/calendar/events?days=7")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "event_1",
                "title": "Team sync",
                "start": "2026-05-05T15:00:00Z",
                "end": "2026-05-05T16:00:00Z",
                "organizer_email": "organizer@example.com",
                "html_link": "https://calendar.google.com/event?eid=1",
                "meeting_link": {
                    "platform": "meet",
                    "url": "https://meet.google.com/abc-defg-hij",
                },
            }
        ]
    }


@pytest.mark.asyncio
async def test_calendar_events_refreshes_expired_token(
    client: AsyncClient,
    db_sessionmaker: async_sessionmaker[AsyncSession],
    httpx_mock: HTTPXMock,
) -> None:
    app.dependency_overrides[get_app_settings] = google_settings
    await create_google_connection(db_sessionmaker, expires_at=datetime.now(UTC) - timedelta(minutes=1))
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        json={"access_token": "new-access-token", "expires_in": 3600},
    )
    httpx_mock.add_response(method="GET", json={"items": []})

    response = await client.get("/api/calendar/events")

    assert response.status_code == 200
    async with db_sessionmaker() as session:
        connection = await session.get(GoogleConnection, "demo")

    assert connection is not None
    assert connection.access_token == "new-access-token"


@pytest.mark.asyncio
async def test_calendar_auto_dispatcher_creates_meeting_once(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    fake_recall_client: FakeRecallClientProtocol,
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.calendar_auto_dispatcher.AsyncSessionLocal", db_sessionmaker)
    await create_google_connection(db_sessionmaker, auto_dispatch_enabled=True)
    httpx_mock.add_response(
        method="GET",
        json={
            "items": [
                {
                    "id": "event_1",
                    "summary": "Team sync",
                    "start": {"dateTime": "2026-05-05T15:00:00Z"},
                    "end": {"dateTime": "2026-05-05T16:00:00Z"},
                    "hangoutLink": "https://meet.google.com/abc-defg-hij",
                }
            ]
        },
    )
    httpx_mock.add_response(method="GET", json={"items": []})
    dispatcher = CalendarAutoDispatcher(google_settings(), cast(RecallClient, fake_recall_client))

    await dispatcher._tick()
    await dispatcher._tick()

    assert fake_recall_client.created_bot_requests == [
        ("https://meet.google.com/abc-defg-hij", "Notetaker")
    ]
    async with db_sessionmaker() as session:
        meetings = (await session.scalars(select(Meeting))).all()
        dispatches = (await session.scalars(select(CalendarDispatch))).all()

    assert len(meetings) == 1
    assert meetings[0].bot_id == "bot_test_123"
    assert meetings[0].status == "bot_created"
    assert len(dispatches) == 1
    assert dispatches[0].google_event_id == "event_1"
    assert dispatches[0].status == "dispatched"


def test_extract_meeting_link_detects_supported_platforms() -> None:
    assert extract_meeting_link({"description": "Join https://zoom.us/j/123456789"}) == {
        "platform": "zoom",
        "url": "https://zoom.us/j/123456789",
    }
    assert extract_meeting_link({"location": "https://meet.google.com/abc-defg-hij"}) == {
        "platform": "meet",
        "url": "https://meet.google.com/abc-defg-hij",
    }
    assert extract_meeting_link(
        {
            "conferenceData": {
                "entryPoints": [
                    {"uri": "https://teams.microsoft.com/l/meetup-join/abc123?context=xyz"}
                ]
            }
        }
    ) == {
        "platform": "teams",
        "url": "https://teams.microsoft.com/l/meetup-join/abc123?context=xyz",
    }
