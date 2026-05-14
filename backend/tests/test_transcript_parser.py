import pytest

from app.services.transcript import parse_transcript


@pytest.mark.asyncio
async def test_parse_two_speaker_transcript() -> None:
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

    participants, segments = await parse_transcript("meeting_123", raw)

    assert [(p["recall_id"], p["name"], p["is_host"]) for p in participants] == [
        ("12345", "Alice Smith", True),
        ("67890", "Bob Jones", False),
    ]
    assert [
        (segment["speaker_label"], segment["text"], segment["start_ms"], segment["end_ms"])
        for segment in segments
    ] == [
        ("Alice Smith", "Hello team", 500, 1300),
        ("Bob Jones", "Morning", 2000, 2500),
    ]


@pytest.mark.asyncio
async def test_parse_empty_transcript_returns_empty() -> None:
    participants, segments = await parse_transcript("meeting_123", [])

    assert participants == []
    assert segments == []


@pytest.mark.asyncio
async def test_parse_skips_malformed_utterance_and_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
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

    participants, segments = await parse_transcript("meeting_123", raw)

    assert len(participants) == 1
    assert len(segments) == 1
    assert "Skipping malformed transcript utterance" in caplog.text
    assert segments[0]["speaker_label"] == "Bob Jones"
    assert segments[0]["text"] == "Still works"
    assert segments[0]["start_ms"] == 1000
    assert segments[0]["end_ms"] == 1800
