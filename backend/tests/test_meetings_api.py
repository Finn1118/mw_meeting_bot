from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Meeting, Participant, TranscriptSegment
from app.services.recall import RecallApiError
from tests.conftest import FakeRecallClient


@pytest.mark.asyncio
async def test_create_meeting_happy_path(
    client: AsyncClient,
    fake_recall_client: FakeRecallClient,
) -> None:
    response = await client.post(
        "/api/meetings",
        json={"meeting_url": "https://meet.google.com/abc-defg-hij", "title": "Standup"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meeting_url"] == "https://meet.google.com/abc-defg-hij"
    assert body["platform"] == "meet"
    assert body["title"] == "Standup"
    assert body["bot_id"] == "bot_test_123"
    assert body["status"] == "bot_created"
    assert fake_recall_client.created_bot_requests == [
        ("https://meet.google.com/abc-defg-hij", "Test Notetaker")
    ]


@pytest.mark.asyncio
async def test_create_meeting_rejects_invalid_url(client: AsyncClient) -> None:
    response = await client.post("/api/meetings", json={"meeting_url": "https://example.com"})

    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_url",
        "message": "Meeting URL is not supported.",
    }


@pytest.mark.asyncio
async def test_create_meeting_marks_failed_on_recall_error(
    client: AsyncClient,
    fake_recall_client: FakeRecallClient,
) -> None:
    fake_recall_client.create_bot_error = RecallApiError(500, "server error")

    response = await client.post(
        "/api/meetings",
        json={"meeting_url": "https://meet.google.com/abc-defg-hij"},
    )

    assert response.status_code == 502
    assert response.json() == {
        "error": "recall_api_error",
        "message": "Recall API request failed.",
    }

    list_response = await client.get("/api/meetings")
    assert list_response.status_code == 200
    item = list_response.json()["items"][0]
    assert item["status"] == "failed"
    assert item["sub_code"] == "dispatch_error"


@pytest.mark.asyncio
async def test_get_missing_meeting_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/meetings/missing")

    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "message": "Meeting not found."}


@pytest.mark.asyncio
async def test_delete_meeting_soft_deletes(client: AsyncClient) -> None:
    create_response = await client.post(
        "/api/meetings",
        json={"meeting_url": "https://meet.google.com/abc-defg-hij"},
    )
    meeting_id = create_response.json()["id"]

    delete_response = await client.delete(f"/api/meetings/{meeting_id}")
    assert delete_response.status_code == 204

    get_response = await client.get(f"/api/meetings/{meeting_id}")
    assert get_response.status_code == 404

    list_response = await client.get("/api/meetings")
    assert list_response.status_code == 200
    assert list_response.json() == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_update_meeting_title(client: AsyncClient) -> None:
    create_response = await client.post(
        "/api/meetings",
        json={"meeting_url": "https://meet.google.com/abc-defg-hij"},
    )
    meeting_id = create_response.json()["id"]

    response = await client.patch(f"/api/meetings/{meeting_id}", json={"title": "New title"})

    assert response.status_code == 200
    assert response.json()["title"] == "New title"


@pytest.mark.asyncio
async def test_rename_participant_updates_segment_labels(
    client: AsyncClient,
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    async with db_sessionmaker() as session:
        meeting = Meeting(
            id="meeting_123",
            meeting_url="https://meet.google.com/abc-defg-hij",
            platform="meet",
            status="complete",
            created_at=now,
            updated_at=now,
        )
        participant = Participant(meeting_id="meeting_123", recall_id="1", name="Alice")
        session.add_all([meeting, participant])
        await session.flush()
        session.add(
            TranscriptSegment(
                meeting_id="meeting_123",
                participant_id=participant.id,
                speaker_label="Alice",
                text="Hello team",
                start_ms=500,
                end_ms=1300,
            )
        )
        await session.commit()
        participant_id = participant.id

    response = await client.patch(
        f"/api/meetings/meeting_123/participants/{participant_id}",
        json={"display_name": "Alice Cooper"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Alice Cooper"

    async with db_sessionmaker() as session:
        segment = await session.scalar(select(TranscriptSegment))
        assert segment is not None
        assert segment.speaker_label == "Alice Cooper"
