import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from svix.webhooks import Webhook

from app.models import Meeting, Participant, TranscriptSegment, WebhookLog
from app.routers import webhooks as webhooks_module
from tests.conftest import FakeRecallClient

pytestmark = pytest.mark.skip(
    reason="Webhook flow disabled; using polling. Re-enable when dashboard access is available."
)

WEBHOOK_SECRET = "whsec_dGVzdA=="


def signed_webhook_headers(payload: dict[str, Any], event_id: str = "msg_test") -> tuple[dict[str, str], str]:
    body = json.dumps(payload, separators=(",", ":"))
    timestamp = datetime.now(UTC)
    signature = Webhook(WEBHOOK_SECRET).sign(event_id, timestamp, body)
    return (
        {
            "content-type": "application/json",
            "webhook-id": event_id,
            "webhook-timestamp": str(int(timestamp.timestamp())),
            "webhook-signature": signature,
        },
        body,
    )


async def create_meeting(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    meeting_id: str = "meeting_123",
    bot_id: str = "bot_123",
    status: str = "bot_created",
) -> None:
    now = datetime.now(UTC)
    async with db_sessionmaker() as session:
        session.add(
            Meeting(
                id=meeting_id,
                meeting_url="https://meet.google.com/abc-defg-hij",
                platform="meet",
                bot_id=bot_id,
                status=status,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_bad_signature_returns_400(client: AsyncClient) -> None:
    response = await client.post(
        "/api/webhooks/recall",
        content='{"event":"bot.in_call_recording","data":{"bot":{"id":"bot_123"}}}',
        headers={
            "content-type": "application/json",
            "webhook-id": "msg_bad",
            "webhook-timestamp": str(int(datetime.now(UTC).timestamp())),
            "webhook-signature": "v1,bad",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_signature",
        "message": "Invalid webhook signature.",
    }


@pytest.mark.asyncio
async def test_unknown_event_type_logs_but_does_not_change_meeting(
    client: AsyncClient,
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await create_meeting(db_sessionmaker, status="recording")
    headers, body = signed_webhook_headers(
        {"event": "unknown.event", "data": {"bot": {"id": "bot_123"}}},
        event_id="msg_unknown",
    )

    response = await client.post("/api/webhooks/recall", content=body, headers=headers)

    assert response.status_code == 200
    async with db_sessionmaker() as session:
        meeting = await session.scalar(select(Meeting).where(Meeting.id == "meeting_123"))
        assert meeting is not None
        assert meeting.status == "recording"
        log_count = await session.scalar(select(func.count()).select_from(WebhookLog))
        assert log_count == 1


@pytest.mark.asyncio
async def test_recording_event_updates_status_and_publishes(
    client: AsyncClient,
    db_sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await create_meeting(db_sessionmaker)
    published: list[tuple[str, dict[str, Any]]] = []

    async def fake_publish(meeting_id: str, event: dict[str, Any]) -> None:
        published.append((meeting_id, event))

    monkeypatch.setattr(webhooks_module.bus, "publish", fake_publish)
    headers, body = signed_webhook_headers(
        {"event": "bot.in_call_recording", "data": {"bot": {"id": "bot_123"}}},
        event_id="msg_recording",
    )

    response = await client.post("/api/webhooks/recall", content=body, headers=headers)

    assert response.status_code == 200
    async with db_sessionmaker() as session:
        meeting = await session.scalar(select(Meeting).where(Meeting.id == "meeting_123"))
        assert meeting is not None
        assert meeting.status == "recording"

    assert published == [
        ("meeting_123", {"meeting_id": "meeting_123", "status": "recording", "event": "bot.in_call_recording"})
    ]


@pytest.mark.asyncio
async def test_duplicate_event_id_is_idempotent(
    client: AsyncClient,
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await create_meeting(db_sessionmaker)
    headers, body = signed_webhook_headers(
        {"event": "bot.in_call_recording", "data": {"bot": {"id": "bot_123"}}},
        event_id="msg_duplicate",
    )

    first_response = await client.post("/api/webhooks/recall", content=body, headers=headers)
    second_response = await client.post("/api/webhooks/recall", content=body, headers=headers)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    async with db_sessionmaker() as session:
        log_count = await session.scalar(select(func.count()).select_from(WebhookLog))
        assert log_count == 1
        meeting = await session.scalar(select(Meeting).where(Meeting.id == "meeting_123"))
        assert meeting is not None
        assert meeting.status == "recording"


@pytest.mark.asyncio
async def test_transcript_done_fetches_downloads_and_persists_segments(
    client: AsyncClient,
    db_sessionmaker: async_sessionmaker[AsyncSession],
    fake_recall_client: FakeRecallClient,
    tmp_path: Path,
) -> None:
    await create_meeting(db_sessionmaker, status="processing")
    fake_recall_client.transcript_json = [
        {
            "participant": {"id": 12345, "name": "Alice Smith", "is_host": True},
            "words": [
                {
                    "text": "Hello",
                    "start_timestamp": {"relative": 0.5},
                    "end_timestamp": {"relative": 0.9},
                },
                {
                    "text": "team",
                    "start_timestamp": {"relative": 0.95},
                    "end_timestamp": {"relative": 1.3},
                },
            ],
        }
    ]
    headers, body = signed_webhook_headers(
        {
            "event": "transcript.done",
            "data": {"bot": {"id": "bot_123"}, "transcript": {"id": "transcript_123"}},
        },
        event_id="msg_transcript",
    )

    response = await client.post("/api/webhooks/recall", content=body, headers=headers)

    assert response.status_code == 200
    assert fake_recall_client.transcript_requests == ["transcript_123"]
    assert fake_recall_client.download_requests == ["https://example.test/transcript.json"]

    async with db_sessionmaker() as session:
        meeting = await session.scalar(select(Meeting).where(Meeting.id == "meeting_123"))
        assert meeting is not None
        assert meeting.status == "complete"
        assert meeting.transcript_id == "transcript_123"
        assert meeting.transcript_path == str(tmp_path / "blobs" / "transcript_meeting_123.json")

        participant = await session.scalar(select(Participant))
        assert participant is not None
        assert participant.recall_id == "12345"
        assert participant.name == "Alice Smith"
        assert participant.is_host is True

        segment = await session.scalar(select(TranscriptSegment))
        assert segment is not None
        assert segment.participant_id == participant.id
        assert segment.speaker_label == "Alice Smith"
        assert segment.text == "Hello team"
        assert segment.start_ms == 500
        assert segment.end_ms == 1300

    saved_transcript = tmp_path / "blobs" / "transcript_meeting_123.json"
    assert json.loads(saved_transcript.read_text(encoding="utf-8")) == fake_recall_client.transcript_json
