from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Meeting, Participant, TranscriptSegment
from app.services.transcript import parse_transcript


async def create_meeting(db_sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    now = datetime.now(UTC)
    async with db_sessionmaker() as session:
        session.add(
            Meeting(
                id="meeting_123",
                meeting_url="https://meet.google.com/abc-defg-hij",
                platform="meet",
                status="processing",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_parse_two_speaker_transcript(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await create_meeting(db_sessionmaker)
    raw: list[object] = [
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
        },
        {
            "participant": {"id": 67890, "name": "Bob Jones", "is_host": False},
            "words": [
                {
                    "text": "Morning",
                    "start_timestamp": {"relative": 2.0},
                    "end_timestamp": {"relative": 2.5},
                }
            ],
        },
    ]

    async with db_sessionmaker() as session:
        participants, segments = await parse_transcript("meeting_123", raw, session)
        await session.commit()

    assert len(participants) == 2
    assert len(segments) == 2

    async with db_sessionmaker() as session:
        stored_participants = list(
            await session.scalars(select(Participant).order_by(Participant.recall_id))
        )
        stored_segments = list(
            await session.scalars(select(TranscriptSegment).order_by(TranscriptSegment.start_ms))
        )

    assert [(p.recall_id, p.name, p.is_host) for p in stored_participants] == [
        ("12345", "Alice Smith", True),
        ("67890", "Bob Jones", False),
    ]
    assert [
        (segment.speaker_label, segment.text, segment.start_ms, segment.end_ms)
        for segment in stored_segments
    ] == [
        ("Alice Smith", "Hello team", 500, 1300),
        ("Bob Jones", "Morning", 2000, 2500),
    ]


@pytest.mark.asyncio
async def test_parse_empty_transcript_returns_empty(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await create_meeting(db_sessionmaker)

    async with db_sessionmaker() as session:
        participants, segments = await parse_transcript("meeting_123", [], session)

    assert participants == []
    assert segments == []


@pytest.mark.asyncio
async def test_parse_skips_malformed_utterance_and_logs_warning(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    await create_meeting(db_sessionmaker)
    raw: list[object] = [
        {"participant": {"id": 12345, "name": "Alice Smith"}},
        {
            "participant": {"id": 67890, "name": "Bob Jones"},
            "words": [
                {
                    "text": "Still",
                    "start_timestamp": {"relative": 1.0},
                    "end_timestamp": {"relative": 1.25},
                },
                {
                    "text": "works",
                    "start_timestamp": {"relative": 1.3},
                    "end_timestamp": {"relative": 1.8},
                },
            ],
        },
    ]

    async with db_sessionmaker() as session:
        participants, segments = await parse_transcript("meeting_123", raw, session)
        await session.commit()

    assert len(participants) == 1
    assert len(segments) == 1
    assert "Skipping malformed transcript utterance" in caplog.text

    async with db_sessionmaker() as session:
        segment = await session.scalar(select(TranscriptSegment))

    assert segment is not None
    assert segment.speaker_label == "Bob Jones"
    assert segment.text == "Still works"
    assert segment.start_ms == 1000
    assert segment.end_ms == 1800
