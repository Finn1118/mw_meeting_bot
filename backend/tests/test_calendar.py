from datetime import UTC, datetime, timedelta
from typing import Protocol, cast

import pytest
from google.cloud.firestore_v1 import AsyncClient
from httpx import AsyncClient as HttpAsyncClient
from pytest_httpx import HTTPXMock

from app.config import Settings
from app.deps import get_app_settings
from app.main import app
from app.repositories import calendar_dispatch as dispatch_repo
from app.repositories import meetings as meetings_repo
from app.repositories.google import get_google_connection, upsert_google_connection
from app.routers.google_auth import TOKEN_URL
from app.services.calendar_auto_dispatcher import CalendarAutoDispatcher
from app.services.google_calendar import extract_meeting_link
from app.services.recall import RecallClient

ORG_ID = "org_123"


class FakeRecallClientProtocol(Protocol):
    created_bot_requests: list[tuple[str, str]]


def google_settings() -> Settings:
    return Settings(
        recall_api_key="test-key",
        google_oauth_client_id="client-id",
        google_oauth_client_secret="client-secret",
        disable_gcs_upload=True,
    )


async def create_google_connection(
    db: AsyncClient,
    *,
    auto_dispatch_enabled: bool = False,
    expires_at: datetime | None = None,
) -> None:
    now = datetime.now(UTC)
    await upsert_google_connection(
        db,
        ORG_ID,
        {
            "email": "finn@example.com",
            "auto_dispatch_enabled": auto_dispatch_enabled,
            "access_token": "old-access-token",
            "refresh_token": "refresh-token",
            "scope": "calendar",
            "expires_at": expires_at or now + timedelta(hours=1),
        },
    )


@pytest.mark.asyncio
async def test_calendar_events_requires_connection(client: HttpAsyncClient) -> None:
    response = await client.get(f"/api/calendar/events?org_id={ORG_ID}")

    assert response.status_code == 409
    assert response.json() == {
        "error": "not_connected",
        "message": "Google Calendar is not connected.",
    }


@pytest.mark.asyncio
async def test_calendar_auto_dispatch_defaults_off(client: HttpAsyncClient) -> None:
    response = await client.get(f"/api/calendar/auto-dispatch?org_id={ORG_ID}")

    assert response.status_code == 200
    assert response.json() == {"enabled": False}


@pytest.mark.asyncio
async def test_calendar_auto_dispatch_toggle_requires_connection(client: HttpAsyncClient) -> None:
    response = await client.patch(
        f"/api/calendar/auto-dispatch?org_id={ORG_ID}",
        json={"enabled": True},
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": "not_connected",
        "message": "Google Calendar is not connected.",
    }


@pytest.mark.asyncio
async def test_calendar_auto_dispatch_toggle_updates_connection(
    client: HttpAsyncClient,
    firestore_client: AsyncClient,
) -> None:
    await create_google_connection(firestore_client)

    response = await client.patch(
        f"/api/calendar/auto-dispatch?org_id={ORG_ID}",
        json={"enabled": True},
    )

    assert response.status_code == 200
    assert response.json() == {"enabled": True}
    connection = await get_google_connection(firestore_client, ORG_ID)
    assert connection is not None
    assert connection["auto_dispatch_enabled"] is True


@pytest.mark.asyncio
async def test_calendar_events_lists_and_detects_meeting_links(
    client: HttpAsyncClient,
    firestore_client: AsyncClient,
    httpx_mock: HTTPXMock,
) -> None:
    await create_google_connection(firestore_client)
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

    response = await client.get(f"/api/calendar/events?org_id={ORG_ID}&days=7")

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
    client: HttpAsyncClient,
    firestore_client: AsyncClient,
    httpx_mock: HTTPXMock,
) -> None:
    app.dependency_overrides[get_app_settings] = google_settings
    await create_google_connection(firestore_client, expires_at=datetime.now(UTC) - timedelta(minutes=1))
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        json={"access_token": "new-access-token", "expires_in": 3600},
    )
    httpx_mock.add_response(method="GET", json={"items": []})

    response = await client.get(f"/api/calendar/events?org_id={ORG_ID}")

    assert response.status_code == 200
    connection = await get_google_connection(firestore_client, ORG_ID)
    assert connection is not None
    assert connection["access_token"] == "new-access-token"


@pytest.mark.asyncio
async def test_calendar_auto_dispatcher_creates_meeting_once(
    firestore_client: AsyncClient,
    fake_recall_client: FakeRecallClientProtocol,
    httpx_mock: HTTPXMock,
) -> None:
    await create_google_connection(firestore_client, auto_dispatch_enabled=True)
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
    dispatcher = CalendarAutoDispatcher(
        google_settings(),
        cast(RecallClient, fake_recall_client),
        db=firestore_client,
    )

    await dispatcher._tick()
    await dispatcher._tick()

    assert fake_recall_client.created_bot_requests == [
        ("https://meet.google.com/abc-defg-hij", "Notetaker")
    ]
    meetings = await meetings_repo.list_meetings(firestore_client, ORG_ID)
    dispatch = await dispatch_repo.get_dispatch(firestore_client, ORG_ID, "event_1")
    assert meetings["total"] == 1
    assert meetings["items"][0]["bot_id"] == "bot_test_123"
    assert meetings["items"][0]["status"] == "bot_created"
    assert dispatch is not None
    assert dispatch["status"] == "dispatched"


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
