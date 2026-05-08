from datetime import UTC, datetime
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.models import Meeting, Participant, TranscriptSegment
from app.services import poller as poller_module
from app.services.poller import BotPoller
from app.services.recall import RecallClient


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        recall_api_key="test-key",
        recall_webhook_secret=None,
        public_webhook_base_url=None,
        blobs_dir=str(tmp_path / "blobs"),
        poll_interval_seconds=5,
    )


def make_poller(tmp_path: Path) -> BotPoller:
    return BotPoller(
        settings=make_settings(tmp_path),
        recall=RecallClient(api_key="test-key", region="us-east-1"),
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


@pytest.fixture(autouse=True)
def override_poller_sessionmaker(
    monkeypatch: pytest.MonkeyPatch,
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    monkeypatch.setattr(poller_module, "AsyncSessionLocal", db_sessionmaker)


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


async def get_meeting(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    meeting_id: str = "meeting_123",
) -> Meeting:
    async with db_sessionmaker() as session:
        meeting = await session.scalar(select(Meeting).where(Meeting.id == meeting_id))
        assert meeting is not None
        return meeting


@pytest.mark.asyncio
async def test_polling_status_transitions_publish_in_order(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    httpx_mock: HTTPXMock,
    published_events: list[tuple[str, dict[str, object]]],
    tmp_path: Path,
) -> None:
    await create_meeting(db_sessionmaker)
    add_bot_response(httpx_mock, "joining_call")
    add_bot_response(httpx_mock, "in_waiting_room")
    add_bot_response(httpx_mock, "in_call_recording")

    bot_poller = make_poller(tmp_path)
    await bot_poller._tick()
    await bot_poller._tick()
    await bot_poller._tick()

    meeting = await get_meeting(db_sessionmaker)
    assert meeting.status == "recording"
    assert [event[1]["status"] for event in published_events] == [
        "joining",
        "waiting_room",
        "recording",
    ]


@pytest.mark.asyncio
async def test_done_with_ready_transcript_finalizes_meeting(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    httpx_mock: HTTPXMock,
    published_events: list[tuple[str, dict[str, object]]],
    tmp_path: Path,
) -> None:
    await create_meeting(db_sessionmaker, status="processing")
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

    await make_poller(tmp_path)._tick()

    meeting = await get_meeting(db_sessionmaker)
    assert meeting.status == "complete"
    assert meeting.transcript_id == "transcript_123"
    assert meeting.recording_id == "recording_123"
    assert meeting.transcript_path == "transcripts/meeting_123.json"
    assert [event[1]["status"] for event in published_events] == ["complete"]

    async with db_sessionmaker() as session:
        participant = await session.scalar(select(Participant))
        segment = await session.scalar(select(TranscriptSegment))

    assert participant is not None
    assert participant.name == "Alice Smith"
    assert segment is not None
    assert segment.text == "Hello team"
    assert segment.start_ms == 500
    assert segment.end_ms == 1300


@pytest.mark.asyncio
async def test_done_without_ready_transcript_finalizes_on_next_ready_tick(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    httpx_mock: HTTPXMock,
    published_events: list[tuple[str, dict[str, object]]],
    tmp_path: Path,
) -> None:
    await create_meeting(db_sessionmaker, status="recording")
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

    bot_poller = make_poller(tmp_path)
    await bot_poller._tick()
    meeting_after_first_tick = await get_meeting(db_sessionmaker)
    assert meeting_after_first_tick.status == "processing"

    await bot_poller._tick()
    meeting_after_second_tick = await get_meeting(db_sessionmaker)
    assert meeting_after_second_tick.status == "complete"
    assert [event[1]["status"] for event in published_events] == ["processing", "complete"]


@pytest.mark.asyncio
async def test_fatal_status_sets_failed_with_sub_code(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    httpx_mock: HTTPXMock,
    published_events: list[tuple[str, dict[str, object]]],
    tmp_path: Path,
) -> None:
    await create_meeting(db_sessionmaker)
    add_bot_response(httpx_mock, "fatal", sub_code="bot_kicked_from_call")

    await make_poller(tmp_path)._tick()

    meeting = await get_meeting(db_sessionmaker)
    assert meeting.status == "failed"
    assert meeting.sub_code == "bot_kicked_from_call"
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
    db_sessionmaker: async_sessionmaker[AsyncSession],
    httpx_mock: HTTPXMock,
    published_events: list[tuple[str, dict[str, object]]],
    tmp_path: Path,
) -> None:
    await create_meeting(db_sessionmaker, status="joining")
    add_bot_response(httpx_mock, "fatal", response_status=500)

    await make_poller(tmp_path)._tick()

    meeting = await get_meeting(db_sessionmaker)
    assert meeting.status == "joining"
    assert published_events == []


@pytest.mark.asyncio
async def test_repeated_tick_without_status_change_does_not_republish(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    httpx_mock: HTTPXMock,
    published_events: list[tuple[str, dict[str, object]]],
    tmp_path: Path,
) -> None:
    await create_meeting(db_sessionmaker, status="recording")
    add_bot_response(httpx_mock, "in_call_recording")
    add_bot_response(httpx_mock, "in_call_recording")

    bot_poller = make_poller(tmp_path)
    await bot_poller._tick()
    await bot_poller._tick()

    assert published_events == []
