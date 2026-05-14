from datetime import UTC, datetime

import pytest
from google.cloud.firestore_v1 import AsyncClient
from pytest_httpx import HTTPXMock

from app.config import Settings
from app.repositories import meetings as meetings_repo
from app.services import poller as poller_module
from app.services.poller import BotPoller
from app.services.recall import RecallClient

ORG_ID = "org_123"


def make_settings() -> Settings:
    return Settings(
        recall_api_key="test-key",
        recall_webhook_secret=None,
        public_webhook_base_url=None,
        poll_interval_seconds=5,
        disable_gcs_upload=True,
    )


def make_poller(db: AsyncClient) -> BotPoller:
    return BotPoller(
        settings=make_settings(),
        recall=RecallClient(api_key="test-key", region="us-east-1"),
        db=db,
    )


async def create_meeting(
    db: AsyncClient,
    *,
    meeting_id: str = "meeting_123",
    bot_id: str = "bot_123",
    status: str = "bot_created",
) -> None:
    now = datetime.now(UTC)
    await meetings_repo.create_meeting(
        db,
        {
            "id": meeting_id,
            "meeting_url": "https://meet.google.com/abc-defg-hij",
            "platform": "meet",
            "title": None,
            "org_id": ORG_ID,
            "created_by_uid": None,
            "platform_conversation_id": None,
            "bot_id": bot_id,
            "recording_id": None,
            "transcript_id": None,
            "status": status,
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
        },
    )


@pytest.fixture
def published_events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []

    async def fake_publish(meeting_id: str, event: dict[str, object]) -> None:
        events.append((meeting_id, event))

    monkeypatch.setattr(poller_module.bus, "publish", fake_publish)
    return events


def add_bot_response(
    httpx_mock: HTTPXMock,
    status_code: str,
    *,
    sub_code: str | None = None,
    recordings: list[object] | None = None,
    response_status: int = 200,
) -> None:
    latest_status: dict[str, object] = {"code": status_code}
    if sub_code is not None:
        latest_status["sub_code"] = sub_code

    httpx_mock.add_response(
        method="GET",
        url="https://us-east-1.recall.ai/api/v1/bot/bot_123/",
        status_code=response_status,
        json={
            "id": "bot_123",
            "status_changes": [latest_status],
            "recordings": recordings or [],
        },
    )


async def get_meeting(db: AsyncClient, meeting_id: str = "meeting_123") -> dict[str, object]:
    meeting = await meetings_repo.get_meeting(db, ORG_ID, meeting_id)
    assert meeting is not None
    return meeting


@pytest.mark.asyncio
async def test_polling_status_transitions_publish_in_order(
    firestore_client: AsyncClient,
    httpx_mock: HTTPXMock,
    published_events: list[tuple[str, dict[str, object]]],
) -> None:
    await create_meeting(firestore_client)
    add_bot_response(httpx_mock, "joining_call")
    add_bot_response(httpx_mock, "in_waiting_room")
    add_bot_response(httpx_mock, "in_call_recording")

    bot_poller = make_poller(firestore_client)
    await bot_poller._tick()
    await bot_poller._tick()
    await bot_poller._tick()

    meeting = await get_meeting(firestore_client)
    assert meeting["status"] == "recording"
    assert [event[1]["status"] for event in published_events] == [
        "joining",
        "waiting_room",
        "recording",
    ]


@pytest.mark.asyncio
async def test_done_with_ready_transcript_finalizes_meeting(
    firestore_client: AsyncClient,
    httpx_mock: HTTPXMock,
    published_events: list[tuple[str, dict[str, object]]],
) -> None:
    await create_meeting(firestore_client, status="processing")
    add_bot_response(
        httpx_mock,
        "done",
        recordings=[
            {
                "id": "recording_123",
                "media_shortcuts": {
                    "transcript": {"id": "transcript_123", "status": {"code": "done"}}
                },
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://us-east-1.recall.ai/api/v1/transcript/transcript_123/",
        json={"data": {"download_url": "https://example.test/transcript.json"}},
    )
    raw_transcript = [
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
    httpx_mock.add_response(url="https://example.test/transcript.json", json=raw_transcript)

    await make_poller(firestore_client)._tick()

    meeting = await get_meeting(firestore_client)
    assert meeting["status"] == "complete"
    assert meeting["transcript_id"] == "transcript_123"
    assert meeting["recording_id"] == "recording_123"
    assert meeting["transcript_path"] == (
        "gs://millionways-platform.firebasestorage.app/"
        "organizations/org_123/meetings/meeting_123/transcript.json"
    )
    assert [event[1]["status"] for event in published_events] == ["complete"]
    assert meeting["participants"][0]["name"] == "Alice Smith"
    assert meeting["segments"][0]["text"] == "Hello team"
    assert meeting["segments"][0]["start_ms"] == 500
    assert meeting["segments"][0]["end_ms"] == 1300


@pytest.mark.asyncio
async def test_done_without_ready_transcript_finalizes_on_next_ready_tick(
    firestore_client: AsyncClient,
    httpx_mock: HTTPXMock,
    published_events: list[tuple[str, dict[str, object]]],
) -> None:
    await create_meeting(firestore_client, status="recording")
    add_bot_response(
        httpx_mock,
        "done",
        recordings=[
            {
                "id": "recording_123",
                "media_shortcuts": {
                    "transcript": {"id": "transcript_123", "status": {"code": "processing"}}
                },
            }
        ],
    )
    add_bot_response(
        httpx_mock,
        "done",
        recordings=[
            {
                "id": "recording_123",
                "media_shortcuts": {
                    "transcript": {"id": "transcript_123", "status": {"code": "done"}}
                },
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://us-east-1.recall.ai/api/v1/transcript/transcript_123/",
        json={"data": {"download_url": "https://example.test/transcript-ready.json"}},
    )
    httpx_mock.add_response(url="https://example.test/transcript-ready.json", json=[])

    bot_poller = make_poller(firestore_client)
    await bot_poller._tick()
    meeting_after_first_tick = await get_meeting(firestore_client)
    assert meeting_after_first_tick["status"] == "processing"

    await bot_poller._tick()
    meeting_after_second_tick = await get_meeting(firestore_client)
    assert meeting_after_second_tick["status"] == "complete"
    assert [event[1]["status"] for event in published_events] == ["processing", "complete"]


@pytest.mark.asyncio
async def test_fatal_status_sets_failed_with_sub_code(
    firestore_client: AsyncClient,
    httpx_mock: HTTPXMock,
    published_events: list[tuple[str, dict[str, object]]],
) -> None:
    await create_meeting(firestore_client)
    add_bot_response(httpx_mock, "fatal", sub_code="bot_kicked_from_call")

    await make_poller(firestore_client)._tick()

    meeting = await get_meeting(firestore_client)
    assert meeting["status"] == "failed"
    assert meeting["sub_code"] == "bot_kicked_from_call"
    assert published_events == [
        (
            "meeting_123",
            {
                "meeting_id": "meeting_123",
                "status": "failed",
                "sub_code": "bot_kicked_from_call",
            },
        )
    ]


@pytest.mark.asyncio
async def test_recall_api_error_leaves_meeting_unchanged(
    firestore_client: AsyncClient,
    httpx_mock: HTTPXMock,
    published_events: list[tuple[str, dict[str, object]]],
) -> None:
    await create_meeting(firestore_client, status="joining")
    add_bot_response(httpx_mock, "fatal", response_status=500)

    await make_poller(firestore_client)._tick()

    meeting = await get_meeting(firestore_client)
    assert meeting["status"] == "joining"
    assert published_events == []


@pytest.mark.asyncio
async def test_repeated_tick_without_status_change_does_not_republish(
    firestore_client: AsyncClient,
    httpx_mock: HTTPXMock,
    published_events: list[tuple[str, dict[str, object]]],
) -> None:
    await create_meeting(firestore_client, status="recording")
    add_bot_response(httpx_mock, "in_call_recording")
    add_bot_response(httpx_mock, "in_call_recording")

    bot_poller = make_poller(firestore_client)
    await bot_poller._tick()
    await bot_poller._tick()

    assert published_events == []
